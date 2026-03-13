# Electoral Roll PDF Extraction — OCR Approach (v1.0)

## Purpose

Local OCR-based tool to extract voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs) into structured CSV. Zero API cost — uses Tesseract OCR + OpenCV locally.

## Architecture

```
PDF -> PyMuPDF (extract image) -> OpenCV (detect grid, crop cells)
    -> Tesseract OCR (per cell) -> Regex parsing -> Merge EN+TA -> CSV
```

| Component | Library |
|-----------|---------|
| PDF image extraction | PyMuPDF (`fitz`) |
| Grid detection | OpenCV (morphological + Hough + contour fallback) |
| Image preprocessing | OpenCV (CLAHE, denoising, adaptive threshold) |
| OCR | Tesseract 5.4+ via `pytesseract` (PSM 6, OEM 1, 4x upscale) |
| Field parsing | Python `re` with fuzzy label matching |
| Tamil matching | EPIC ID + serial number + position-based fallback |

## Key Files

- `extract_ocr.py` — Main OCR extraction script (~2100 lines)
- `split_pdfs.py` — Splits multi-page PDFs into individual page files
- `merge_outputs.py` — Merges page-level CSVs into part-level CSVs
- `analyze_quality.py` — Quality analysis script for validating extraction accuracy
- `check-progress.sh` — Progress monitoring
- `setup.bat` — Automated setup (Windows)

## Workflow

```
1. split_pdfs.py    — Split downloaded PDFs into pages
2. extract_ocr.py   — OCR extract data from each page pair
3. merge_outputs.py  — Merge page CSVs back into part-level files
```

## Input/Output

- **Downloads**: `Input/ER_Downloads/AC-xxx/{english,tamil}/` — original multi-page PDFs
- **Split pages**: `Input/split_files/AC-xxx/{english,tamil}/` — one PDF per page
- **Page CSVs**: `output/split_files/AC-xxx/` — one CSV per English page
- **Merged CSVs**: `output/merged/AC-xxx/` — one CSV per original part file
- **Checkpoints**: `Input/split_files/AC-xxx/checkpoint.json` — tracks processed filenames
- **Logs**: `logs/extract_{AC}_{timestamp}.log` and `_summary.json`

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
# Split PDFs
python split_pdfs.py --ac AC-188              # Split PDFs for an AC
python split_pdfs.py                           # Interactive prompt

# Extract data
python extract_ocr.py AC-188 --validate        # Test 1 pair
python extract_ocr.py AC-188 --workers 4       # Process full AC
python extract_ocr.py AC-188 --part 101        # Process specific part
python extract_ocr.py AC-188 --part 50-100     # Process part range
python extract_ocr.py --all --workers 4         # All AC directories
python extract_ocr.py AC-188 --dry-run          # Show pending pairs
python extract_ocr.py AC-188 --reset --part 101 # Reset specific part
python extract_ocr.py                           # Interactive prompt

# Merge outputs
python merge_outputs.py --ac AC-188            # Merge page CSVs to part CSVs
python merge_outputs.py                         # Interactive prompt

# Monitor
bash check-progress.sh                          # Check progress
python analyze_quality.py --ac AC-188          # Quality analysis
```

## Critical Rules

- **Tamil page = English page + 1** (offset baked into PDF naming)
- **English PDFs skip first 2 pages**, Tamil skip first 3 (metadata pages)
- **One output CSV per input English PDF** — enables 1:1 input/output traceability
- **Checkpoint per AC directory** — supports parallel sessions on different ACs
- **Grid detection uses multi-scale + fallback chain**: morphological -> Hough lines -> contours -> proportional
- **Column collapse guard**: if detected columns span <85% of page width, falls back to proportional `[2%, 34%, 66%, 98%]`
- **Legacy batch dirs** (AC-184-Part-1-50 etc.) still work with extract_ocr.py for backward compatibility
