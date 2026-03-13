# Electoral Roll OCR Extraction Tool (v1.0)

Extracts voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs) into structured CSV files using local OCR. Completely offline, zero API cost, and achieves **99.30% cell-level accuracy** across 6,510 validated records.

## Why OCR Instead of LLM?

| Factor | OCR (this tool) | LLM-based |
|--------|----------------|-----------|
| **Cost** | $0 (runs locally) | API costs per page (~$0.01-0.05/page) |
| **Accuracy** | 99.30% cell accuracy | Comparable, but varies by model |
| **Speed** | ~45s per page pair | Depends on API rate limits |
| **Scalability** | Run 1000s of pairs overnight with multi-worker | Limited by API quotas and cost |
| **Privacy** | All data stays local | Data sent to external API |
| **Offline** | Works without internet | Requires internet |

With 4 workers, the tool processes ~11,700 page pairs in ~5-6 hours — run it overnight and have all results in the morning. The 99.30% accuracy was achieved through 4 phases of targeted improvements (EPIC ID extraction, Tamil matching, grid detection fallbacks) without any LLM involvement.

## Architecture

```
PDF --> PyMuPDF (extract image) --> OpenCV (detect grid, crop 30 cells)
    --> Tesseract OCR (per cell) --> Regex parsing --> Merge EN+TA --> CSV
```

| Component | Library | Purpose |
|-----------|---------|---------|
| PDF image extraction | PyMuPDF (`fitz`) | Extract embedded PNG from each single-page PDF |
| Grid detection | OpenCV | Morphological ops to find 3x10 row/column grid |
| Image preprocessing | OpenCV | CLAHE, denoising, adaptive threshold, 4x upscale |
| OCR | Tesseract 5.4+ (`pytesseract`) | Text recognition (PSM 6, OEM 1) |
| Field parsing | Python `re` | Regex extraction with fuzzy label matching |
| Tamil matching | EPIC ID + serial + position | Match Tamil page to English page |

## Quick Start

### Option 1: Automated Setup (Windows)

```batch
setup.bat
```

This checks/installs Python, Tesseract, Tamil language data, and Python dependencies.

### Option 2: Manual Setup

#### 1. Install Python 3.10+

