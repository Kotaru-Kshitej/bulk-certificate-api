"""API and generation tests required by the brief."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.certificate_service import CertificateGenerationError, generate_certificate_file
from app.models import CertificateStatus, JobStatus
from app.worker import process_all_pending_sync


def _run_jobs(client: TestClient) -> None:
    """
    Process pending jobs using the same DB the TestClient uses.

    The background worker is disabled in tests; we call the processor
    with SessionLocal rebound to the override engine via process hooks
    in each test that needs generation.
    """
    # process_all_pending_sync uses SessionLocal from app.database —
    # tests patch SessionLocal to the test session factory.
    process_all_pending_sync()


@pytest.fixture()
def run_worker(client, db_engine, monkeypatch):
    """Patch SessionLocal so the worker uses the in-memory test DB."""
    from sqlalchemy.orm import sessionmaker

    from app import database as db_module
    from app import worker as worker_module

    TestSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, future=True)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    monkeypatch.setattr(worker_module, "SessionLocal", TestSession)

    def _run() -> None:
        process_all_pending_sync()

    return _run


# ---------------------------------------------------------------------------
# Creating a generation job
# ---------------------------------------------------------------------------


def test_create_job(client: TestClient, sample_recipients: list[dict], run_worker):
    response = client.post(
        "/api/v1/jobs",
        json={"title": "Spring Cohort", "recipients": sample_recipients},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] >= 1
    assert body["status"] == JobStatus.PENDING.value
    assert body["total_recipients"] == 2
    assert "/api/v1/jobs/" in body["status_url"]


def test_create_job_minimal_name_only(client: TestClient):
    response = client.post(
        "/api/v1/jobs",
        json={"recipients": [{"name": "Only Name"}]},
    )
    assert response.status_code == 202
    assert response.json()["total_recipients"] == 1


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_validation_rejects_empty_recipients(client: TestClient):
    response = client.post("/api/v1/jobs", json={"recipients": []})
    assert response.status_code == 422


def test_validation_rejects_missing_recipients(client: TestClient):
    response = client.post("/api/v1/jobs", json={"title": "x"})
    assert response.status_code == 422


def test_validation_rejects_blank_name(client: TestClient):
    response = client.post(
        "/api/v1/jobs",
        json={"recipients": [{"name": "   "}]},
    )
    assert response.status_code == 422


def test_validation_rejects_missing_name(client: TestClient):
    response = client.post(
        "/api/v1/jobs",
        json={"recipients": [{"course": "Python"}]},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Certificate generation (unit + via job)
# ---------------------------------------------------------------------------


def test_generate_certificate_file_writes_png(tmp_path: Path):
    out = generate_certificate_file(
        cert_id=1,
        job_id=99,
        recipient_name="Test User",
        course="Intro to APIs",
        date="2026-01-01",
        signatory="Director",
        organization="Org",
        output_dir=tmp_path,
    )
    assert out.is_file()
    assert out.suffix == ".png"
    assert out.stat().st_size > 1000


def test_job_generates_certificates(
    client: TestClient, sample_recipients: list[dict], run_worker
):
    create = client.post("/api/v1/jobs", json={"recipients": sample_recipients})
    job_id = create.json()["job_id"]

    run_worker()

    status = client.get(f"/api/v1/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == JobStatus.COMPLETED.value
    assert body["success_count"] == 2
    assert body["failure_count"] == 0
    assert body["progress_percent"] == 100.0
    assert len(body["certificates"]) == 2
    for cert in body["certificates"]:
        assert cert["status"] == CertificateStatus.SUCCESS.value
        assert cert["download_url"] is not None


# ---------------------------------------------------------------------------
# Job status / progress
# ---------------------------------------------------------------------------


def test_job_status_progress_before_and_after(
    client: TestClient, sample_recipients: list[dict], run_worker
):
    create = client.post("/api/v1/jobs", json={"recipients": sample_recipients})
    job_id = create.json()["job_id"]

    before = client.get(f"/api/v1/jobs/{job_id}").json()
    assert before["status"] == JobStatus.PENDING.value
    assert before["pending_count"] == 2
    assert before["progress_percent"] == 0.0

    run_worker()

    after = client.get(f"/api/v1/jobs/{job_id}").json()
    assert after["status"] == JobStatus.COMPLETED.value
    assert after["pending_count"] == 0
    assert after["progress_percent"] == 100.0
    assert after["started_at"] is not None
    assert after["completed_at"] is not None


def test_get_job_not_found(client: TestClient):
    response = client.get("/api/v1/jobs/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Individual certificate failure does not block others
# ---------------------------------------------------------------------------


def test_individual_failure_isolated(
    client: TestClient, sample_recipients: list[dict], run_worker, monkeypatch
):
    """One bad generation must not stop the rest of the job."""
    real_generate = generate_certificate_file
    call_count = {"n": 0}

    def flaky_generate(**kwargs):
        call_count["n"] += 1
        # Fail only the first certificate
        if call_count["n"] == 1:
            raise CertificateGenerationError("simulated render failure")
        return real_generate(**kwargs)

    monkeypatch.setattr("app.worker.generate_certificate_file", flaky_generate)

    create = client.post("/api/v1/jobs", json={"recipients": sample_recipients})
    job_id = create.json()["job_id"]
    run_worker()

    body = client.get(f"/api/v1/jobs/{job_id}").json()
    assert body["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    assert body["success_count"] == 1
    assert body["failure_count"] == 1

    statuses = {c["recipient_name"]: c["status"] for c in body["certificates"]}
    # Order follows insertion; first recipient fails
    assert statuses["Aisha Khan"] == CertificateStatus.FAILED.value
    assert statuses["Jordan Lee"] == CertificateStatus.SUCCESS.value

    failed = next(c for c in body["certificates"] if c["status"] == "failed")
    assert "simulated render failure" in (failed["error_message"] or "")


# ---------------------------------------------------------------------------
# Retrieving generated certificates
# ---------------------------------------------------------------------------


def test_list_and_download_certificates(
    client: TestClient, sample_recipients: list[dict], run_worker
):
    create = client.post("/api/v1/jobs", json={"recipients": sample_recipients})
    job_id = create.json()["job_id"]
    run_worker()

    listing = client.get(f"/api/v1/jobs/{job_id}/certificates")
    assert listing.status_code == 200
    certs = listing.json()
    assert len(certs) == 2

    cert_id = certs[0]["id"]
    meta = client.get(f"/api/v1/certificates/{cert_id}")
    assert meta.status_code == 200
    assert meta.json()["recipient_name"] == certs[0]["recipient_name"]

    download = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/png")
    assert len(download.content) > 1000


def test_download_pending_certificate_conflict(client: TestClient, sample_recipients: list[dict]):
    create = client.post("/api/v1/jobs", json={"recipients": sample_recipients})
    job_id = create.json()["job_id"]
    certs = client.get(f"/api/v1/jobs/{job_id}/certificates").json()
    cert_id = certs[0]["id"]

    response = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 409


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
