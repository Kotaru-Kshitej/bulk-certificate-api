"""Background worker that processes pending certificate jobs.

Design choice (documented in README):
- Jobs are accepted immediately and processed asynchronously in a daemon thread.
- This keeps HTTP requests fast for bulk lists and isolates slow image I/O
  from the API event loop. SQLite + a single worker thread avoids concurrent
  write contention while remaining simple to run locally.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.certificate_service import CertificateGenerationError, generate_certificate_file
from app.config import settings
from app.database import SessionLocal
from app.models import Certificate, CertificateStatus, Job, JobStatus

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def process_job(job_id: int) -> None:
    """Generate certificates for one job; isolate per-recipient failures."""
    db = SessionLocal()
    try:
        job = db.execute(
            select(Job).where(Job.id == job_id).options(selectinload(Job.certificates))
        ).scalar_one_or_none()
        if job is None:
            return

        job.status = JobStatus.PROCESSING
        job.started_at = _utcnow()
        db.commit()

        success = 0
        failure = 0

        for cert in job.certificates:
            if cert.status == CertificateStatus.SUCCESS:
                success += 1
                continue

            try:
                path = generate_certificate_file(
                    cert_id=cert.id,
                    job_id=job.id,
                    recipient_name=cert.recipient_name,
                    course=cert.course,
                    date=cert.date,
                    signatory=cert.signatory,
                    organization=cert.organization,
                )
                cert.status = CertificateStatus.SUCCESS
                cert.file_path = str(path)
                cert.error_message = None
                cert.generated_at = _utcnow()
                success += 1
            except CertificateGenerationError as exc:
                logger.warning("Certificate %s failed: %s", cert.id, exc)
                cert.status = CertificateStatus.FAILED
                cert.error_message = str(exc)
                failure += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error for certificate %s", cert.id)
                cert.status = CertificateStatus.FAILED
                cert.error_message = f"Unexpected error: {exc}"
                failure += 1

            job.success_count = success
            job.failure_count = failure
            db.commit()

        job.success_count = success
        job.failure_count = failure
        job.completed_at = _utcnow()
        if failure == 0:
            job.status = JobStatus.COMPLETED
        elif success == 0:
            job.status = JobStatus.FAILED
            job.error_message = "All certificate generations failed"
        else:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s crashed", job_id)
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = _utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def _claim_next_pending_job() -> int | None:
    """Pick the oldest pending job id, or None."""
    db = SessionLocal()
    try:
        job = db.execute(
            select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.id.asc()).limit(1)
        ).scalar_one_or_none()
        return job.id if job else None
    except Exception:  # noqa: BLE001 — keep worker alive across transient DB issues
        logger.exception("Failed to claim pending job")
        return None
    finally:
        db.close()


def _worker_loop() -> None:
    logger.info("Certificate worker started")
    while not _stop_event.is_set():
        try:
            job_id = _claim_next_pending_job()
            if job_id is not None:
                process_job(job_id)
            else:
                _stop_event.wait(settings.worker_poll_interval)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            _stop_event.wait(settings.worker_poll_interval)
    logger.info("Certificate worker stopped")


def start_worker() -> None:
    """Start the background daemon thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_worker_loop, name="cert-worker", daemon=True)
    _thread.start()


def stop_worker(timeout: float = 5.0) -> None:
    """Signal the worker to stop (used in tests/shutdown)."""
    global _thread
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=timeout)
        _thread = None


def process_all_pending_sync() -> None:
    """Process every pending job in-process (tests / CLI without background thread)."""
    while True:
        job_id = _claim_next_pending_job()
        if job_id is None:
            break
        process_job(job_id)
