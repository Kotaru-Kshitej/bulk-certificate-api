"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
FONTS_DIR = BASE_DIR / "fonts"
# On Render, point these at the persistent disk (e.g. /var/data/output) via env vars.
OUTPUT_DIR = Path(os.environ.get("CERT_OUTPUT_DIR", BASE_DIR / "output"))
DATA_DIR = Path(os.environ.get("CERT_DATA_DIR", BASE_DIR / "data"))

# Ensure runtime directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Runtime settings (override via env vars)."""

    app_name: str = "Bulk Certificate Generator"
    app_version: str = "1.0.0"
    database_url: str = f"sqlite:///{(DATA_DIR / 'certificates.db').as_posix()}"
    # Single predefined template (brief requirement)
    certificate_template: Path = TEMPLATES_DIR / "certificate_template.png"
    # Background worker polls this often (seconds)
    worker_poll_interval: float = 0.5
    # Set CERT_ENABLE_WORKER=false in tests to skip the daemon thread
    enable_worker: bool = True
    # Certificate layout (pixels on 1200x850 template)
    name_y: int = 370
    name_max_width: int = 700
    name_font_max: int = 48
    name_font_min: int = 18
    course_y: int = 500
    course_font_size: int = 28
    date_y: int = 560
    date_font_size: int = 22
    signatory_xy: tuple[int, int] = (300, 700)
    organization_xy: tuple[int, int] = (900, 700)
    meta_font_size: int = 18
    text_color: tuple[int, int, int] = (30, 40, 60)
    accent_color: tuple[int, int, int] = (30, 60, 120)

    class Config:
        env_prefix = "CERT_"


settings = Settings()
