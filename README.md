# Electoral Roll PDF Extraction — OCR Approach

Extracts voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs) into structured CSV files using local OCR. This is an alternative to the LLM-based approach in the parent directory — completely independent, zero API cost.

## Architecture

```
PDF ──► PyMuPDF (extract image) ──► OpenCV (detect grid, crop 30 cells)
    ──► Tesseract OCR (per cell) ──► Regex parsing ──► Merge EN+TA ──► CSV
```

| Component | Library | Purpose |
|-----------|---------|---------|
| PDF image extraction | PyMuPDF (`fitz`) | Extract embedded PNG from each single-page PDF |
| Grid detection | OpenCV | Morphological ops to find row/column boundaries |
| OCR | Tesseract (via `pytesseract`) | Text recognition on individual cells |
| Field parsing | Python `re` | Regex extraction of serial no, EPIC ID, name, etc. |
| Tamil matching | EPIC ID comparison | Finds correct Tamil page by matching EPIC IDs |

## Directory Structure

```
ocr/
├── extract_ocr.py          # Main extraction script
├── check-progress.sh        # Progress monitoring script
├── README.md                # This file
├── SETUP.md                 # Installation & setup instructions
├── extraction.log           # Runtime log (created on first run)
├── checkpoints/             # Per-directory checkpoint files
│   ├── AC-184-Part-1-50.json
│   ├── AC-184-Part-51-100.json
│   └── ...
└── output/                  # Extracted CSV files (one per input pair)
    ├── AC-184-Part-1-50/
    │   ├── 2026-EROLLGEN-...-ENG-1-WI_page_3.csv
    │   ├── 2026-EROLLGEN-...-ENG-1-WI_page_4.csv
    │   └── ...  (one CSV per English PDF, matching filename)
    ├── AC-184-Part-51-100/
    └── ...
```

**Input PDFs** are read from `Input/split_files/` (local to ER_OCR).

## CSV Output Format

One CSV per input English PDF pair: `output/{directory}/{english_filename}.csv` (matching input filename with `.csv` extension). Non-data pages (summary, legend) produce header-only CSVs.

| Column | Source | Example |
|--------|--------|---------|
| AC No | Filename | `184` |
| Part No | Filename | `33` |
| Serial No | English OCR | `211` |
| EPIC ID | English OCR | `RVJ1612993` |
| Name (English) | English OCR | `Kavitha` |
| Name (Tamil) | Tamil OCR | `கவிதா` |
| Relation Name (English) | English OCR | `Murugesan` |
| Relation Name (Tamil) | Tamil OCR | `முருகேசன்` |
| Relation Type | English OCR | `Father` |
| House No | English OCR | `'1-192` |
| Age | English OCR | `30` |
| Gender | English OCR | `Female` |
| DOB | (empty) | |
| ContactNo | (empty) | |

- Encoding: `utf-8-sig` (BOM for Excel compatibility)
- House numbers prefixed with `'` to prevent Excel auto-formatting
- Records sorted ascending by Serial No within each file

## Quick Start

```bash
# 1. Setup (one-time) — see SETUP.md for detailed instructions
# Tesseract + Tamil language data must be installed first

# 2. Navigate to ocr directory
cd ocr/

# 3. Validate on a single page pair (recommended first step)
python extract_ocr.py AC-184-Part-1-50 --validate

# 4. Process one directory
python extract_ocr.py AC-184-Part-1-50 --workers 4

# 5. Process all directories
python extract_ocr.py --all --workers 4

# 6. Check progress
bash check-progress.sh
```

## CLI Reference

```
python extract_ocr.py <directory> [options]
python extract_ocr.py --all [options]

Positional:
  directory              Batch directory name (e.g., AC-184-Part-1-50)

Options:
  --all                  Process all 8 batch directories sequentially
  --validate             Process only 1 pair, print detailed field-by-field output
  --dry-run              List pending pairs without processing
  --reset                Clear checkpoint and output for a directory (with confirmation)
  --workers N            Number of parallel workers (default: 4)
  --limit N              Process only N pairs, then stop (default: all)
```

## Batch Directories

| Directory | Parts |
|-----------|-------|
| `AC-184-Part-1-50` | Parts 1-50 |
| `AC-184-Part-51-100` | Parts 51-100 |
| `AC-184-Part-101-150` | Parts 101-150 |
| `AC-184-Part-151-200` | Parts 151-200 |
| `AC-184-Part-201-250` | Parts 201-250 |
| `AC-184-Part-251-300` | Parts 251-300 |
| `AC-184-Part-301-350` | Parts 301-350 |
| `AC-184-Part-351-400` | Parts 351-400 |

Total: ~11,700 PDF pairs across 388 parts.

## How It Works

### 1. Grid Detection
Each PDF page contains a 3-column x 10-row grid of voter entry boxes. OpenCV detects:
- **Horizontal lines** using morphological opening with a wide kernel
- **Column boundaries** by finding vertical gaps in pixel density
- Fallback to proportional splitting if detection fails

### 2. Cell OCR
Each cell is cropped, upscaled 4x (Lanczos), preprocessed (CLAHE + denoise + adaptive threshold), then passed to Tesseract:
- **English cells**: `--psm 6 --oem 1` with `lang=eng`
- **Tamil cells**: `--psm 6 --oem 1` with `lang=tam+eng` (bottom 20% cropped to avoid label contamination)
- **EPIC ID**: Also extracted from Tamil cells using English OCR for matching

### 3. Field Parsing
Regex patterns with fuzzy label matching handle common OCR errors:
- `"Fatner Name"` → recognized as `"Father Name"`
- `"Gerder"` → recognized as `"Gender"`
- `"Age = 30"` → recognized as `"Age : 30"`
- EPIC ID `O` → `0` correction in digit positions

### 4. Serial Number Inference
Some serial numbers are in bordered boxes that Tesseract misses. The script infers missing serials from surrounding records (electoral rolls have sequential numbering).

### 5. Tamil Page Matching
English and Tamil pages don't have a consistent filename offset. The script:
1. Extracts EPIC IDs from the English page
2. Tries Tamil pages at same number, +1, -1 first (fast path)
3. Falls back to scanning all Tamil pages for the part
4. Matches based on 2+ EPIC ID matches

### 6. Checkpoint/Resume
After each page pair, the English filename is saved to `checkpoints/{dir_name}.json`. Processing can be stopped and resumed at any time.

## Known Limitations

- **OCR accuracy at 115 DPI**: Some English names have minor errors (`VFLAVAN` instead of `VELAVAN`)
- **EPIC ID misreads**: Occasional letter/digit confusion (`RVI` vs `RVJ`)
- **Tamil relation names**: ~80% extraction rate; some missed when labels aren't recognized
- **Processing speed**: ~45 seconds per page pair (English + Tamil matching + Tamil OCR)

## Performance Estimates

| Metric | Value |
|--------|-------|
| Per page pair (sequential) | ~45 seconds |
| Per directory (~720 pairs) | ~9 hours (1 worker) |
| All directories (~11,700 pairs) | ~5-6 hours (4 workers) |
| Cost | $0 (all local) |
| RAM usage (4 workers) | ~800 MB |