Download from [python.org](https://www.python.org/downloads/). Check "Add Python to PATH" during installation.

#### 2. Install Tesseract OCR

```bash
winget install UB-Mannheim.TesseractOCR
```

This installs to `C:\Program Files\Tesseract-OCR\`. Verify:

```bash
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
# Expected: tesseract v5.4.0.xxxxx
```

**Important:** During Tesseract installation, check **"Additional language data"** and **"Additional script data"** to include Tamil support automatically.

#### 3. Install Tamil Language Data (if not done during install)

Download [`tam.traineddata`](https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata) and copy to Tesseract's tessdata folder:

```bash
# Open Command Prompt as Administrator
copy %USERPROFILE%\Downloads\tam.traineddata "C:\Program Files\Tesseract-OCR\tessdata\tam.traineddata"
```

Verify Tamil is available:

```bash
"C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
# Should list: eng, osd, tam
```

#### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Verify:

```bash
python -c "import fitz, cv2, pytesseract, numpy, PIL; print('All packages OK')"
```

## End-to-End Workflow

### Step 1: Organize Input PDFs

Place your downloaded electoral roll PDFs in the following structure:

```
Input/ER_Downloads/AC-xxx/
    english/    <-- English PDF files (e.g., 2026-EROLLGEN-...-ENG-1-WI.pdf)
    tamil/      <-- Tamil PDF files (e.g., 2026-EROLLGEN-...-TAM-1-WI.pdf)
```

Replace `AC-xxx` with your Assembly Constituency number (e.g., `AC-184`, `AC-188`).

### Step 2: Split PDFs into Pages

```bash
python split_pdfs.py --ac AC-188
# Or run interactively:
python split_pdfs.py
```

This splits each multi-page PDF into individual page files, skipping metadata pages (2 for English, 3 for Tamil). Output goes to `Input/split_files/AC-188/{english,tamil}/`.

### Step 3: Extract Data

```bash
# Validate on a single page pair first (recommended)
python extract_ocr.py AC-188 --validate

# Process one AC with 4 parallel workers
python extract_ocr.py AC-188 --workers 4

# Process specific part(s) — useful when splitting work across people
python extract_ocr.py AC-188 --part 101
python extract_ocr.py AC-188 --part 50-100
python extract_ocr.py AC-188 --part 1,5,10-20

# Process first 100 pairs only (useful for testing)
python extract_ocr.py AC-188 --limit 100 --workers 4

# Process all ACs (can run overnight for large datasets)
python extract_ocr.py --all --workers 4

# Run interactively (prompts for AC number):
python extract_ocr.py
```

Output CSVs (one per page) are saved to `output/split_files/AC-188/`.

### Step 4: Merge Page CSVs into Part Files

```bash
python merge_outputs.py --ac AC-188
# Or run interactively:
python merge_outputs.py
```

This merges page-level CSVs back into part-level files (matching the original downloaded PDFs). Output goes to `output/merged/AC-188/`.

### Step 5: Check Progress

```bash
bash check-progress.sh
```

## Directory Structure

```
ER_OCR/
├── extract_ocr.py          # Main OCR extraction script
├── split_pdfs.py           # Split multi-page PDFs into individual pages
├── merge_outputs.py        # Merge page CSVs into part-level CSVs
├── analyze_quality.py      # Quality analysis and accuracy reporting
├── check-progress.sh       # Progress monitoring script
├── setup.bat               # Automated setup (Windows)
├── requirements.txt        # Python dependencies
├── Input/
│   ├── ER_Downloads/
│   │   └── AC-xxx/         # Original downloaded PDFs
│   │       ├── english/
│   │       └── tamil/
│   └── split_files/
│       └── AC-xxx/         # Split page PDFs + checkpoint
│           ├── english/
│           ├── tamil/
│           └── checkpoint.json
├── output/
│   ├── split_files/
│   │   └── AC-xxx/         # Page-level CSVs (one per page)
│   └── merged/
│       └── AC-xxx/         # Part-level merged CSVs
└── logs/                   # Per-run log files and JSON summaries
```

## CSV Output Format

14 columns, UTF-8 with BOM encoding (for Excel compatibility):

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
| DOB | (always blank) | |
| ContactNo | (always blank) | |

- House numbers prefixed with `'` to prevent Excel auto-formatting
- Records sorted ascending by Serial No within each file

## CLI Reference

### `split_pdfs.py` — Split PDFs into Pages

```
python split_pdfs.py [options]

Options:
  --ac AC-xxx       Assembly Constituency (e.g., AC-188). Prompts if omitted.
  --force           Overwrite existing split files
```

### `extract_ocr.py` — Extract Data from PDFs

```
python extract_ocr.py [directory] [options]

Positional:
  directory         AC directory (e.g., AC-188). Prompts if omitted.

Options:
  --all             Process all discovered AC directories
  --validate        Process only 1 pair, print detailed output
  --dry-run         List pending pairs without processing
  --reset           Reset checkpoint and output for a directory
  --part PARTS      Filter by part number: single (101), range (50-100), or mixed (1,5,10-20)
  --workers N       Number of parallel workers (default: 4)
  --limit N         Process only N pairs, then stop

Part filtering examples:
  python extract_ocr.py AC-188 --part 101               # Only Part 101
  python extract_ocr.py AC-188 --part 50-100             # Parts 50 through 100
  python extract_ocr.py AC-188 --part 1,5,10-20          # Parts 1, 5, and 10-20
  python extract_ocr.py AC-188 --reset --part 101        # Reset only Part 101
  python extract_ocr.py AC-188 --reset --part 50-100     # Reset Parts 50-100
  python extract_ocr.py AC-188 --dry-run --part 101      # Preview Part 101 pending pairs
```

### `merge_outputs.py` — Merge Page CSVs into Part Files

```
python merge_outputs.py [options]

Options:
  --ac AC-xxx       Assembly Constituency (e.g., AC-188). Prompts if omitted.
  --force           Re-merge even if checkpoint says already done
```

### `analyze_quality.py` — Quality Analysis

```
python analyze_quality.py [options]

Options:
  --ac AC-xxx       Analyze specific AC (default: all available)
```

## How It Works

### Grid Detection
Each PDF page contains a 3-column x 10-row grid of voter entries (max 30 per page). OpenCV detects:
- **Horizontal lines** using morphological opening with a wide kernel
- **Column boundaries** by finding vertical gaps in pixel density
- **Fallback**: If detected columns span <85% of page width, falls back to proportional `[2%, 34%, 66%, 98%]`

### Cell OCR
Each cell is cropped, upscaled 4x (Lanczos), preprocessed (CLAHE + denoise + adaptive threshold), then passed to Tesseract:
- **English cells**: `--psm 6 --oem 1` with `lang=eng`
- **Tamil cells**: `--psm 6 --oem 1` with `lang=tam+eng` (bottom 20% cropped to avoid label contamination)

### Field Parsing
Regex patterns with fuzzy label matching handle common OCR errors:
- `"Fatner Name"` --> `"Father Name"`, `"Gerder"` --> `"Gender"`
- EPIC ID `O` --> `0` correction in digit positions

### Tamil Page Matching
1. Extract EPIC IDs from English page
2. Try Tamil pages at same number, +/-1 first (fast path)
3. Fall back to scanning all Tamil pages for the part
4. Position-based fallback if EPIC matching fails

### Checkpoints
After each page pair, the filename is saved to `checkpoint.json` inside the AC directory. Processing can be stopped and resumed at any time.

## Accuracy

Validated on 240 page pairs across 4 directories (6,510 voter records):

| Metric | Value |
|--------|-------|
| **Overall cell accuracy** | **99.30%** |
| **All 12 fields complete** | **93.0%** |
| EPIC ID fill rate | 97.3% |
| Name (English) | 99.4% |
| Name (Tamil) | 99.9% |
| Relation Name (English) | 99.8% |
| Relation Name (Tamil) | 98.3% |
| Age | 98.9% |
| Gender | 98.8% |
| Malformed EPIC IDs | 0 |

Accuracy was achieved through 4 phases of targeted improvements including multi-ROI EPIC extraction from Tamil cells, position-based Tamil matching fallback, column collapse detection, and ASCII contamination guards.

## Performance

| Metric | Value |
|--------|-------|
| Per page pair (sequential) | ~45 seconds |
| Per AC (~720 pairs, 4 workers) | ~2-3 hours |
| All ACs (~11,700 pairs, 4 workers) | ~5-6 hours |
| Cost | $0 (all local) |
| RAM usage (4 workers) | ~800 MB |

## Run Logs

Each extraction run generates:
- **Log file**: `logs/extract_{AC}_{timestamp}.log` — per-file processing details
- **Summary JSON**: `logs/extract_{AC}_{timestamp}_summary.json` — total records, warnings, errors, duration

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Tesseract OCR not found` | Verify install path; check that `C:\Program Files\Tesseract-OCR\tesseract.exe` exists |
| `No module named 'fitz'` | Run `pip install pymupdf` |
| Tamil names are empty | Verify `tam` appears in `tesseract --list-langs` |
| `Grid detection failed` | Falls back to proportional splitting automatically |
| Processing is slow | Reduce `--workers` if RAM is limited; increase for faster CPUs |
| `Permission denied` on tessdata | Copy `tam.traineddata` using an admin terminal |
| Unicode errors on Windows | The script handles UTF-8 encoding automatically |

## Known Limitations

- **OCR accuracy ceiling at 115 DPI**: Source PDFs are rasterized at 115 DPI, limiting OCR precision for some characters
- **EPIC ID misreads**: Occasional letter/digit confusion (e.g., `RVI` vs `RVJ`) — inherent to OCR at this resolution
- **Processing speed**: ~45s per page pair due to Tesseract OCR overhead; parallelized with `--workers`

## License

This project is licensed under the [MIT License](LICENSE).
