"""
Bulk Certificate Generator
--------------------------
Give a blank/sample certificate image + a CSV of names.
The tool finds the long underline on the certificate and prints each name on it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

import config


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def _font_candidates() -> list[Path]:
    """Common system + project font paths (Windows-first)."""
    windir = Path(r"C:\Windows\Fonts")
    names = [
        "georgia.ttf",
        "georgiab.ttf",
        "times.ttf",
        "timesbd.ttf",
        "arial.ttf",
        "arialbd.ttf",
        "calibri.ttf",
        "calibrib.ttf",
        "DejaVuSerif.ttf",
        "DejaVuSerif-Bold.ttf",
    ]
    paths: list[Path] = []
    for n in names:
        paths.append(config.FONTS_DIR / n)
        paths.append(windir / n)
    # macOS / Linux fallbacks
    paths.extend(
        [
            Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
        ]
    )
    return paths


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred = []
    if bold:
        preferred = ["georgiab.ttf", "timesbd.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSerif-Bold.ttf"]
    else:
        preferred = ["georgia.ttf", "times.ttf", "arial.ttf", "calibri.ttf", "DejaVuSerif.ttf"]

    for name in preferred:
        for base in (config.FONTS_DIR, Path(r"C:\Windows\Fonts")):
            p = base / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size=size)
                except OSError:
                    pass

    for p in _font_candidates():
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def fit_font(text: str, max_width: int, max_size: int, min_size: int) -> ImageFont.ImageFont:
    """Shrink font until text fits max_width."""
    size = max_size
    while size >= min_size:
        font = load_font(size, bold=True)
        bbox = font.getbbox(text)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            return font
        size -= 2
    return load_font(min_size, bold=True)


# ---------------------------------------------------------------------------
# Line detection — find the longest dark horizontal rule (name underline)
# ---------------------------------------------------------------------------

def detect_name_line(image: Image.Image) -> dict[str, Any] | None:
    """
    Scan the certificate for the longest dark horizontal line.
    Returns dict with y, x_start, x_end, length, thickness — or None.
    """
    gray = image.convert("L")
    w, h = gray.size
    pixels = gray.load()

    y0 = int(h * config.LINE_SEARCH_Y_START_RATIO)
    y1 = int(h * config.LINE_SEARCH_Y_END_RATIO)
    min_len = int(w * config.LINE_MIN_LENGTH_RATIO)
    thr = config.LINE_DARK_THRESHOLD

    # Score each row: longest contiguous dark run + total dark fraction
    best: dict[str, Any] | None = None
    best_score = 0.0

    y = y0
    while y < y1:
        # Build dark mask for this row
        dark = [pixels[x, y] < thr for x in range(w)]
        dark_count = sum(dark)
        if dark_count < w * config.LINE_ROW_INK_RATIO * 0.5:
            y += 1
            continue

        # Longest contiguous dark run
        run_start = 0
        longest = 0
        longest_start = 0
        longest_end = 0
        in_run = False
        for x in range(w):
            if dark[x]:
                if not in_run:
                    run_start = x
                    in_run = True
            else:
                if in_run:
                    run_len = x - run_start
                    if run_len > longest:
                        longest = run_len
                        longest_start = run_start
                        longest_end = x - 1
                    in_run = False
        if in_run:
            run_len = w - run_start
            if run_len > longest:
                longest = run_len
                longest_start = run_start
                longest_end = w - 1

        if longest < min_len:
            y += 1
            continue

        # Measure thickness downward from this row
        thickness = 1
        for dy in range(1, config.LINE_MAX_THICKNESS + 1):
            yy = y + dy
            if yy >= h:
                break
            row_dark = sum(1 for x in range(longest_start, longest_end + 1) if pixels[x, yy] < thr)
            if row_dark / max(1, longest) < 0.55:
                break
            thickness += 1

        if thickness < config.LINE_MIN_THICKNESS:
            y += 1
            continue

        # Prefer longer lines near vertical center of search band
        center = (y0 + y1) / 2
        center_bonus = 1.0 - abs(y - center) / max(1, (y1 - y0))
        score = longest * (1.0 + 0.35 * center_bonus) * (1.0 + 0.05 * thickness)

        if score > best_score:
            best_score = score
            best = {
                "y": y + thickness // 2,
                "y_top": y,
                "x_start": longest_start,
                "x_end": longest_end,
                "length": longest,
                "thickness": thickness,
                "score": score,
            }

        # Skip past this line's thickness so we don't re-detect the same rule
        y += max(1, thickness)
    return best


def ensure_blank_template(path: Path) -> Path:
    """Create a simple blank certificate with a name underline if none exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    w, h = 2000, 1414  # ~landscape A4 @ 150dpi-ish
    img = Image.new("RGB", (w, h), (252, 248, 240))
    draw = ImageDraw.Draw(img)

    # Outer double border
    for i, color in ((20, (40, 60, 100)), (28, (180, 150, 80)), (36, (40, 60, 100))):
        draw.rectangle([i, i, w - i, h - i], outline=color, width=3)

    title_font = load_font(72, bold=True)
    sub_font = load_font(28, bold=False)
    small = load_font(22, bold=False)

    def center_text(text: str, y: int, font, fill=(40, 50, 80)):
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) / 2, y), text, font=font, fill=fill)

    center_text("CERTIFICATE OF COMPLETION", 180, title_font, (30, 45, 90))
    center_text("This is to certify that", 340, sub_font, (80, 80, 90))

    # The long name line (what detect_name_line will find)
    line_y = 520
    line_x0, line_x1 = int(w * 0.18), int(w * 0.82)
    draw.line([(line_x0, line_y), (line_x1, line_y)], fill=(50, 50, 70), width=3)

    center_text("has successfully completed the program", 580, sub_font, (80, 80, 90))

    # Decorative footer lines
    draw.line([(int(w * 0.12), h - 220), (int(w * 0.35), h - 220)], fill=(100, 100, 120), width=2)
    draw.line([(int(w * 0.65), h - 220), (int(w * 0.88), h - 220)], fill=(100, 100, 120), width=2)
    center_text("Date", h - 200, small, (100, 100, 110))
    # fake right label without overlapping center
    sig_font = small
    sig = "Authorized Signatory"
    sb = sig_font.getbbox(sig)
    draw.text((int(w * 0.65) + (int(w * 0.23) - (sb[2] - sb[0])) / 2, h - 200), sig, font=sig_font, fill=(100, 100, 110))

    center_text("Team HMS", h - 120, load_font(26, bold=True), (40, 60, 100))

    img.save(path, "PNG")
    print(f"Created sample blank template: {path}")
    return path


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def find_name_column(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    for candidate in config.NAME_COLUMNS:
        if candidate in cols:
            return candidate
    # First column fallback
    if cols:
        return cols[0]
    raise ValueError("CSV has no columns.")


def load_recipients(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Recipients file not found: {path}")

    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df = _normalize_columns(df)
    df = df.dropna(how="all")
    name_col = find_name_column(df)
    df = df[df[name_col].notna()]
    df[name_col] = df[name_col].astype(str).str.strip()
    df = df[df[name_col] != ""]
    if df.empty:
        raise ValueError("No recipient names found in the file.")
    return df.reset_index(drop=True)


def safe_filename(name: str, index: int) -> str:
    cleaned = re.sub(r"[^\w\s\-]", "", name, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned.strip()) or "recipient"
    return f"{index:03d}_{cleaned}"


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_name_on_template(
    template: Image.Image,
    name: str,
    line_info: dict[str, Any] | None,
    extra: dict[str, str] | None = None,
) -> Image.Image:
    """Return a copy of the template with the name placed above the long line."""
    img = template.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    max_name_w = int(w * config.NAME_MAX_WIDTH_RATIO)
    max_size = min(config.NAME_MAX_FONT_SIZE, max(config.NAME_MIN_FONT_SIZE, int(h * config.NAME_FONT_SIZE_RATIO)))
    font = fit_font(name, max_name_w, max_size, config.NAME_MIN_FONT_SIZE)

    bbox = font.getbbox(name)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if line_info:
        # Center name on the detected line, sitting just above it
        cx = (line_info["x_start"] + line_info["x_end"]) / 2
        # text y: baseline-ish — Pillow text uses top-left of em-box
        text_x = cx - tw / 2
        text_y = line_info["y_top"] - th - config.NAME_GAP_ABOVE_LINE
        # Keep on canvas
        text_y = max(10, min(text_y, h - th - 10))
        text_x = max(10, min(text_x, w - tw - 10))
    else:
        text_x = (w - tw) / 2
        text_y = h * config.FALLBACK_NAME_Y_RATIO - th / 2

    draw.text((text_x, text_y), name, font=font, fill=config.NAME_COLOR)

    # Optional fields are deliberately placed well below the template's
    # pre-printed "has successfully completed..." sentence.  The previous
    # layout started immediately below the name line, which caused course/date
    # values to overlap that sentence on the bundled certificate template.
    if extra and line_info:
        sub_size = max(20, int(h * 0.022))
        sub_font = load_font(sub_size, bold=False)
        # Keep the first field clear of the template's fixed subtitle, then use
        # a consistent vertical rhythm for all supplied fields.
        y = max(
            line_info["y_top"] + int(h * 0.09),
            int(h * 0.45),
        )
        line_gap = max(int(h * 0.045), sub_size + int(h * 0.015))
        for key, _label in config.OPTIONAL_FIELDS:
            val = extra.get(key)
            if not val:
                continue
            if val.strip().lower() == name.strip().lower():
                continue

            # Fit long course/organization names within the certificate width.
            field_font = fit_font(val, int(w * 0.72), sub_size, max(16, int(sub_size * 0.7)))
            sb = field_font.getbbox(val)
            sw = sb[2] - sb[0]
            sh = sb[3] - sb[1]
            text_x = max(10, min((w - sw) / 2, w - sw - 10))
            draw.text((text_x, y), val, font=field_font, fill=(70, 70, 90))
            y += max(line_gap, sh + int(h * 0.015))
            if y > h * 0.78:
                break

    return img


def save_outputs(img: Image.Image, out_dir: Path, stem: str, fmt: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    fmt = fmt.lower()
    if fmt in ("png", "both"):
        p = out_dir / f"{stem}.png"
        img.save(p, "PNG", dpi=(config.PNG_DPI, config.PNG_DPI))
        saved.append(p)
    if fmt in ("pdf", "both"):
        p = out_dir / f"{stem}.pdf"
        rgb = img.convert("RGB")
        rgb.save(p, "PDF", resolution=float(config.PNG_DPI))
        saved.append(p)
    return saved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_certificates(
    recipients_path: str | Path,
    template_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_format: str | None = None,
    name_column: str | None = None,
    draw_extras: bool = True,
) -> list[Path]:
    """
    Load blank certificate + CSV, detect the long name line, stamp each name.

    Returns list of written file paths.
    """
    recipients_path = Path(recipients_path)
    template_path = Path(template_path) if template_path else config.DEFAULT_TEMPLATE
    output_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
    output_format = output_format or config.OUTPUT_FORMAT

    if not template_path.exists():
        if template_path == config.DEFAULT_TEMPLATE:
            ensure_blank_template(template_path)
        else:
            raise FileNotFoundError(
                f"Template image not found: {template_path}\n"
                "Place your blank certificate PNG/JPG in templates/ and pass --template."
            )

    template = Image.open(template_path)
    # Flatten alpha onto white if needed
    if template.mode in ("RGBA", "LA") or (template.mode == "P" and "transparency" in template.info):
        bg = Image.new("RGB", template.size, (255, 255, 255))
        rgba = template.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        template = bg
    else:
        template = template.convert("RGB")

    line_info = detect_name_line(template)
    if line_info:
        print(
            f"Detected name line at y={line_info['y']} "
            f"(x={line_info['x_start']}..{line_info['x_end']}, "
            f"length={line_info['length']}px, thickness={line_info['thickness']}px)"
        )
    else:
        print(
            "WARNING: No long horizontal line found on the template. "
            f"Names will be centered at ~{int(config.FALLBACK_NAME_Y_RATIO * 100)}% height. "
            "For best results, use a blank certificate that has a clear underline for the name."
        )

    df = load_recipients(recipients_path)
    col = name_column.lower().strip() if name_column else find_name_column(df)
    if col not in df.columns:
        raise ValueError(f"Name column '{col}' not in CSV. Columns: {list(df.columns)}")

    written: list[Path] = []
    total = len(df)
    print(f"Generating {total} certificate(s) -> {output_dir.resolve()}")

    for i, row in df.iterrows():
        name = str(row[col]).strip()
        extra: dict[str, str] = {}
        if draw_extras:
            for key, _label in config.OPTIONAL_FIELDS:
                if key in df.columns and key != col:
                    val = row.get(key)
                    if pd.notna(val) and str(val).strip():
                        extra[key] = str(val).strip()

        cert = draw_name_on_template(template, name, line_info, extra or None)
        stem = safe_filename(name, int(i) + 1)
        paths = save_outputs(cert, output_dir, stem, output_format)
        written.extend(paths)
        print(f"  [{int(i) + 1}/{total}] {name} -> {', '.join(p.name for p in paths)}")

    print(f"Done. {len(written)} file(s) written.")
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bulk certificates: blank image + CSV names placed on the long line."
    )
    p.add_argument(
        "-d", "--data",
        default=str(config.DATA_DIR / "recipients.csv"),
        help="CSV or Excel with a name column (default: data/recipients.csv)",
    )
    p.add_argument(
        "-t", "--template",
        default=str(config.DEFAULT_TEMPLATE),
        help="Blank/sample certificate image (PNG/JPG). Long underline is auto-detected.",
    )
    p.add_argument(
        "-o", "--output",
        default=str(config.OUTPUT_DIR),
        help="Output folder (default: output/)",
    )
    p.add_argument(
        "-f", "--format",
        choices=("png", "pdf", "both"),
        default=config.OUTPUT_FORMAT,
        help="Output format (default: both)",
    )
    p.add_argument(
        "--name-column",
        default=None,
        help="CSV column for names (default: auto-detect name/full_name/…)",
    )
    p.add_argument(
        "--no-extras",
        action="store_true",
        help="Only draw the name (ignore course/date/etc. columns)",
    )
    p.add_argument(
        "--make-blank",
        action="store_true",
        help="Write a sample blank certificate to templates/ and exit",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.make_blank:
        ensure_blank_template(config.DEFAULT_TEMPLATE)
        return 0

    try:
        generate_certificates(
            recipients_path=args.data,
            template_path=args.template,
            output_dir=args.output,
            output_format=args.format,
            name_column=args.name_column,
            draw_extras=not args.no_extras,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
