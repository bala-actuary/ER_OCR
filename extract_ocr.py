#!/usr/bin/env python3
"""
Electoral Roll PDF Data Extraction using OCR (Tesseract + OpenCV).

Extracts voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs)
into structured CSV files. Uses PyMuPDF for image extraction, OpenCV for grid
detection, and Tesseract OCR for text recognition.

Usage:
    python extract_ocr.py AC-184-Part-1-50                # Process one directory
    python extract_ocr.py AC-184-Part-1-50 --validate     # Test on 1 pair
    python extract_ocr.py --all --workers 4               # Process all directories
    python extract_ocr.py AC-184-Part-1-50 --dry-run      # Show pairs only
    python extract_ocr.py AC-184-Part-1-50 --reset        # Reset checkpoint
    python extract_ocr.py AC-184-Part-1-50 --limit 10     # Process only 10 pairs
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import traceback
import unicodedata
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
import io

try:
    import pytesseract
    # Set Tesseract path for Windows (default install location)
    _tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_tess_path):
        pytesseract.pytesseract.tesseract_cmd = _tess_path
except ImportError:
    pytesseract = None

# ----- Configuration -----

OCR_DIR = Path(__file__).parent          # ER_OCR/
INPUT_DIR = OCR_DIR / "Input" / "split_files"
OUTPUT_DIR = OCR_DIR / "output"
CHECKPOINT_DIR = OCR_DIR / "checkpoints"

BATCH_DIRS = [
    "AC-184-Part-1-50",
    "AC-184-Part-51-100",
    "AC-184-Part-101-150",
    "AC-184-Part-151-200",
    "AC-184-Part-201-250",
    "AC-184-Part-251-300",
    "AC-184-Part-301-350",
    "AC-184-Part-351-400",
]

CSV_HEADERS = [
    "AC No", "Part No", "Serial No", "EPIC ID",
    "Name (English)", "Name (Tamil)",
    "Relation Name (English)", "Relation Name (Tamil)",
    "Relation Type", "House No", "Age", "Gender",
    "DOB", "ContactNo",
]

# ----- Logging -----

log = logging.getLogger("extract_ocr")


def setup_logging(log_file: Path = None):
    """Configure dual logging: console + file."""
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)


# ----- Filename Parsing -----

FILENAME_RE = re.compile(
    r"^(\d+)-EROLLGEN-S(\d+)-(\d+)-(\w+)-FinalRoll-Revision(\d+)"
    r"-ENG-(\d+)-WI_page_(\d+)\.pdf$"
)


def parse_filename(filename: str) -> Optional[dict]:
    """Extract metadata from an English PDF filename."""
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    return {
        "year": m.group(1),
        "state_code": m.group(2),
        "ac_no": m.group(3),
        "ac_abbr": m.group(4),
        "revision": m.group(5),
        "part_no": m.group(6),
        "page_no": int(m.group(7)),
        "filename": filename,
    }


def discover_tamil_files(tamil_dir: Path) -> dict[str, dict[int, Path]]:
    """
    Index all Tamil PDF files by (part_no, page_no).
    Returns dict: part_no -> {page_no: Path}
    """
    TAM_RE = re.compile(
        r"^(\d+)-EROLLGEN-S(\d+)-(\d+)-(\w+)-FinalRoll-Revision(\d+)"
        r"-TAM-(\d+)-WI_page_(\d+)\.pdf$"
    )
    index = defaultdict(dict)
    if not tamil_dir.exists():
        return index
    for f in tamil_dir.iterdir():
        if not f.name.endswith(".pdf"):
            continue
        m = TAM_RE.match(f.name)
        if m:
            part_no = m.group(6)
            page_no = int(m.group(7))
            index[part_no][page_no] = f
    return index


def discover_pairs(directory: Path) -> list[dict]:
    """Discover all English PDF files in a directory.

    Tamil matching is done later at processing time using EPIC ID matching,
    since page number offsets between English and Tamil vary by part.
    We still store all Tamil files indexed by part for efficient lookup.
    """
    eng_dir = directory / "english"
    tam_dir = directory / "tamil"

    if not eng_dir.exists():
        log.error(f"English directory not found: {eng_dir}")
        return []

    # Index all Tamil files
    tamil_index = discover_tamil_files(tam_dir)

    pairs = []
    for f in sorted(eng_dir.iterdir()):
        if not f.name.endswith(".pdf"):
            continue
        meta = parse_filename(f.name)
        if meta is None:
            log.warning(f"Skipping unrecognized filename: {f.name}")
            continue

        # Collect all Tamil pages for this part (for later EPIC matching)
        tamil_pages = tamil_index.get(meta["part_no"], {})

        pairs.append({
            "english_path": str(f),
            "tamil_pages": {pg: str(p) for pg, p in tamil_pages.items()},
            "ac_no": meta["ac_no"],
            "part_no": meta["part_no"],
            "page_no": meta["page_no"],
            "key": f.name,
        })

    return pairs


# ----- Checkpoint -----

def _checkpoint_path(dir_name: str) -> Path:
    """Return checkpoint file path for a batch directory (stored under ocr/checkpoints/)."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / f"{dir_name}.json"


def load_checkpoint(dir_name: str) -> dict:
    """Load checkpoint data for a batch directory."""
    cp_file = _checkpoint_path(dir_name)
    if cp_file.exists():
        with open(cp_file, "r") as f:
            return json.load(f)
    return {"processed": [], "batch_number": 0}


def save_checkpoint(dir_name: str, data: dict):
    """Save checkpoint data for a batch directory."""
    cp_file = _checkpoint_path(dir_name)
    with open(cp_file, "w") as f:
        json.dump(data, f, indent=2)


# ----- Image Extraction -----

