"""Central, named configuration. No magic numbers scattered through the code.

Every threshold used anywhere in the pipeline lives here so it can be
reviewed, tuned, and cited from the documentation in one place.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
DOCUMENT_EXTENSIONS = {".pdf"}
# Proprietary / source formats we deliberately do NOT deep-parse (would
# require large dependencies e.g. psd-tools). We still record file-level
# facts (size, hash, mtime) and flag them clearly.
SOURCE_ONLY_EXTENSIONS = {".psd", ".ai", ".indd", ".sketch", ".fig", ".eps"}

ALL_KNOWN_EXTENSIONS = (
    IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS | SOURCE_ONLY_EXTENSIONS
)

# Directories that signal "this is a source/working file, not a delivery
# candidate" purely by location, regardless of filename.
SOURCE_FOLDER_NAMES = {"source", "sources", "src", "working", "wip", "raw"}

# ---------------------------------------------------------------------------
# Duplicate / similarity thresholds  (see docs/architecture-decision.md §5)
# ---------------------------------------------------------------------------
PHASH_SIZE = 16  # imagehash phash hash_size -> 16x16 = 256-bit hash, higher precision
VISUAL_DUPLICATE_MAX_DISTANCE = 10     # <= this Hamming distance => VISUAL_DUPLICATE
VISUALLY_SIMILAR_MAX_DISTANCE = 28     # <= this (and > duplicate) => VISUALLY_SIMILAR

# ---------------------------------------------------------------------------
# Filename signal patterns (deterministic, regex-based)
# ---------------------------------------------------------------------------
FINAL_PATTERNS = [
    r"final\s*final",
    r"\bfinal\b",
    r"\bFINAL\b",
    r"approved",
    r"delivered?",
    r"\blatest\b",
]
INTERMEDIATE_PATTERNS = [
    r"\bdraft\b",
    r"\bwip\b",
    r"\bold\b",
    r"\btemp\b",
    r"\btest\b",
    r"copy\s*\d*$",
    r"\bv0*1\b",  # v1 / v01 read as an early, likely-superseded version (matched against the separator-normalized filename -- see classification._normalize_for_word_match)
]
VERSION_SUFFIX_PATTERN = r"(_v\d+|_final|_FINAL|_new|_newest|_latest|_revised|_rev\d*|\(\d+\)|_\d{1,3}$|_copy\d*)"

# ---------------------------------------------------------------------------
# Classification scoring weights (see docs/architecture-decision.md §7)
# ---------------------------------------------------------------------------
SCORE_FINAL_FILENAME = 0.35
SCORE_MOST_RECENT_IN_FAMILY = 0.20
SCORE_MATCHES_MANIFEST = 0.15
SCORE_NOT_DUPLICATE = 0.10
SCORE_AI_CONFIDENCE_WEIGHT = 0.20
PENALTY_EXACT_DUPLICATE = -0.30
PENALTY_INTERMEDIATE_FILENAME = -0.20

THRESHOLD_LIKELY_FINAL = 0.72
THRESHOLD_NEEDS_REVIEW_LOW = 0.40
REVIEW_BAND_MARGIN = 0.08  # scores within this margin of a threshold force review

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------
MAX_IMAGE_SIZE_BYTES = 50 * 1024 * 1024     # 50 MB
MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024    # 500 MB
ASPECT_RATIO_TOLERANCE = 0.02               # 2% tolerance when comparing to manifest

# ---------------------------------------------------------------------------
# Delivery category mapping — first match wins
# ---------------------------------------------------------------------------
CATEGORY_RULES = [
    # (predicate keys checked in delivery.py) -> category folder name
    ("brand_asset", "Brand_Assets"),
    ("social", "Social"),
    ("web", "Web"),
    ("video", "Videos"),
    ("image", "Images"),
    ("source", "Source"),
]

DEFAULT_OUTPUT_DIR_NAME = "output"
DELIVERY_DIR_NAME = "delivery"
