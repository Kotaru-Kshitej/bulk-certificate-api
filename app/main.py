"""
FastAPI application entrypoint.

Run:
    uvicorn app.main:app --reload --app-dir .
or:
    python -m app.main
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import router
from app.config import settings
from app.database import init_db
from app.worker import start_worker, stop_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.enable_worker:
        start_worker()
    yield
    stop_worker()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Backend API for bulk certificate generation. "
        "Submit a list of recipients, track job progress, and download certificates."
    ),
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