def extract_image_from_pdf(pdf_path: str) -> np.ndarray:
    """Extract the embedded PNG image from a single-page PDF."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        images = page.get_images(full=True)
        if not images:
            raise ValueError(f"No images found in {pdf_path}")
        xref = images[0][0]
        img_data = doc.extract_image(xref)
        img_bytes = img_data["image"]
        img_pil = Image.open(io.BytesIO(img_bytes))
        return np.array(img_pil)
    finally:
        doc.close()


# ----- Image Preprocessing -----

def preprocess_for_ocr(gray: np.ndarray, use_adaptive: bool = True) -> np.ndarray:
    """
    Preprocess a grayscale image for better OCR accuracy.
    Applies CLAHE contrast enhancement, noise removal, and adaptive thresholding.
    """
    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Noise removal
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)

    if use_adaptive:
        # Adaptive thresholding handles uneven lighting/scanning
        thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 10
        )
    else:
        _, thresh = cv2.threshold(denoised, 150, 255, cv2.THRESH_BINARY)

    return thresh


# ----- Grid Detection -----

def detect_grid(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """
    Detect voter entry cell boundaries in the electoral roll page.

    Returns list of (x1, y1, x2, y2) tuples for each cell,
    ordered left-to-right, top-to-bottom (col-major within each row).
    """
    h, w = image.shape[:2]

    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image.copy()

    # Binary threshold
    _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)

    # Multi-scale horizontal line detection — try decreasing kernel widths
    h_groups = []
    for kernel_width in [w // 4, w // 6, w // 8, w // 12]:
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        h_proj = np.sum(h_lines, axis=1)
        h_positions = np.where(h_proj > w * 0.3 * 255)[0]
        h_groups = _group_positions(h_positions, min_gap=15)
        if len(h_groups) >= 2:
            break

    # If morphological detection failed, try Hough Line Transform
    if len(h_groups) < 2:
        h_groups = _detect_lines_hough(binary, h, w, direction="horizontal")

    if len(h_groups) < 2:
        log.warning("Grid detection failed: not enough horizontal lines")
        # Try contour-based detection before proportional fallback
        contour_cells = _detect_grid_contours(binary, h, w)
        if contour_cells:
            return contour_cells
        return _fallback_grid(h, w)

    # Detect vertical lines for column boundary validation
    v_groups = []
    for kernel_height in [h // 4, h // 6, h // 8]:
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_height))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        v_proj = np.sum(v_lines, axis=0)
        v_positions = np.where(v_proj > h * 0.2 * 255)[0]
        v_groups = _group_positions(v_positions, min_gap=15)
        if len(v_groups) >= 2:
            break

    # Determine column boundaries
    col_boundaries = _detect_column_boundaries(binary, h_groups)

    # If vertical lines detected, use them to validate/replace column boundaries
    if len(v_groups) >= 4:
        # Vertical lines give us direct column boundaries
        col_boundaries = _validate_column_boundaries(v_groups, w)
    elif len(col_boundaries) < 2:
        # Fallback: assume 3 equal columns
        col_boundaries = [
            int(w * 0.02),  # left margin
            int(w * 0.34),
            int(w * 0.66),
            int(w * 0.98),  # right margin
        ]

    # Validate: electoral rolls always have 3 data columns (4 boundaries)
    col_boundaries = _enforce_three_columns(col_boundaries, w)

    # Build cell list
    cells = []
    for row_idx in range(len(h_groups) - 1):
        y1 = h_groups[row_idx]
        y2 = h_groups[row_idx + 1]
        for col_idx in range(len(col_boundaries) - 1):
            x1 = col_boundaries[col_idx]
            x2 = col_boundaries[col_idx + 1]
            cells.append((x1, y1, x2, y2))

    return cells


def _detect_lines_hough(binary: np.ndarray, h: int, w: int, direction: str = "horizontal") -> list[int]:
    """Detect line positions using Hough Line Transform (catches lines with gaps)."""
    lines = cv2.HoughLinesP(binary, 1, np.pi / 180, threshold=100,
                            minLineLength=w // 6 if direction == "horizontal" else h // 6,
                            maxLineGap=20)
    if lines is None:
        return []

    positions = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if direction == "horizontal":
            # Horizontal lines: small y difference, large x span
            if abs(y2 - y1) < 10 and abs(x2 - x1) > w * 0.2:
                positions.append((y1 + y2) // 2)
        else:
            # Vertical lines: small x difference, large y span
            if abs(x2 - x1) < 10 and abs(y2 - y1) > h * 0.2:
                positions.append((x1 + x2) // 2)

    if not positions:
        return []

    return _group_positions(np.array(sorted(positions)), min_gap=15)


def _detect_grid_contours(binary: np.ndarray, h: int, w: int) -> list[tuple[int, int, int, int]]:
    """Detect grid cells using contour detection as fallback."""
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Expected cell size
    expected_area = (w / 3) * (h / 10)
    min_area = expected_area * 0.3
    max_area = expected_area * 2.5

    cells = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cw * ch
        aspect = cw / ch if ch > 0 else 0

        if min_area < area < max_area and 0.5 < aspect < 4.0:
            cells.append((x, y, x + cw, y + ch))

    if len(cells) < 5:
        return []

    # Sort by y then x (row-major order)
    cells.sort(key=lambda c: (c[1], c[0]))
    return cells


def _validate_column_boundaries(v_groups: list[int], w: int) -> list[int]:
    """Use detected vertical lines to determine column boundaries."""
    # Filter to boundaries that span a reasonable portion of the page width
    # Expect: left margin, col1/col2 border, col2/col3 border, right margin
    if len(v_groups) >= 4:
        # Take the leftmost, rightmost, and 2 middle ones
        boundaries = [v_groups[0]]
        inner = v_groups[1:-1]
        if len(inner) >= 2:
            # Take the two that best split into thirds
            third = w / 3
            best_pair = None
            best_score = float("inf")
            for i in range(len(inner)):
                for j in range(i + 1, len(inner)):
                    score = abs(inner[i] - third) + abs(inner[j] - 2 * third)
                    if score < best_score:
                        best_score = score
                        best_pair = (inner[i], inner[j])
            if best_pair:
                boundaries.extend(best_pair)
        elif len(inner) == 1:
            boundaries.append(inner[0])
        boundaries.append(v_groups[-1])
        return sorted(boundaries)
    return []


def _enforce_three_columns(boundaries: list[int], w: int) -> list[int]:
    """Ensure exactly 4 boundaries (3 columns) for electoral roll pages."""
    if len(boundaries) == 4:
        return boundaries
    if len(boundaries) > 4:
        # Merge closest pair until we have 4
        while len(boundaries) > 4:
            min_gap = float("inf")
            merge_idx = 0
            for i in range(len(boundaries) - 1):
                gap = boundaries[i + 1] - boundaries[i]
                if gap < min_gap:
                    min_gap = gap
                    merge_idx = i
            merged = (boundaries[merge_idx] + boundaries[merge_idx + 1]) // 2
            boundaries = boundaries[:merge_idx] + [merged] + boundaries[merge_idx + 2:]
        return boundaries
    if len(boundaries) < 4 and len(boundaries) >= 2:
        # Split widest span until we have 4
        while len(boundaries) < 4:
            max_gap = 0
            split_idx = 0
            for i in range(len(boundaries) - 1):
                gap = boundaries[i + 1] - boundaries[i]
                if gap > max_gap:
                    max_gap = gap
                    split_idx = i
            mid = (boundaries[split_idx] + boundaries[split_idx + 1]) // 2
            boundaries = boundaries[:split_idx + 1] + [mid] + boundaries[split_idx + 1:]
        return boundaries
    # Not enough data — use default proportional
    return [int(w * 0.02), int(w * 0.34), int(w * 0.66), int(w * 0.98)]


def _detect_column_boundaries(binary: np.ndarray, h_groups: list[int]) -> list[int]:
    """Detect column boundaries by analyzing vertical density in the data rows."""
    h, w = binary.shape

    # Use the middle rows for analysis (avoid header/footer)
    if len(h_groups) >= 3:
        y_start = h_groups[1]
        y_end = h_groups[-2]
    else:
        y_start = h_groups[0]
        y_end = h_groups[-1]

    row_slice = binary[y_start:y_end, :]
    col_density = np.sum(row_slice, axis=0) / 255

    # Find low-density gaps (column separators)
    # Look for regions where density drops near zero
    threshold = 10
    gaps = []
    in_gap = False
    gap_start = 0

    for x in range(w):
        if col_density[x] < threshold:
            if not in_gap:
                gap_start = x
                in_gap = True
        else:
            if in_gap:
                gap_end = x
                gap_width = gap_end - gap_start
                if gap_width >= 3:
                    gaps.append((gap_start, gap_end))
                in_gap = False

    if in_gap:
        gaps.append((gap_start, w))

    if len(gaps) < 2:
        return []

    # First gap is left margin, last gap is right margin
    # Gaps in between are column separators
    boundaries = []
    boundaries.append(gaps[0][1])  # right edge of left margin = start of col 1

    for g in gaps[1:-1]:
        mid = (g[0] + g[1]) // 2
        boundaries.append(mid)

    boundaries.append(gaps[-1][0])  # left edge of right margin = end of last col

    return boundaries


def _group_positions(positions: np.ndarray, min_gap: int = 15) -> list[int]:
    """Group nearby pixel positions into single line positions."""
    if len(positions) == 0:
        return []
    groups = []
    current = [positions[0]]
    for p in positions[1:]:
        if p - current[-1] <= min_gap:
            current.append(p)
        else:
            groups.append(int(np.mean(current)))
            current = [p]
    groups.append(int(np.mean(current)))
    return groups


def _fallback_grid(h: int, w: int) -> list[tuple[int, int, int, int]]:
    """Fallback: return proportionally-split 3x10 grid."""
    margin_x = int(w * 0.02)
    margin_top = int(h * 0.033)
    margin_bottom = int(h * 0.03)
    content_w = w - 2 * margin_x
    content_h = h - margin_top - margin_bottom
    col_w = content_w // 3
    row_h = content_h // 10

    cells = []
    for row in range(10):
        y1 = margin_top + row * row_h
        y2 = y1 + row_h
        for col in range(3):
            x1 = margin_x + col * col_w
            x2 = x1 + col_w
            cells.append((x1, y1, x2, y2))
    return cells


# ----- OCR -----

def ocr_serial_targeted(cell_img: np.ndarray) -> str:
    """
    Targeted serial number extraction from the top-left corner of a cell.
    Serial numbers appear in a small bordered box at the top-left.
    Uses character whitelist for digits only.
    """
    h, w = cell_img.shape[:2]
    # Serial number box is in the top-left ~25% height, ~20% width of the cell
    roi = cell_img[0:int(h * 0.25), 0:int(w * 0.20)]

    scale = 4
    upscaled = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    if len(upscaled.shape) == 3:
        gray = cv2.cvtColor(upscaled, cv2.COLOR_RGB2GRAY)
    else:
        gray = upscaled

    # Use fixed threshold for the small serial box (adaptive can over-segment small regions)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    config = "--psm 7 --oem 1 --dpi 300 -c tessedit_char_whitelist=0123456789#"
    text = pytesseract.image_to_string(thresh, lang="eng", config=config).strip()

    # Extract digits
    m = re.search(r"(\d{1,4})", text)
    if m:
        return m.group(1)
    return ""


def ocr_cell_english(cell_img: np.ndarray) -> dict:
    """OCR a single cell from the English PDF and parse fields."""
    # Upscale 4x with Lanczos for sharper text
    scale = 4
    upscaled = cv2.resize(cell_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    # Convert to grayscale if needed
    if len(upscaled.shape) == 3:
        gray = cv2.cvtColor(upscaled, cv2.COLOR_RGB2GRAY)
    else:
        gray = upscaled

    # Preprocessed thresholding (adaptive + CLAHE + denoising)
    thresh = preprocess_for_ocr(gray)

    # OCR with PSM 4 (single column of text) — handles the serial number box + text layout
    # better than PSM 6 which treats it as one flat block
    text = pytesseract.image_to_string(thresh, lang="eng", config="--psm 4 --oem 1 --dpi 300")

    return parse_english_text(text)


def ocr_cell_tamil(cell_img: np.ndarray) -> dict:
    """OCR a single cell from the Tamil PDF and extract Tamil names."""
    h, w = cell_img.shape[:2]
    # Crop out bottom 15% to avoid age/gender/house labels contaminating name extraction
    # (reduced from 20% — Tamil names sometimes extend further down)
    cropped = cell_img[0:int(h * 0.85), :]

    scale = 4
    upscaled = cv2.resize(cropped, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    if len(upscaled.shape) == 3:
        gray = cv2.cvtColor(upscaled, cv2.COLOR_RGB2GRAY)
    else:
        gray = upscaled

    thresh = preprocess_for_ocr(gray)

    text = pytesseract.image_to_string(thresh, lang="tam+eng", config="--psm 6 --oem 1 --dpi 300")

    return parse_tamil_text(text)


def ocr_epic_id_targeted(cell_img: np.ndarray) -> Optional[str]:
    """
    Targeted EPIC ID extraction from the top-right area of a cell.
    Uses character allowlist for better accuracy.
    """
    h, w = cell_img.shape[:2]
    # EPIC ID is in the top-right portion of the cell
    roi = cell_img[0:int(h * 0.3), int(w * 0.4):]

    scale = 4
    upscaled = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    if len(upscaled.shape) == 3:
        gray = cv2.cvtColor(upscaled, cv2.COLOR_RGB2GRAY)
    else:
        gray = upscaled

    thresh = preprocess_for_ocr(gray)

    config = "--psm 7 --oem 1 --dpi 300 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    text = pytesseract.image_to_string(thresh, lang="eng", config=config).strip()

    epic_id = fix_epic_id(text)
    if epic_id and re.match(r"^[A-Z]{3}\d{7}$", epic_id):
        return epic_id
    return None


# ----- Text Parsing -----

# Regex patterns with fuzzy label matching for OCR errors
# Serial can be preceded by OCR artifacts like =, |, #, etc.
SERIAL_RE = re.compile(r"^[#=|:;\s]*(\d{1,4})\b")
EPIC_RE = re.compile(r"([A-Z]{2,4}\s?\d{6,8})")
NAME_RE = re.compile(r"(?:Name|Nama|Nane|Narne)\s*[:.|\-]?\s*(.+?)(?:\s*-\s*)?$", re.IGNORECASE)
RELATION_RE = re.compile(
    r"(Father|Husband|Mother|Other|Falher|Fathor|Fatner|Fath|Husb|Othor)['\s]*(?:s\s*)?(?:Name|Nama|Nane|Narne)?\s*[:.|\-]?\s*(.+?)(?:\s*-\s*)?$",
    re.IGNORECASE,
)
# Fallback: matches lines like "Name: Boominathan" that appear after relation type line
RELATION_NAME_ONLY_RE = re.compile(
    r"^(?:Name|Nama|Nane|Narne)\s*[:.|\-]?\s*(.+?)(?:\s*-\s*)?$",
    re.IGNORECASE,
)
HOUSE_RE = re.compile(
    r"(?:House|Housc|Hovse|Houso)\s*(?:Number|Numbe|Numoor|Numb|No)\s*[:.|\-]?\s*(.+?)$",
    re.IGNORECASE,
)
AGE_GENDER_RE = re.compile(
    r"(?:Age|Ago|Aga)\s*[:.=|\-]?\s*(\d{2,3})\s*(?:Gender|Gend|Gencer|Gander|Gerder)\s*[:.=|\-]?\s*(Male|Female|Ma\w*|Fe\w*)",
    re.IGNORECASE,
)
AGE_RE = re.compile(r"(?:Age|Ago)\s*[:.=|\-]?\s*(\d{2,3})", re.IGNORECASE)
GENDER_RE = re.compile(r"(?:Gender|Gend|Gerder)\s*[:.=|\-]?\s*(Male|Female|Ma\w*|Fe\w*)", re.IGNORECASE)

# Tamil patterns
TAMIL_NAME_RE = re.compile(r"(?:பெயர்)\s*[:.\-]?\s*(.+?)(?:\s*-\s*)?$")
TAMIL_RELATION_RE = re.compile(
    r"(?:தந்தையின்|கணவரின்|கணவர்|தாயின்)\s*(?:பெயர்)?\s*[:.|\-]?\s*(.+?)(?:\s*-\s*)?$"
)
# Tamil form label noise that can contaminate name fields
TAMIL_LABEL_NOISE_RE = re.compile(
    r"\d+\s*பாலினம்\s*:\s*(?:ஆண்|பெண்)"     # "28 பாலினம் : ஆண்" = Age + Gender label
    r"|பாலினம்\s*:\s*(?:ஆண்|பெண்)"            # "பாலினம் : ஆண்" = Gender label alone
    r"|வயது\s*[:：]\s*\d+"                      # "வயது : 28" = Age label
    r"|வீட்டு\s*எண்"                            # "வீட்டு எண்" = House Number label
    r"|புகைப்படம்"                               # "புகைப்படம்" = Photo label
)


def parse_english_text(text: str) -> dict:
    """Parse OCR text from an English cell into structured fields."""
    result = {
        "serial_no": "",
        "epic_id": "",
        "name_english": "",
        "relation_name_english": "",
        "relation_type": "",
        "house_no": "",
        "age": "",
        "gender": "",
    }

    # Clean lines: strip artifacts like "Photo", "Available", "Photo Available"
    lines = []
    for l in text.split("\n"):
        l = l.strip()
        if not l:
            continue
        # Skip pure artifact lines
        l_lower = l.lower()
        if l_lower in ("available", "photo", "photo available", "photo is available"):
            continue
        # Remove trailing "Photo" / "Available" from data lines
        l = re.sub(r"\s*Photo\s*$", "", l, flags=re.IGNORECASE).strip()
        l = re.sub(r"\s*Available\s*$", "", l, flags=re.IGNORECASE).strip()
        if l:
            lines.append(l)

    if not lines:
        return result

    # First 2 lines may have serial number and/or EPIC ID (e.g., "211 RVJ1612993")
    for check_line in lines[:2]:
        serial_match = SERIAL_RE.search(check_line)
        if serial_match:
            result["serial_no"] = serial_match.group(1)
            break

    # Look for EPIC ID in all lines (can appear on first line, or separate line)
    for line in lines:
        epic_match = EPIC_RE.search(line)
        if epic_match:
            candidate = fix_epic_id(epic_match.group(1))
            if re.match(r"^[A-Z]{3}\d{7}$", candidate):
                result["epic_id"] = candidate
                break

    # If no valid EPIC found, try with looser matching
    if not result["epic_id"]:
        for line in lines[:4]:
            epic_match = EPIC_RE.search(line)
            if epic_match:
                result["epic_id"] = fix_epic_id(epic_match.group(1))
                break

    # Parse remaining fields from all lines
    found_name = False
    found_relation_type = False
    for line in lines:
        # Name (must come before relation to avoid confusion)
        if not found_name:
            name_match = NAME_RE.search(line)
            if name_match and not RELATION_RE.search(line):
                result["name_english"] = clean_name(name_match.group(1))
                found_name = True
                continue

        # Relation (e.g., "Father Name: Meyyappan -" or "Husband Name: Ganesan")
        rel_match = RELATION_RE.search(line)
        if rel_match:
            result["relation_type"] = normalize_relation_type(rel_match.group(1))
            rel_name = clean_name(rel_match.group(2))
            # Strip any "Name:" prefix that leaked into the captured value
            rel_name = re.sub(r"^(?:Name|Nama|Nane|Narne)\s*[:.|\-]?\s*", "", rel_name, flags=re.IGNORECASE)
            result["relation_name_english"] = rel_name.strip()
            found_relation_type = True
            continue

        # Standalone relation type line (e.g., just "Father" or "Husband" on its own)
        if found_name and not result["relation_type"]:
            line_stripped = line.strip().rstrip("'s").strip()
            if re.match(r"^(Father|Husband|Mother|Other)(\s|$)", line_stripped, re.IGNORECASE):
                result["relation_type"] = normalize_relation_type(line_stripped.split()[0])
                found_relation_type = True
                continue

        # Fallback: line with just "Name: <value>" after we already found the voter name
        # This happens when OCR splits "Father Name:" across lines, producing:
        #   Line N: "Father" (or relation type alone)
        #   Line N+1: "Name: Boominathan"
        if found_name and not result["relation_name_english"]:
            rel_name_match = RELATION_NAME_ONLY_RE.search(line)
            if rel_name_match:
                result["relation_name_english"] = clean_name(rel_name_match.group(1))
                continue

        # House number
        house_match = HOUSE_RE.search(line)
        if house_match:
            house_val = house_match.group(1).strip()
            # Remove trailing "Photo" artifacts
            house_val = re.sub(r"\s*Photo.*$", "", house_val, flags=re.IGNORECASE).strip()
            # Remove location name suffixes (e.g., "20 Saraswathi Vasagasala")
            house_val = re.sub(r"\s+[A-Z][a-z]{2,}.*$", "", house_val)
            # Truncate overly long values (house numbers should be short)
            if len(house_val) > 15:
                house_val = house_val.split()[0] if house_val.split() else house_val
            # Apply systematic cleanup: confusable mapping + whitelist
            result["house_no"] = clean_house_no(house_val)
            continue

        # Age and Gender (often on same line)
        ag_match = AGE_GENDER_RE.search(line)
        if ag_match:
            age_val = ag_match.group(1)
            try:
                if 18 <= int(age_val) <= 120:
                    result["age"] = age_val
            except ValueError:
                pass
            result["gender"] = normalize_gender(ag_match.group(2))
            continue

        # Age alone
        if not result["age"]:
            age_match = AGE_RE.search(line)
            if age_match:
                age_val = age_match.group(1)
                try:
                    if 18 <= int(age_val) <= 120:
                        result["age"] = age_val
                except ValueError:
                    pass

        # Gender alone
        if not result["gender"]:
            gender_match = GENDER_RE.search(line)
            if gender_match:
                result["gender"] = normalize_gender(gender_match.group(1))

    # Last-resort age extraction: if we have gender but no age, scan all lines
    # for a bare 2-3 digit number in the valid range (18-120).
    # OCR sometimes drops the "Age:" label but still captures the number.
    if not result["age"]:
        for line in lines:
            # Skip lines already parsed as name/relation/house/EPIC
            if any(kw in line.lower() for kw in ["name", "house", "father", "husband", "mother"]):
                continue
            # Look for bare numbers that could be age
            for m in re.finditer(r"\b(\d{2,3})\b", line):
                try:
                    val = int(m.group(1))
                    if 18 <= val <= 120:
                        result["age"] = m.group(1)
                        break
                except ValueError:
                    pass
            if result["age"]:
                break

    return result


def _clean_tamil_text(text: str) -> str:
    """Clean Tamil OCR text: remove zero-width chars, label prefixes, trailing dashes, label noise."""
    # Remove zero-width non-joiner and similar invisible chars
    text = text.replace("\u200c", "").replace("\u200d", "").replace("\u200b", "")
    # Remove Tamil label prefixes that leak into the value
    text = re.sub(r"^.*பெயர்\s*[:：]?\s*", "", text)
    text = re.sub(r"^[\s:.\-|]+", "", text)
    text = text.strip().rstrip("-").strip()
    # Filter out form label noise (e.g., "28 பாலினம் : ஆண்" = Age+Gender)
    if TAMIL_LABEL_NOISE_RE.search(text):
        return ""
    return text


def parse_tamil_text(text: str) -> dict:
    """Parse OCR text from a Tamil cell to extract Tamil names."""
    result = {
        "serial_no": "",
        "name_tamil": "",
        "relation_name_tamil": "",
    }

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return result

    # Serial number from first line
    serial_match = SERIAL_RE.search(lines[0])
    if serial_match:
        result["serial_no"] = serial_match.group(1)

    for line in lines:
        # Skip non-data lines
        l_lower = line.lower()
        if any(skip in l_lower for skip in ["available", "photo"]):
            continue

        # Tamil name: line containing பெயர் (name) but NOT தந்தையின்/கணவரின்/தாயின் (relation)
        name_match = TAMIL_NAME_RE.search(line)
        if name_match and not result["name_tamil"]:
            if not TAMIL_RELATION_RE.search(line):
                result["name_tamil"] = _clean_tamil_text(name_match.group(1))
                continue

        # Tamil relation name
        rel_match = TAMIL_RELATION_RE.search(line)
        if rel_match:
            result["relation_name_tamil"] = _clean_tamil_text(rel_match.group(1))
            continue

    # If regex didn't match, try positional extraction:
    # In Tamil cells, line 2 is typically name, line 3 is relation
    if not result["name_tamil"] and len(lines) >= 2:
        for line in lines[1:]:
            if any(skip in line.lower() for skip in ["available", "photo"]):
                continue
            # Look for lines with Tamil characters and colon separator
            colon_match = re.search(r"[:：]\s*(.+?)(?:\s*-\s*)?$", line)
            if colon_match:
                value = _clean_tamil_text(colon_match.group(1))
                # Check if it has Tamil chars (Unicode range 0B80-0BFF)
                if any("\u0B80" <= c <= "\u0BFF" for c in value):
                    if not result["name_tamil"]:
                        # Remove label prefix like "பெயர்" if present
                        value = re.sub(r"^.*பெயர்\s*[:：]?\s*", "", value).strip()
                        if value:
                            result["name_tamil"] = value
                    elif not result["relation_name_tamil"]:
                        value = re.sub(r"^.*பெயர்\s*[:：]?\s*", "", value).strip()
                        if value:
                            result["relation_name_tamil"] = value

    return result


# Known valid EPIC ID prefixes for AC 184
KNOWN_EPIC_PREFIXES = {"RVJ", "MDJ", "IOD", "JOD"}


def fix_epic_id(raw: str) -> str:
    """Post-process EPIC ID: fix common OCR errors like O→0 in digit positions."""
    # Remove spaces within EPIC ID (OCR sometimes adds them)
    raw = raw.replace(" ", "").strip()
    if len(raw) < 10:
        return raw

    # Take first 10 chars
    raw = raw[:10]

    # Fix digit positions (3-9): letters → digits
    digit_fixes = {"O": "0", "I": "1", "l": "1", "S": "5", "B": "8",
                   "G": "6", "Z": "2", "D": "0", "T": "7", "q": "9"}
    chars = list(raw)
    for i in range(3, 10):
        if i < len(chars) and chars[i] in digit_fixes:
            chars[i] = digit_fixes[chars[i]]

    # Fix letter positions (0-2): digits → letters
    letter_fixes = {"0": "O", "1": "I", "5": "S", "8": "B", "6": "G"}
    for i in range(3):
        if i < len(chars) and chars[i] in letter_fixes:
            chars[i] = letter_fixes[chars[i]]

    result = "".join(chars)

    # Try to correct prefix using known valid prefixes (Levenshtein distance 1)
    prefix = result[:3]
    if prefix not in KNOWN_EPIC_PREFIXES:
        best_match = None
        best_dist = 2  # Only correct if distance <= 1
        for known in KNOWN_EPIC_PREFIXES:
            dist = sum(a != b for a, b in zip(prefix, known))
            if dist < best_dist:
                best_dist = dist
                best_match = known
        if best_match:
            result = best_match + result[3:]

    return result


def clean_name(name: str) -> str:
    """Clean up an extracted name.

    Uses a whitelist approach: only actual letters (any script), spaces, periods,
    hyphens, and apostrophes are valid in names. Everything else is stripped.
    Uses unicodedata to distinguish real letters from symbols like «, ¢, °, ©.
    """
    # Strip "Name:" prefix that leaks from relation label splitting
    name = re.sub(r"^(?:Name|Nama|Nane|Narne)\s*[:.|\-]?\s*", "", name, flags=re.IGNORECASE)
    # Whitelist: keep only characters that are Unicode letters (category L*),
    # spaces, periods, hyphens, and apostrophes. This excludes symbols (S*),
    # punctuation (P*), digits (N*), and other non-letter categories.
    cleaned = []
    for ch in name:
        cat = unicodedata.category(ch)
        if cat.startswith("L"):       # Any letter (Latin, Tamil, etc.)
            cleaned.append(ch)
        elif ch in " .-'":            # Allowed punctuation in names
            cleaned.append(ch)
        elif cat == "Zs":             # Any Unicode space
            cleaned.append(" ")
        # Everything else (symbols, digits, punctuation) is dropped
    name = "".join(cleaned)
    # Collapse multiple spaces
    name = re.sub(r"\s{2,}", " ", name)
    # Remove leading/trailing punctuation and whitespace
    name = name.strip(" .-'")
    return name


# OCR frequently confuses visually similar Unicode symbols with ASCII characters.
# For house numbers (which are mostly digits + occasional letters like A, B, C),
# we map symbols to the digit or letter they most resemble in that context.
_HOUSE_NO_CONFUSABLES = {
    # Digit-like symbols (most house number chars are digits)
    '§': '5', '$': '5',           # § and $ look like 5 in digit context
    '°': '', 'º': '',             # degree sign -> strip (noise)
    '|': '1', '¡': '1', '¦': '1',  # pipe/inverted-! -> 1
    '²': '2', '³': '3',
    # Letter-like symbols (for house sub-parts like "64A", "83C")
    '¢': 'C', '©': 'C', '€': 'C',  # C-like
    '®': 'R',
    '@': 'A',
    # Pure noise -> strip
    '~': '', '`': '', '™': '',
    '«': '', '»': '',
    '>': '', '<': '',
}


def clean_house_no(raw: str) -> str:
    """Clean a house number using Unicode confusable mapping + whitelist.

    House numbers contain: digits, letters (A-Z for sub-parts), hyphens, slashes,
    parentheses. Anything else is an OCR artifact that should be mapped to its
    visually similar ASCII equivalent or stripped.
    """
    # Step 1: Unicode NFKC normalization (maps compatibility chars to canonical forms)
    raw = unicodedata.normalize("NFKC", raw)

    # Step 2: Apply confusable mapping for chars that survive normalization
    result = []
    for ch in raw:
        if ch in _HOUSE_NO_CONFUSABLES:
            result.append(_HOUSE_NO_CONFUSABLES[ch])
        else:
            result.append(ch)
    raw = "".join(result)

    # Step 3: Whitelist — keep only digits, letters, hyphens, slashes, parens, spaces
    raw = re.sub(r"[^a-zA-Z0-9\-/() ]", "", raw)

    # Step 4: Clean up spacing and formatting
    raw = re.sub(r"\s{2,}", " ", raw).strip()
    raw = raw.strip("-/ ")

    # Step 5: Fix common OCR letter-for-digit confusion in leading position
    # House numbers start with digits. A leading single letter before digits/space
    # is likely a misread digit (e.g., "S8" should be "58", "C 92" should be "92").
    # But letters AFTER digits are valid sub-parts (e.g., "83C", "64A").
    m = re.match(r"^([A-Za-z])\s*(\d.*)$", raw)
    if m:
        letter, rest = m.group(1), m.group(2)
        # Common OCR digit-for-letter misreads at start of house number
        leading_letter_to_digit = {
            'S': '5', 's': '5', 'O': '0', 'o': '0', 'I': '1', 'l': '1',
            'B': '8', 'G': '6', 'g': '6', 'Z': '2', 'z': '2', 'T': '7',
            'C': 'C',  # C could be valid if followed by space (noise prefix)
        }
        replacement = leading_letter_to_digit.get(letter.upper())
        if replacement and replacement != letter.upper():
            raw = replacement + rest
        elif letter.upper() == 'C':
            # "C 92" -> "92" (C is noise prefix); but "C3" might be valid
            if rest and rest[0] == ' ':
                raw = rest.strip()

    return raw


def normalize_relation_type(raw: str) -> str:
    """Normalize relation type from OCR text."""
    raw_lower = raw.lower().strip()
    if raw_lower.startswith("fat") or raw_lower.startswith("fal"):
        return "Father"
    elif raw_lower.startswith("hus"):
        return "Husband"
    elif raw_lower.startswith("moth"):
        return "Mother"
    return raw.strip().title()


def normalize_gender(raw: str) -> str:
    """Normalize gender from OCR text."""
    raw_lower = raw.lower().strip()
    if raw_lower.startswith("ma"):
        return "Male"
    elif raw_lower.startswith("fe"):
        return "Female"
    return raw.strip()


# ----- Page Processing -----

def _infer_serial_numbers(records: list[dict], page_base_serial: int = 0):
    """
    Infer missing serial numbers from surrounding records.
    Electoral rolls have sequential serial numbers (e.g., 211, 212, 213, ...).
    Records are in cell order (left-to-right, top-to-bottom).

    Args:
        records: list of record dicts
        page_base_serial: expected first serial number on this page
                          (calculated from page position in part)
    """
    if not records:
        return

    # First pass: convert existing serials to int
    for rec in records:
        try:
            rec["_serial_int"] = int(rec["serial_no"]) if rec["serial_no"] else None
        except ValueError:
            rec["_serial_int"] = None

    # Find records with known serials to establish the sequence
    known = [(i, rec["_serial_int"]) for i, rec in enumerate(records) if rec["_serial_int"] is not None]

    if not known:
        # No serials detected at all — leave blank rather than guessing wrong.
        # They may be filled later from Tamil page cross-validation.
        for rec in records:
            rec.pop("_serial_int", None)
        return

    # For each record with missing serial, interpolate from neighbors
    for i, rec in enumerate(records):
        if rec["_serial_int"] is not None:
            continue

        # Find nearest known before and after
        before = None
        after = None
        for ki, kval in known:
            if ki < i:
                before = (ki, kval)
            elif ki > i and after is None:
                after = (ki, kval)
                break

        if before is not None:
            # Infer: serial = before_serial + (position_diff)
            inferred = before[1] + (i - before[0])
            rec["serial_no"] = str(inferred)
            rec["_serial_int"] = inferred
        elif after is not None:
            inferred = after[1] - (after[0] - i)
            rec["serial_no"] = str(inferred)
            rec["_serial_int"] = inferred

    # Cleanup
    for rec in records:
        rec.pop("_serial_int", None)


def _dedup_serial_numbers(records: list[dict]):
    """
    Fix duplicate serial numbers. Electoral rolls have strictly sequential serials.
    When two records share the same serial, one of them has a misread serial.

    Strategy: find gaps in the sequence (missing serials) and match them to
    duplicates. The duplicate record closest to the gap position gets reassigned.
    If no gap is found, clear the second occurrence and re-infer.
    """
    if len(records) < 2:
        return

    # Build serial -> list of record indices
    serial_indices = defaultdict(list)
    for i, rec in enumerate(records):
        s = rec.get("serial_no", "")
        if s:
            serial_indices[s].append(i)

    # Find duplicates (serials appearing more than once)
    dup_serials = {s: idxs for s, idxs in serial_indices.items() if len(idxs) > 1}
    if not dup_serials:
        return

    # Find gaps in the expected sequence
    all_serials = sorted(int(s) for s in serial_indices if s)
    if len(all_serials) < 2:
        return
    expected = set(range(all_serials[0], all_serials[-1] + 1))
    actual = set(all_serials)
    gaps = sorted(expected - actual)

    # Match each gap to the nearest duplicate
    for dup_serial_str, idxs in dup_serials.items():
        dup_val = int(dup_serial_str)
        if gaps:
            # Find the gap closest to this duplicate's value
            best_gap = min(gaps, key=lambda g: abs(g - dup_val))
            # Assign the gap to the duplicate occurrence whose position is
            # closest to where the gap should be in the record sequence
            # (gaps appear where a record is "missing" in position order)
            gap_expected_pos = best_gap - all_serials[0]  # approximate index
            best_idx = min(idxs, key=lambda i: abs(i - gap_expected_pos))
            old = records[best_idx]["serial_no"]
            records[best_idx]["serial_no"] = str(best_gap)
            gaps.remove(best_gap)
            log.info(f"Reassigned duplicate serial {old} -> {best_gap} at index {best_idx}")
        else:
            # No gap to fill — clear the last duplicate and re-infer
            for idx in idxs[1:]:
                old = records[idx]["serial_no"]
                records[idx]["serial_no"] = ""
                log.info(f"Cleared duplicate serial {old} at index {idx}")
            _infer_serial_numbers(records)


def _filter_stray_records(records: list[dict]) -> list[dict]:
    """
    Correct stray records whose serial numbers are far outside the page's range.
    Each page has ~30 sequential records. If a serial is far from the median,
    it's likely an OCR misread (e.g., 253 -> 203). Instead of removing the record,
    we clear the serial so _infer_serial_numbers can re-derive it from neighbors,
    or we attempt digit-level correction when possible.
    """
    if len(records) < 3:
        return records

    serials = []
    for r in records:
        try:
            if r.get("serial_no"):
                serials.append(int(r["serial_no"]))
        except ValueError:
            pass

    if len(serials) < 3:
        return records

    sorted_serials = sorted(serials)
    median_serial = sorted_serials[len(sorted_serials) // 2]
    # Determine the expected range from the majority of records
    min_expected = median_serial - 35
    max_expected = median_serial + 35

    corrected_any = False
    for r in records:
        try:
            s = int(r.get("serial_no", "0"))
            if s == 0:
                continue
            if abs(s - median_serial) > 35:
                # Try digit-level correction: common OCR misreads
                # e.g., 203 -> 253 (0 misread as 5), 205 -> 255
                original = r["serial_no"]
                corrected = _try_correct_serial(s, min_expected, max_expected)
                if corrected is not None:
                    log.info(f"Corrected stray serial {original} -> {corrected} (median: {median_serial})")
                    r["serial_no"] = str(corrected)
                    corrected_any = True
                else:
                    # Can't correct — clear it so inference can fill it from neighbors
                    log.info(f"Cleared stray serial {original} (too far from median {median_serial})")
                    r["serial_no"] = ""
                    corrected_any = True
        except ValueError:
            pass

    # If we cleared any serials, re-run inference to fill gaps
    if corrected_any:
        _infer_serial_numbers(records)

    return records


def _try_correct_serial(stray: int, min_expected: int, max_expected: int) -> Optional[int]:
    """
    Attempt digit-level correction of a misread serial number.
    Common OCR confusions: 0<->5, 0<->6, 0<->8, 1<->7, 3<->8, 2<->7, etc.
    Returns corrected serial if exactly one substitution puts it in range, else None.
    """
    digit_confusions = {
        '0': ['5', '6', '8', '9'],
        '1': ['7', '4'],
        '2': ['7', '3'],
        '3': ['8', '5'],
        '4': ['1', '9'],
        '5': ['0', '3', '6'],
        '6': ['0', '5', '8'],
        '7': ['1', '2'],
        '8': ['0', '3', '6'],
        '9': ['0', '4'],
    }
    s = str(stray)
    candidates = []
    for i, ch in enumerate(s):
        for replacement in digit_confusions.get(ch, []):
            candidate = int(s[:i] + replacement + s[i+1:])
            if min_expected <= candidate <= max_expected:
                candidates.append(candidate)

    # Only return if there's exactly one plausible correction
    unique = list(set(candidates))
    if len(unique) == 1:
        return unique[0]
    return None


def is_summary_or_legend_page(text: str) -> bool:
    """Check if OCR text indicates a summary or legend page (non-data)."""
    text_upper = text.upper()
    if "SUMMARY OF ELECTORS" in text_upper:
        return True
    if "SUMMARY" in text_upper and "TOTAL" in text_upper:
        return True
    # Tamil legend page
    if "E- Expired" in text or "S- Shifted" in text:
        return True
    if "Expired" in text and "Shifted" in text and "Repeated" in text:
        return True
    return False


def _ocr_tamil_page(tam_path: str) -> dict[str, dict]:
    """
    OCR a Tamil page and return a dict of {epic_id: {name_tamil, relation_name_tamil}}.
    Also returns a dict keyed by serial_no as fallback under "_by_serial" key.
    """
    result_by_epic = {}
    result_by_serial = {}

    try:
        tam_img = extract_image_from_pdf(tam_path)
    except Exception as e:
        log.warning(f"Failed to extract Tamil image {tam_path}: {e}")
        return result_by_epic

    tam_cells = detect_grid(tam_img)
    if not tam_cells:
        return result_by_epic

    for x1, y1, x2, y2 in tam_cells:
        cell_img = tam_img[y1:y2, x1:x2]
        if cell_img.size == 0:
            continue

        # Tamil OCR for names
        tam_data = ocr_cell_tamil(cell_img)

        # EPIC ID extraction using English OCR on full cell
        epic_id = _extract_epic_from_cell(cell_img)

        if epic_id and re.match(r"^[A-Z]{3}\d{7}$", epic_id):
            result_by_epic[epic_id] = {
                "name_tamil": tam_data["name_tamil"],
                "relation_name_tamil": tam_data["relation_name_tamil"],
            }

        if tam_data["serial_no"]:
            result_by_serial[tam_data["serial_no"]] = {
                "name_tamil": tam_data["name_tamil"],
                "relation_name_tamil": tam_data["relation_name_tamil"],
            }

    result_by_epic["_by_serial"] = result_by_serial
    return result_by_epic


def _extract_epic_from_cell(cell_img: np.ndarray) -> str:
    """Extract EPIC ID from a cell image using English OCR (works on both EN and TA pages)."""
    up = cv2.resize(cell_img, None, fx=4, fy=4, interpolation=cv2.INTER_LANCZOS4)
    if len(up.shape) == 3:
        gray = cv2.cvtColor(up, cv2.COLOR_RGB2GRAY)
    else:
        gray = up
    thresh = preprocess_for_ocr(gray)
    text = pytesseract.image_to_string(thresh, lang="eng", config="--psm 6 --oem 1 --dpi 300")
    epic_match = EPIC_RE.search(text)
    if epic_match:
        return fix_epic_id(epic_match.group(1))
    return ""


def _check_tamil_page_match(tam_path: str, eng_epic_ids: set[str]) -> int:
    """Check how many EPIC IDs from a Tamil page match the English page. Returns match count."""
    try:
        tam_img = extract_image_from_pdf(tam_path)
    except Exception:
        return 0

    tam_cells = detect_grid(tam_img)
    if not tam_cells:
        return 0

    match_count = 0
    for x1, y1, x2, y2 in tam_cells[:6]:  # Check first 6 cells
        cell_img = tam_img[y1:y2, x1:x2]
        if cell_img.size == 0:
            continue
        epic = _extract_epic_from_cell(cell_img)
        if epic in eng_epic_ids:
            match_count += 1
        if match_count >= 3:
            return match_count  # Early exit: confirmed match

    return match_count


def _find_tamil_page(eng_page_no: int, eng_epic_ids: set[str], tamil_pages: dict[int, str]) -> Optional[str]:
    """
    Find the Tamil page matching an English page. Tries likely candidates first:
    1. Same page number
    2. Page number + 1 (common offset)
    3. Scan remaining pages if needed
    Uses both EPIC ID matching and relaxed threshold for better pairing.
    """
    if not tamil_pages:
        return None

    # Try likely candidates first (fast path)
    candidates = []
    for offset in [0, 1, -1]:
        pg = eng_page_no + offset
        if pg in tamil_pages:
            candidates.append((pg, tamil_pages[pg]))

    # First pass: strict match (2+ EPIC IDs)
    if eng_epic_ids:
        for pg, tam_path in candidates:
            count = _check_tamil_page_match(tam_path, eng_epic_ids)
            if count >= 2:
                return tam_path

    # Second pass: relaxed match (1 EPIC ID match for candidates)
    if eng_epic_ids:
        for pg, tam_path in candidates:
            count = _check_tamil_page_match(tam_path, eng_epic_ids)
            if count >= 1:
                return tam_path

    # Slow path: scan all Tamil pages for this part
    if eng_epic_ids:
        for pg, tam_path in sorted(tamil_pages.items()):
            if pg in [eng_page_no, eng_page_no + 1, eng_page_no - 1]:
                continue  # Already tried
            count = _check_tamil_page_match(tam_path, eng_epic_ids)
            if count >= 1:
                return tam_path

    # Last resort: use page+1 offset (the documented standard pattern:
    # "Tamil page = English page + 1"). This catches cases where EPIC ID
    # matching failed due to OCR errors on both sides.
    pg = eng_page_no + 1
    if pg in tamil_pages:
        return tamil_pages[pg]
    if eng_page_no in tamil_pages:
        return tamil_pages[eng_page_no]

    return None


def process_page(eng_path: str, tamil_pages: dict[int, str] = None, eng_page_no: int = 0) -> list[dict]:
    """
    Process one English PDF page and find+merge its Tamil pair.

    Args:
        eng_path: Path to English PDF
        tamil_pages: Dict of {page_no: tamil_path} for this part
        eng_page_no: Page number of the English PDF (for Tamil matching hint)

    Returns list of voter record dicts.
    """
    if tamil_pages is None:
        tamil_pages = {}

    # Extract English image
    eng_img = extract_image_from_pdf(eng_path)

    # Quick check: OCR the full page to detect summary/legend pages
    if len(eng_img.shape) == 3:
        eng_gray = cv2.cvtColor(eng_img, cv2.COLOR_RGB2GRAY)
    else:
        eng_gray = eng_img
    _, eng_thresh = cv2.threshold(eng_gray, 150, 255, cv2.THRESH_BINARY)
    full_text = pytesseract.image_to_string(eng_thresh, lang="eng", config="--psm 3")

    if is_summary_or_legend_page(full_text):
        return []

    # Detect grid on English page
    eng_cells = detect_grid(eng_img)
    if not eng_cells:
        log.warning(f"No grid cells detected in {eng_path}")
        return []

    # OCR each English cell
    eng_records = []
    for i, (x1, y1, x2, y2) in enumerate(eng_cells):
        cell_img = eng_img[y1:y2, x1:x2]
        if cell_img.size == 0:
            continue

        record = ocr_cell_english(cell_img)

        # Targeted serial number extraction from the top-left box
        if not record["serial_no"]:
            targeted_serial = ocr_serial_targeted(cell_img)
            if targeted_serial:
                record["serial_no"] = targeted_serial

        # Try targeted EPIC ID extraction if regex didn't find a valid one
        if not record["epic_id"] or not re.match(r"^[A-Z]{3}\d{7}$", record["epic_id"]):
            targeted_epic = ocr_epic_id_targeted(cell_img)
            if targeted_epic:
                record["epic_id"] = targeted_epic

        # Skip truly empty cells (no name and no EPIC ID found)
        if not record["name_english"] and not record["epic_id"]:
            continue

        record["_cell_index"] = i
        eng_records.append(record)

    # Infer missing serial numbers from surrounding records
    _infer_serial_numbers(eng_records)

    # Correct stray records: fix OCR-misread serials instead of removing records
    eng_records = _filter_stray_records(eng_records)

    # Fix duplicate serial numbers (OCR misread causing two records with same serial)
    _dedup_serial_numbers(eng_records)

    if not eng_records:
        return []

    # Record count validation: each page should have ~30 records (3 cols x 10 rows)
    expected_max = 30
    actual_count = len(eng_records)
    if actual_count < expected_max - 2:
        log.warning(f"Low record count in {Path(eng_path).name}: {actual_count}/{expected_max} expected")
    elif actual_count > expected_max + 2:
        log.warning(f"High record count in {Path(eng_path).name}: {actual_count}/{expected_max} expected")

    # Find matching Tamil page using EPIC IDs
    eng_epic_ids = {r["epic_id"] for r in eng_records if r.get("epic_id")}

    if tamil_pages:
        tam_path = _find_tamil_page(eng_page_no, eng_epic_ids, tamil_pages)
        if tam_path:
            tam_data = _ocr_tamil_page(tam_path)
            serial_data = tam_data.pop("_by_serial", {})

            # First pass: merge by EPIC ID
            for record in eng_records:
                epic = record.get("epic_id", "")
                if epic and epic in tam_data:
                    record["name_tamil"] = tam_data[epic]["name_tamil"]
                    record["relation_name_tamil"] = tam_data[epic]["relation_name_tamil"]

            # Second pass: fill gaps using serial number matching
            for record in eng_records:
                if record.get("name_tamil"):
                    continue
                serial = record.get("serial_no", "")
                if serial and serial in serial_data:
                    record["name_tamil"] = serial_data[serial]["name_tamil"]
                    record["relation_name_tamil"] = serial_data[serial]["relation_name_tamil"]

            # Cross-validate: fill serial gaps from Tamil page serials
            for record in eng_records:
                if not record.get("serial_no"):
                    epic = record.get("epic_id", "")
                    if epic and epic in tam_data:
                        for ts, td in serial_data.items():
                            if td == tam_data.get(epic):
                                record["serial_no"] = ts
                                break

    # Clean up and set defaults
    for record in eng_records:
        record.pop("_cell_index", None)
        if "name_tamil" not in record:
            record["name_tamil"] = ""
        if "relation_name_tamil" not in record:
            record["relation_name_tamil"] = ""

    return eng_records


# ----- Validation -----

def validate_record(record: dict) -> list[str]:
    """Validate a single record. Returns list of warnings."""
    warnings = []

    epic_id = record.get("epic_id", "")
    if epic_id and not re.match(r"^[A-Z]{3}\d{7}$", epic_id):
        warnings.append(f"Invalid EPIC ID: {epic_id}")

    age = record.get("age", "")
    if age:
        try:
            age_int = int(age)
            if age_int < 18 or age_int > 120:
                warnings.append(f"Unusual age: {age}")
        except ValueError:
            warnings.append(f"Non-numeric age: {age}")

    gender = record.get("gender", "")
    if gender and gender not in ("Male", "Female"):
        warnings.append(f"Unexpected gender: {gender}")

    return warnings


# ----- CSV Output -----

def write_pair_csv(records: list[dict], output_dir: Path, ac_no: str, part_no: str, eng_filename: str):
    """
    Write records for one page pair to a CSV file.
    Filename matches the English input PDF (with .csv extension).
    Creates a header-only file for non-data pages (summary/legend).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # Replace .pdf extension with .csv to match input filename
    csv_name = eng_filename.replace(".pdf", ".csv")
    csv_path = output_dir / csv_name

    # Sort by serial number
    def sort_key(r):
        try:
            return int(r.get("serial_no", 0))
        except ValueError:
            return 0

    records.sort(key=sort_key)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for rec in records:
            house_no = str(rec.get("house_no", ""))
            if house_no and not house_no.startswith("'"):
                house_no = f"'{house_no}"

            row = [
                ac_no,
                part_no,
                rec.get("serial_no", ""),
                rec.get("epic_id", ""),
                rec.get("name_english", ""),
                rec.get("name_tamil", ""),
                rec.get("relation_name_english", ""),
                rec.get("relation_name_tamil", ""),
                rec.get("relation_type", ""),
                house_no,
                rec.get("age", ""),
                rec.get("gender", ""),
                "",  # DOB
                "",  # ContactNo
            ]
            writer.writerow(row)

    return csv_path


