"""Pytest fixtures — isolated SQLite DB, no background worker thread."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure app package is importable when running pytest from project root
os.environ.setdefault("CERT_DATABASE_URL", "sqlite://")
os.environ["CERT_ENABLE_WORKER"] = "false"

from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.worker import stop_worker  # noqa: E402

settings.enable_worker = False


@pytest.fixture()
def db_engine(tmp_path: Path):
    """In-memory SQLite shared across connections (StaticPool)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, future=True)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """API client with overridden DB + isolated output dir. Worker is stopped."""
    stop_worker()

    TestingSessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, future=True)

    def _override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Point certificate output at tmp
    monkeypatch.setattr("app.certificate_service.OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr("app.config.OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)

    # Use lifespan off so we control the worker ourselves in tests
    with TestClient(app, raise_server_exceptions=True) as test_client:
        stop_worker()  # lifespan may have started it
        yield test_client

    app.dependency_overrides.clear()
    stop_worker()


@pytest.fixture()
def sample_recipients() -> list[dict]:
    return [
        {
            "name": "Aisha Khan",
            "course": "Full Stack Web Development",
            "date": "March 15, 2026",
            "signatory": "Dr. R. Mehta",
            "organization": "Team HMS",
        },
        {
            "name": "Jordan Lee",
            "course": "Data Science Bootcamp",
            "date": "March 15, 2026",
            "signatory": "Dr. R. Mehta",
            "organization": "Team HMS",
        },
    ]
