"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CertificateStatus, JobStatus


class RecipientIn(BaseModel):
    """Single recipient in a bulk generation request."""

    name: str = Field(..., min_length=1, max_length=255, description="Recipient full name")
    course: str | None = Field(None, max_length=255)
    date: str | None = Field(None, max_length=100)
    signatory: str | None = Field(None, max_length=255)
    organization: str | None = Field(None, max_length=255)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("course", "date", "signatory", "organization", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v


class JobCreateRequest(BaseModel):
    """POST /jobs body: bulk certificate generation request."""

    title: str | None = Field(None, max_length=255, description="Optional job label")
    recipients: list[RecipientIn] = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="List of recipients (bulk — one request for many certificates)",
    )


class CertificateOut(BaseModel):
    """Certificate summary in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    recipient_name: str
    course: str | None
    date: str | None
    signatory: str | None
    organization: str | None
    status: CertificateStatus
    error_message: str | None
    download_url: str | None = None
    created_at: datetime
    generated_at: datetime | None


class JobOut(BaseModel):
    """Job summary / status response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: JobStatus
    title: str | None
    total_recipients: int
    success_count: int
    failure_count: int
    pending_count: int = 0
    progress_percent: float = 0.0
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    certificates: list[CertificateOut] | None = None


class JobCreateResponse(BaseModel):
    """Response after accepting a generation request."""

    job_id: int
    status: JobStatus
    total_recipients: int
    message: str
    status_url: str
    certificates_url: str


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