# ----- Worker Function (for multiprocessing) -----

def _process_pair_worker(args: tuple) -> tuple[str, list[dict], list[str], str, str]:
    """
    Worker function for ProcessPoolExecutor.
    Returns (key, records, warnings, ac_no, part_no).
    """
    eng_path, tamil_pages, key, page_no, ac_no, part_no = args
    warnings = []
    try:
        records = process_page(eng_path, tamil_pages, eng_page_no=page_no)
        for rec in records:
            warnings.extend(validate_record(rec))
        return (key, records, warnings, ac_no, part_no)
    except Exception as e:
        return (key, [], [f"ERROR processing {key}: {e}\n{traceback.format_exc()}"], ac_no, part_no)


# ----- Directory Processing -----

def process_directory(dir_name: str, workers: int = 4, validate_only: bool = False, limit: int = 0):
    """Process all unprocessed pairs in a batch directory."""
    directory = INPUT_DIR / dir_name
    if not directory.exists():
        log.error(f"Directory not found: {directory}")
        return

    output_dir = OUTPUT_DIR / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Discover pairs
    pairs = discover_pairs(directory)
    log.info(f"Found {len(pairs)} total pairs in {dir_name}")

    if not pairs:
        return

    # Load checkpoint
    checkpoint = load_checkpoint(dir_name)
    processed_set = set(checkpoint.get("processed", []))

    # Filter to unprocessed
    pending = [p for p in pairs if p["key"] not in processed_set]

    if validate_only:
        pending = pending[:1]
        log.info("Validate mode: processing only 1 pair")
    elif limit > 0:
        pending = pending[:limit]
        log.info(f"Limit mode: processing up to {limit} pairs")

    log.info(f"Pending: {len(pending)} pairs ({len(processed_set)} already processed)")

    if not pending:
        log.info("All pairs already processed!")
        return

    total_records = 0
    total_warnings = 0
    total_files = 0
    error_count = 0

    # Process pairs — one output CSV per input pair
    if workers > 1 and len(pending) > 1 and not validate_only:
        # Multiprocessing
        work_items = [
            (p["english_path"], p.get("tamil_pages", {}), p["key"], p["page_no"],
             p["ac_no"], p["part_no"])
            for p in pending
        ]

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_pair_worker, item): item
                for item in work_items
            }

            for i, future in enumerate(as_completed(futures)):
                key, records, warnings, ac_no, part_no = future.result()

                for w in warnings:
                    if w.startswith("ERROR"):
                        log.error(w)
                        error_count += 1
                    else:
                        log.warning(w)
                        total_warnings += 1

                # Write per-pair CSV (even if empty — header-only for non-data pages)
                csv_path = write_pair_csv(records, output_dir, ac_no, part_no, key)
                total_records += len(records)
                total_files += 1

                # Update checkpoint
                processed_set.add(key)
                checkpoint["processed"] = sorted(processed_set)
                save_checkpoint(dir_name, checkpoint)

                if (i + 1) % 10 == 0 or (i + 1) == len(pending):
                    log.info(f"Progress: {i + 1}/{len(pending)} pairs, {total_records} records, {total_files} files")
    else:
        # Sequential processing
        for i, pair in enumerate(pending):
            log.info(f"Processing {i + 1}/{len(pending)}: {pair['key']}")

            try:
                records = process_page(pair["english_path"], pair.get("tamil_pages", {}), eng_page_no=pair["page_no"])
                for rec in records:
                    rec_warnings = validate_record(rec)
                    for w in rec_warnings:
                        log.warning(f"{pair['key']} serial {rec.get('serial_no', '?')}: {w}")
                        total_warnings += 1

                total_records += len(records)

                # Write per-pair CSV (even if empty — header-only for non-data pages)
                csv_path = write_pair_csv(records, output_dir, pair["ac_no"], pair["part_no"], pair["key"])
                total_files += 1
                log.info(f"  Extracted {len(records)} records -> {csv_path.name}")

                if validate_only:
                    # Print detailed output (handle Unicode on Windows)
                    import io as _io
                    out = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
                    out.write("\n" + "=" * 60 + "\n")
                    out.write("VALIDATION RESULTS\n")
                    out.write("=" * 60 + "\n")
                    for rec in records:
                        out.write(f"\n  Serial: {rec.get('serial_no', '?')}\n")
                        out.write(f"  EPIC ID: {rec.get('epic_id', '')}\n")
                        out.write(f"  Name (EN): {rec.get('name_english', '')}\n")
                        out.write(f"  Name (TA): {rec.get('name_tamil', '')}\n")
                        out.write(f"  Relation (EN): {rec.get('relation_name_english', '')} ({rec.get('relation_type', '')})\n")
                        out.write(f"  Relation (TA): {rec.get('relation_name_tamil', '')}\n")
                        out.write(f"  House No: {rec.get('house_no', '')}\n")
                        out.write(f"  Age: {rec.get('age', '')}  Gender: {rec.get('gender', '')}\n")
                    out.write(f"\nTotal records: {len(records)}\n")
                    out.flush()
                    return

            except Exception as e:
                log.error(f"Failed to process {pair['key']}: {e}")
                error_count += 1

            # Update checkpoint
            processed_set.add(pair["key"])
            checkpoint["processed"] = sorted(processed_set)
            save_checkpoint(dir_name, checkpoint)

    # Summary
    log.info(f"\n{'=' * 40}")
    log.info(f"SUMMARY for {dir_name}")
    log.info(f"  Pairs processed: {len(pending)}")
    log.info(f"  Output files: {total_files}")
    log.info(f"  Records extracted: {total_records}")
    log.info(f"  Warnings: {total_warnings}")
    log.info(f"  Errors: {error_count}")
    log.info(f"  Output: {output_dir}")
    log.info(f"{'=' * 40}")


