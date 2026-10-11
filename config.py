"""Configuration for bulk certificate generation."""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
FONTS_DIR = BASE_DIR / "fonts"

# Default blank template (generated on first run if missing)
DEFAULT_TEMPLATE = TEMPLATES_DIR / "blank_certificate.png"

# CSV column used for the name on the long line (case-insensitive match)
NAME_COLUMNS = ("name", "full_name", "recipient", "student", "participant")

# Optional extra fields drawn under the name line (if columns exist)
OPTIONAL_FIELDS = (
    ("course", "Course"),
    ("date", "Date"),
    ("organization", "Organization"),
    ("signatory", "Signed by"),
)

# Name text styling (on top of template image)
NAME_FONT_SIZE_RATIO = 0.045  # fraction of image height
NAME_MIN_FONT_SIZE = 28
NAME_MAX_FONT_SIZE = 96
NAME_COLOR = (30, 30, 50)  # dark navy
NAME_GAP_ABOVE_LINE = 12  # pixels between text baseline and the detected line
NAME_MAX_WIDTH_RATIO = 0.72  # name must fit within this fraction of image width

# Line detection (finds the longest dark horizontal rule = name underline)
LINE_DARK_THRESHOLD = 140  # pixel darker than this counts as "ink"
LINE_MIN_LENGTH_RATIO = 0.25  # line must span at least 25% of image width
LINE_MIN_THICKNESS = 1
LINE_MAX_THICKNESS = 12
LINE_SEARCH_Y_START_RATIO = 0.25  # ignore top 25% (headers/logos)
LINE_SEARCH_Y_END_RATIO = 0.85  # ignore bottom 15% (signatures/footer)
LINE_ROW_INK_RATIO = 0.18  # min fraction of row pixels that are dark

# Fallback name position if no line is found (center of image)
FALLBACK_NAME_Y_RATIO = 0.48

# Output
OUTPUT_FORMAT = "both"  # "pdf" | "png" | "both"
PNG_DPI = 150
