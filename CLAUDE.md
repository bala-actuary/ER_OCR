# Electoral Roll PDF Extraction — OCR Approach (Claude Code Context)

## Purpose

Local OCR-based alternative to the LLM approach. Extracts voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs) into structured CSV. Zero API cost — uses Tesseract OCR + OpenCV locally.

## Architecture

```
PDF → PyMuPDF (extract image) → OpenCV (detect grid, crop cells)
    → Tesseract OCR (per cell) → Regex parsing → Merge EN+TA → CSV
```

| Component | Library |
|-----------|---------|
| PDF image extraction | PyMuPDF (`fitz`) |
| Grid detection | OpenCV (morphological + Hough + contour fallback) |
| Image preprocessing | OpenCV (CLAHE, denoising, adaptive threshold) |
| OCR | Tesseract 5.4+ via `pytesseract` (PSM 6, OEM 1, 4x upscale) |
| Field parsing | Python `re` with fuzzy label matching |
| Tamil matching | EPIC ID + serial number + position-based fallback |

## Key File

- `extract_ocr.py` — Single-file script containing all logic (~2100 lines)
- `analyze_quality.py` — Quality analysis script for validating extraction accuracy

## Input/Output

- **Input**: `Input/split_files/{directory}/english/` and `tamil/` (local to ER_OCR)
- **Output**: `output/{directory}/` — one CSV per input English PDF pair
- **Output filename**: matches English PDF name with `.csv` extension
  - e.g., `2026-EROLLGEN-S22-184-SIR-FinalRoll-Revision1-ENG-301-WI_page_10.csv`
- **Non-data pages** (summary, legend): produce header-only CSV (0 records)
- **Checkpoints**: `checkpoints/{dir_name}.json` — tracks processed filenames

## CSV Output Format (14 columns)

AC No, Part No, Serial No, EPIC ID, Name (English), Name (Tamil), Relation Name (English), Relation Name (Tamil), Relation Type, House No, Age, Gender, DOB, ContactNo

- Records sorted ascending by Serial No
- House numbers prefixed with `'` for Excel compatibility
- DOB and ContactNo always blank
- Encoding: utf-8-sig (BOM for Excel)

## Pages to Skip (Non-Data Pages)

These pages produce header-only CSVs (no voter records extracted):
- **Summary page (English)** — contains "SUMMARY OF ELECTORS" table
- **Summary page (Tamil)** — Tamil equivalent
- **Legend page (Tamil only)** — contains "E- Expired, S- Shifted, R-Repeated, M - Missing, Q- Disqualified"

Detection: `is_summary_or_legend_page()` checks OCR text for these markers.

## Extraction Rules

From ENGLISH PDF: serial_no, epic_id, name_english, relation_name_english, relation_type, house_no, age, gender
From TAMIL PDF (matched by EPIC ID, serial number, or cell position): name_tamil, relation_name_tamil

## Validation Rules

- EPIC ID: 3 uppercase letters + 7 digits (any prefix accepted)
- Age: 18-120 range
- Gender: "Male" or "Female"
- Max 30 records per page (3 columns x 10 rows)

## CLI Usage

```bash
python extract_ocr.py AC-184-Part-1-50 --validate       # Test 1 pair
python extract_ocr.py AC-184-Part-1-50 --limit 10       # Process 10 pairs
python extract_ocr.py AC-184-Part-1-50 --workers 4      # Process full directory
python extract_ocr.py --all --workers 4                  # All 8 directories
python extract_ocr.py AC-184-Part-1-50 --dry-run         # Show pending pairs
python extract_ocr.py AC-184-Part-1-50 --reset           # Reset checkpoint
bash check-progress.sh                                    # Monitor progress
```

## Critical Rules

- **Tamil page = English page + 1** (offset baked into PDF naming)
- **One output CSV per input English PDF** — enables 1:1 input/output traceability
- **Checkpoint per directory** — supports parallel sessions on different directories
- **Grid detection uses multi-scale + fallback chain**: morphological → Hough lines → contours → proportional
- **Column collapse guard**: if detected columns span <85% of page width, falls back to proportional `[2%, 34%, 66%, 98%]`
