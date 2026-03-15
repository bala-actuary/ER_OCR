# Electoral Roll OCR Extraction Tool (v1.2)

Extracts voter data from Tamil Nadu electoral roll PDFs (English + Tamil pairs) into structured CSV files using local OCR. Completely offline, zero API cost, and achieves **99.87% cell-level accuracy** across 1,118 validated records.

## Why OCR Instead of LLM?

| Factor | OCR (this tool) | LLM-based |
|--------|----------------|-----------|
| **Cost** | $0 (runs locally) | API costs per page (~$0.01-0.05/page) |
| **Accuracy** | 99.87% cell accuracy | Comparable, but varies by model |
| **Speed** | ~60s per page pair | Depends on API rate limits |
| **Scalability** | Run 1000s of pairs overnight with multi-worker | Limited by API quotas and cost |
| **Privacy** | All data stays local | Data sent to external API |
| **Offline** | Works without internet | Requires internet |

With 4 workers, the tool processes ~11,700 page pairs overnight. Accuracy was achieved through 5 phases of targeted improvements including empty cell detection, multi-strategy EPIC/serial voting, confidence-aware Tamil matching, and consecutive-run serial anchoring.

## Architecture

```
PDF --> PyMuPDF (extract image) --> OpenCV (detect grid, crop cells)
    --> Empty cell filter (ink density) --> Tesseract OCR (per cell)
    --> Multi-signal validation --> Regex parsing --> Merge EN+TA --> CSV
```

| Component | Library | Purpose |
|-----------|---------|---------|
| PDF image extraction | PyMuPDF (`fitz`) | Extract embedded PNG from each single-page PDF |
| Grid detection | OpenCV | Morphological ops to find 3x10 row/column grid |
| Empty cell detection | OpenCV | Ink density analysis to skip empty cells before OCR |
| Image preprocessing | OpenCV | CLAHE, denoising, adaptive threshold, 4x upscale |
| OCR | Tesseract 5.4+ (`pytesseract`) | Text recognition (PSM 6, OEM 1) |
| Field parsing | Python `re` | Regex extraction with fuzzy label matching |
| Tamil matching | EPIC ID (confidence-aware) + serial + position | Match Tamil page to English page |

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

This splits each multi-page PDF into individual page files. **All pages are split** — non-data pages (metadata, summary, maps) are auto-detected and skipped during extraction in Step 3. Output goes to `Input/split_files/AC-188/{english,tamil}/`.

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

### Step 4: Merge Page CSVs into Part and AC Files

```bash
python merge_outputs.py --ac AC-188
# Or run interactively:
python merge_outputs.py
```

This merges page-level CSVs back into part-level and AC-level files. Output goes to `output/merged_files/parts/AC-188/` (per-part) and `output/merged_files/ac/AC-188.csv` (entire constituency).

**Important:** The merge script does a **full rewrite** of each part CSV, not an incremental append. Once a part is merged, it is marked as done in a checkpoint and skipped on subsequent runs. If you extract additional pages for a part that was already merged (e.g., extracted 20 pages, merged, then extracted the remaining 26), you must use `--force` to re-merge and pick up the new pages:

```bash
python merge_outputs.py --ac AC-188 --force
```

For best results, complete all extraction for a part before merging.

### Step 5: Check Progress

```bash
bash check-progress.sh
```

## Directory Structure

```
ER_OCR/
├── extract_ocr.py          # Main OCR extraction script
├── split_pdfs.py           # Split multi-page PDFs into individual pages
├── merge_outputs.py        # Merge page CSVs into part-level and AC-level CSVs
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
│   └── merged_files/
│       ├── parts/
│       │   └── AC-xxx/     # Part-level merged CSVs
│       └── ac/
│           └── AC-xxx.csv  # AC-level merged CSV (entire constituency)
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

All pages are split (no metadata pages skipped). Non-data pages are auto-detected and skipped during extraction by `extract_ocr.py`.

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

### `merge_outputs.py` — Merge Page CSVs into Part and AC Files

```
python merge_outputs.py [options]

Options:
  --ac AC-xxx       Assembly Constituency (e.g., AC-188). Prompts if omitted.
  --force           Re-merge all parts from scratch (required if new pages were
                    extracted after a previous merge)
