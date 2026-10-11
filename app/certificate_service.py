"""Certificate image generation from the predefined template."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import FONTS_DIR, OUTPUT_DIR, settings


class CertificateGenerationError(Exception):
    """Raised when a single certificate cannot be generated."""


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try common system fonts; fall back to Pillow default."""
    candidates = [
        str(FONTS_DIR / "DejaVuSans.ttf"),  # bundled, so it works on any server
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(text: str, max_width: int, max_size: int, min_size: int) -> ImageFont.ImageFont:
    size = max_size
    while size >= min_size:
        font = _load_font(size)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 2
    return _load_font(min_size)


def _safe_filename(name: str, cert_id: int) -> str:
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    slug = re.sub(r"[-\s]+", "_", slug).strip("_") or "recipient"
    return f"{cert_id:04d}_{slug[:80]}.png"


def generate_certificate_file(
    *,
    cert_id: int,
    job_id: int,
    recipient_name: str,
    course: str | None = None,
    date: str | None = None,
    signatory: str | None = None,
    organization: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """
    Render one certificate PNG from the predefined template.

    Returns the absolute path of the written file.
    Raises CertificateGenerationError on failure.
    """
    template_path = settings.certificate_template
    if not template_path.is_file():
        raise CertificateGenerationError(f"Template not found: {template_path}")

    out_root = output_dir or (OUTPUT_DIR / f"job_{job_id}")
    try:
        out_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CertificateGenerationError(f"Cannot create output dir: {exc}") from exc

    try:
        img = Image.open(template_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, _h = img.size
        cx = w // 2

        # Recipient name (primary field) — centered above the underline
        name_font = _fit_font(
            recipient_name,
            settings.name_max_width,
            settings.name_font_max,
            settings.name_font_min,
        )
        draw.text(
            (cx, settings.name_y),
            recipient_name,
            fill=settings.accent_color,
            font=name_font,
            anchor="mm",
        )

        if course:
            course_font = _fit_font(course, settings.name_max_width, settings.course_font_size, 14)
            draw.text(
                (cx, settings.course_y),
                course,
                fill=settings.accent_color,
                font=course_font,
                anchor="mm",
            )

        if date:
            date_font = _load_font(settings.date_font_size)
            draw.text(
                (cx, settings.date_y),
                f"Date: {date}",
                fill=settings.text_color,
                font=date_font,
                anchor="mm",
            )

        meta_font = _load_font(settings.meta_font_size)
        if signatory:
            sx, sy = settings.signatory_xy
            draw.text((sx, sy), signatory, fill=settings.text_color, font=meta_font, anchor="mt")

        if organization:
            ox, oy = settings.organization_xy
            draw.text((ox, oy), organization, fill=settings.text_color, font=meta_font, anchor="mt")

        out_path = out_root / _safe_filename(recipient_name, cert_id)
        img.save(out_path, format="PNG", optimize=True)
        return out_path
    except CertificateGenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as generation failure
        raise CertificateGenerationError(str(exc)) from exc
