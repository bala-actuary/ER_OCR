"""Shared path constants and helpers for all route modules."""
from pathlib import Path
import sys

# Project root — two levels up from web/api/
BASE_DIR = Path(__file__).parent.parent.parent

INPUT_DOWNLOADS_DIR = BASE_DIR / "Input" / "ER_Downloads"
INPUT_SPLIT_DIR     = BASE_DIR / "Input" / "split_files"
OUTPUT_SPLIT_DIR    = BASE_DIR / "output" / "split_files"
OUTPUT_PARTS_DIR    = BASE_DIR / "output" / "merged_files" / "parts"
OUTPUT_AC_DIR       = BASE_DIR / "output" / "merged_files" / "ac"
LOGS_DIR            = BASE_DIR / "logs"

SCRIPTS = {
    "split":   BASE_DIR / "split_pdfs.py",
    "extract": BASE_DIR / "extract_ocr.py",
    "merge":   BASE_DIR / "merge_outputs.py",
    "analyze": BASE_DIR / "analyze_quality.py",
}

PYTHON = sys.executable


def list_ac_dirs() -> list[str]:
    """Return sorted list of AC-xxx directory names found in ER_Downloads."""
    acs = set()
    for base in (INPUT_DOWNLOADS_DIR, INPUT_SPLIT_DIR):
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and d.name.startswith("AC-"):
                    acs.add(d.name)
    return sorted(acs)