# ----- Main -----

def main():
    parser = argparse.ArgumentParser(
        description="Extract electoral roll data from PDFs using OCR"
    )
    parser.add_argument(
        "directory", nargs="?",
        help="Batch directory to process (e.g., AC-184-Part-1-50)"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Process all batch directories sequentially"
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Process only 1 pair and print detailed output"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show file pairs without processing"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset checkpoint for directory"
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max number of pairs to process (default: 0 = all)"
    )
    args = parser.parse_args()

    setup_logging(OCR_DIR / "extraction.log")

    # Verify Tesseract is available
    if pytesseract is None:
        log.error("pytesseract not installed. Run: pip install pytesseract")
        sys.exit(1)

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        log.error(
            "Tesseract OCR not found. Install it:\n"
            "  winget install UB-Mannheim.TesseractOCR\n"
            "  Then add to PATH and install Tamil language data."
        )
        sys.exit(1)

    if not args.directory and not args.all:
        parser.error("Specify a directory or use --all")

    dirs_to_process = BATCH_DIRS if args.all else [args.directory]

    for dir_name in dirs_to_process:
        directory = INPUT_DIR / dir_name

        if args.dry_run:
            pairs = discover_pairs(directory)
            checkpoint = load_checkpoint(dir_name)
            processed_set = set(checkpoint.get("processed", []))
            pending = [p for p in pairs if p["key"] not in processed_set]
            print(f"\n{dir_name}: {len(pairs)} total, {len(pending)} pending")
            for p in pending[:10]:
                print(f"  ENG: {os.path.basename(p['english_path'])}")
                tam_count = len(p.get("tamil_pages", {}))
                print(f"  Tamil pages available: {tam_count}")
                print(f"  AC={p['ac_no']} Part={p['part_no']} Page={p['page_no']}")
                print()
            if len(pending) > 10:
                print(f"  ... and {len(pending) - 10} more")
            continue

        if args.reset:
            cp_file = _checkpoint_path(dir_name)
            response = input(f"Reset checkpoint for {dir_name}? (y/N): ")
            if response.lower() == "y":
                if cp_file.exists():
                    cp_file.unlink()
                output_dir = OUTPUT_DIR / dir_name
                if output_dir.exists():
                    for f in output_dir.glob("*.csv"):
                        f.unlink()
                log.info(f"Reset complete for {dir_name}")
            continue

        log.info(f"\n{'=' * 50}")
        log.info(f"Processing: {dir_name}")
        log.info(f"{'=' * 50}")

        process_directory(
            dir_name,
            workers=args.workers,
            validate_only=args.validate,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
