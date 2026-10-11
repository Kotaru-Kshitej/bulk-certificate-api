"""HTTP routes for bulk certificate generation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import __version__
from app.database import get_db
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import (
    CertificateOut,
    HealthOut,
    JobCreateRequest,
    JobCreateResponse,
    JobOut,
)

router = APIRouter()


def _cert_to_out(cert: Certificate) -> CertificateOut:
    download = None
    if cert.status == CertificateStatus.SUCCESS and cert.file_path:
        download = f"/api/v1/certificates/{cert.id}/download"
    return CertificateOut(
        id=cert.id,
        job_id=cert.job_id,
        recipient_name=cert.recipient_name,
        course=cert.course,
        date=cert.date,
        signatory=cert.signatory,
        organization=cert.organization,
        status=cert.status,
        error_message=cert.error_message,
        download_url=download,
        created_at=cert.created_at,
        generated_at=cert.generated_at,
    )


def _job_to_out(job: Job, *, include_certificates: bool = False) -> JobOut:
    pending = max(job.total_recipients - job.success_count - job.failure_count, 0)
    done = job.success_count + job.failure_count
    progress = (done / job.total_recipients * 100.0) if job.total_recipients else 0.0
    certs = None
    if include_certificates:
        certs = [_cert_to_out(c) for c in job.certificates]
    return JobOut(
        id=job.id,
        status=job.status,
        title=job.title,
        total_recipients=job.total_recipients,
        success_count=job.success_count,
        failure_count=job.failure_count,
        pending_count=pending,
        progress_percent=round(progress, 2),
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        certificates=certs,
    )


@router.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    return HealthOut(status="ok", version=__version__)


@router.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    summary="Submit a bulk certificate generation request",
)
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)) -> JobCreateResponse:
    """
    Accept a list of recipients and enqueue a generation job.

    Validation is handled by Pydantic (empty names rejected, list non-empty).
    Generation runs in the background; poll GET /jobs/{id} for progress.
    """
    job = Job(
        status=JobStatus.PENDING,
        title=payload.title,
        total_recipients=len(payload.recipients),
        success_count=0,
        failure_count=0,
    )
    db.add(job)
    db.flush()  # assign job.id

    for recipient in payload.recipients:
        db.add(
            Certificate(
                job_id=job.id,
                recipient_name=recipient.name,
                course=recipient.course,
                date=recipient.date,
                signatory=recipient.signatory,
                organization=recipient.organization,
                status=CertificateStatus.PENDING,
            )
        )

    db.commit()
    db.refresh(job)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_recipients=job.total_recipients,
        message="Job accepted. Certificate generation is running in the background.",
        status_url=f"/api/v1/jobs/{job.id}",
        certificates_url=f"/api/v1/jobs/{job.id}/certificates",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    tags=["jobs"],
    summary="Get job status and progress",
)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.execute(
        select(Job).where(Job.id == job_id).options(selectinload(Job.certificates))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_to_out(job, include_certificates=True)


@router.get(
    "/jobs/{job_id}/certificates",
    response_model=list[CertificateOut],
    tags=["certificates"],
    summary="List certificates for a job",
)
def list_job_certificates(job_id: int, db: Session = Depends(get_db)) -> list[CertificateOut]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    certs = db.execute(
        select(Certificate).where(Certificate.job_id == job_id).order_by(Certificate.id.asc())
    ).scalars().all()
    return [_cert_to_out(c) for c in certs]


@router.get(
    "/certificates/{certificate_id}",
    response_model=CertificateOut,
    tags=["certificates"],
    summary="Get a single certificate record",
)
def get_certificate(certificate_id: int, db: Session = Depends(get_db)) -> CertificateOut:
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return _cert_to_out(cert)


@router.get(
    "/certificates/{certificate_id}/download",
    tags=["certificates"],
    summary="Download a generated certificate PNG",
)
def download_certificate(certificate_id: int, db: Session = Depends(get_db)) -> FileResponse:
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    if cert.status != CertificateStatus.SUCCESS or not cert.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=cert.error_message or "Certificate is not available for download",
        )
    path = Path(cert.file_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate file missing on disk",
        )
    filename = path.name
    return FileResponse(
        path,
        media_type="image/png",
        filename=filename,
        content_disposition_type="attachment",
    )