```

Produces both part-level CSVs (`output/merged_files/parts/AC-xxx/`) and a single AC-level CSV (`output/merged_files/ac/AC-xxx.csv`). Each merge does a full rewrite — it does not append. Without `--force`, already-merged parts are skipped. The AC-level file is always regenerated from current part CSVs.

### `analyze_quality.py` — Quality Analysis

```
python analyze_quality.py [options]

Options:
  --ac AC-xxx       Analyze specific AC (default: all available)
```

## How It Works

### Page Splitting
`split_pdfs.py` splits all pages from multi-page PDFs into individual page files. No pages are skipped during splitting — non-data pages (metadata, summary, maps, legends) are auto-detected and skipped during extraction.

### Empty Cell Detection (v1.1)

Before running OCR on each cell, ink density is analyzed. Cells with less than 2% ink coverage (after excluding grid line borders) are skipped. This eliminates phantom records from empty cells on partial pages (pages with fewer than 30 entries), with zero OCR cost.

### Grid Detection
Each PDF page contains a 3-column x 10-row grid of voter entries (max 30 per page). OpenCV detects:
- **Horizontal lines** using morphological opening with a wide kernel
- **Column boundaries** by finding vertical gaps in pixel density
- **Fallback**: If detected columns span <85% of page width, falls back to proportional `[2%, 34%, 66%, 98%]`

### Cell OCR
Each non-empty cell is cropped, upscaled 4x (Lanczos), preprocessed, then passed to Tesseract:
- **English cells**: `--psm 4 --oem 1` with `lang=eng`
- **Tamil cells**: `--psm 6 --oem 1` with `lang=tam+eng` (bottom 15% cropped to avoid label contamination), with retry using alternative preprocessing (Otsu, less aggressive crop) when initial result is poor

### Multi-Signal Record Validation (v1.1)

Records must have at least 2 valid signals (name, EPIC ID, serial number, age+gender, house number) to be accepted. This prevents noise from empty or partially-filled cells from creating phantom records.

### Serial Number Accuracy (v1.1)

- **Multi-strategy voting**: Serial numbers extracted using 3 threshold strategies (fixed 150, Otsu, fixed 120) with majority voting
- **Cross-validation**: Targeted serial always cross-validates the primary OCR result
- **Consecutive-run anchoring**: Stray serial filter uses the longest consecutive run as anchor instead of median, preventing a single misread from cascading into incorrect corrections

### EPIC ID Confidence Scoring (v1.1)

- **Multi-strategy voting**: 3 preprocessing strategies (CLAHE, Otsu, sharpen) with confidence scoring
- **Consensus detection**: If 2+ strategies agree, confidence is boosted
- **Confidence-aware Tamil matching**: Low-confidence EPICs (<70) skip EPIC-based Tamil matching in favor of position-based matching

### Field Parsing
Regex patterns with fuzzy label matching handle common OCR errors:
- `"Fatner Name"` --> `"Father Name"`, `"Gerder"` --> `"Gender"`
- EPIC ID `O` --> `0` correction in digit positions

### Tamil Name Quality (v1.1)

- Gender labels ("ஆண்", "பெண்") and noise words are filtered from Tamil name output
- Minimum 3 Tamil characters required (rejects single-char OCR fragments)
- Retry with alternative preprocessing (Otsu threshold, less aggressive crop) when initial result is poor

### Tamil Page Matching
1. Extract EPIC IDs from English page
2. Try Tamil pages at same number, +/-1 first (fast path)
3. Fall back to scanning all Tamil pages for the part
4. **EPIC-based matching** (Pass 1): Only used when EPIC confidence >= 70
5. **Serial-based matching** (Pass 2): Fills gaps from Pass 1
6. **Position-based matching** (Pass 3): Cell index fallback
7. **Cross-validation**: Low-confidence EPIC matches are verified against position-based results

### Checkpoints
After each page pair, the filename is saved to `checkpoint.json` inside the AC directory. Processing can be stopped and resumed at any time.

## Accuracy

Validated on AC-166 Part 1 (46 page pairs, 1,118 voter records including 10 partial pages):

| Metric | Value |
|--------|-------|
| **Overall cell accuracy** | **99.87%** |
| **Record completeness** | **98.39%** |
| Serial number accuracy | 100% |
| EPIC ID fill rate | 99.9% |
| Name (English) | 99.8% |
| Name (Tamil) | 99.8% |
| Malformed EPIC IDs | 0 |

v1.1 improvements over v1.0:

- Eliminated phantom records on partial pages (pages with <30 entries)
- Fixed serial number misreads caused by stray filter cascading (e.g., 505 misread as 605)
- Improved Tamil name quality: no more gender labels or single-char fragments as names
- Reduced EPIC digit misreads via multi-strategy confidence voting

## Performance

| Metric | Value |
|--------|-------|
| Per page pair (sequential) | ~60 seconds |
| Per AC (~720 pairs, 4 workers) | ~3-4 hours |
| All ACs (~11,700 pairs, 4 workers) | ~6-8 hours |
| Cost | $0 (all local) |
| RAM usage (4 workers) | ~800 MB |

Note: v1.1 is slightly slower per page than v1.0 due to multi-strategy EPIC/serial voting. The additional OCR passes only trigger when needed (low confidence or missing fields).

## Run Logs

Each extraction run generates:
- **Log file**: `logs/extract_{AC}_{timestamp}.log` — per-file processing details
- **Summary JSON**: `logs/extract_{AC}_{timestamp}_summary.json` — total records, warnings, errors, duration

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `setup.bat` fails to install Tesseract | `winget` may not be available on your system. Install Tesseract manually from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki), then re-run `setup.bat` |
| `Tesseract OCR not found` | Verify install path; check that `C:\Program Files\Tesseract-OCR\tesseract.exe` exists |
| `No module named 'fitz'` | Run `pip install pymupdf` |
| Tamil names are empty | Verify `tam` appears in `tesseract --list-langs` |
| `Grid detection failed` | Falls back to proportional splitting automatically |
| Processing is slow | Reduce `--workers` if RAM is limited; increase for faster CPUs |
| `Permission denied` on tessdata | Copy `tam.traineddata` using an admin terminal |
| Unicode errors on Windows | The script handles UTF-8 encoding automatically |
| Merge missing new pages | Use `python merge_outputs.py --ac AC-xxx --force` to re-merge |

## Known Limitations

- **OCR accuracy ceiling at 115 DPI**: Source PDFs are rasterized at 115 DPI, limiting OCR precision for some characters
- **EPIC ID misreads**: Occasional letter/digit confusion (e.g., `RVI` vs `RVJ`) — inherent to OCR at this resolution, mitigated by multi-strategy voting in v1.1
- **Tamil name quality on partial pages**: A few cells on partial pages may have missing or mismatched Tamil names due to garbled OCR at 115 DPI
- **Processing speed**: ~60s per page pair due to Tesseract OCR overhead and multi-strategy voting; parallelized with `--workers`

## Changelog

### v1.2 (2026-03-15)

- **AC-level merge**: `merge_outputs.py` now automatically produces a single CSV per constituency alongside part-level files
- **Output directory restructure**: Merged output moved from `output/merged/` to `output/merged_files/parts/` and `output/merged_files/ac/`

### v1.1 (2026-03-14)

- **Split all pages**: `split_pdfs.py` no longer skips metadata pages; non-data pages are auto-detected during extraction
- **Empty cell detection**: Pre-OCR ink density analysis eliminates phantom records on partial pages
- **Multi-signal record validation**: Requires 2+ valid fields to accept a record
- **Serial number multi-strategy voting**: 3 threshold strategies with majority voting and cross-validation
- **Consecutive-run serial anchor**: Stray filter uses longest consecutive run instead of median, preventing misread cascades
- **Trailing empty row trim**: Safety net removes noise records from bottom of partial pages
- **Tamil name quality**: Minimum 3 Tamil characters, gender/noise label rejection, expanded noise word list
- **Tamil OCR retry**: Alternative preprocessing (Otsu, less aggressive crop) when initial Tamil result is poor
- **EPIC confidence scoring**: Multi-strategy voting with per-word confidence from Tesseract
- **Confidence-aware Tamil matching**: Low-confidence EPICs skip to position-based matching; cross-validation for borderline cases
- **Merge documentation**: Clarified that merge does full rewrite, not append; `--force` required for re-merge

### v1.0

- Initial release with 4 phases of OCR improvements
- 99.30% cell-level accuracy across 6,510 validated records

## License

This project is licensed under the [MIT License](LICENSE).
