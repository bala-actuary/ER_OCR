# How to Run OCR Extraction — Step-by-Step

## Before You Start

Ensure prerequisites are installed (see [SETUP.md](SETUP.md) for details):
- Tesseract OCR with Tamil language data
- Python packages: `pymupdf opencv-python-headless pytesseract numpy Pillow`

## Step 1: Open Terminal and Navigate

```bash
cd C:\Users\balaa\Dev\NTK\ElectorialData\Claude\ocr
```

## Step 2: Dry Run (See What Will Be Processed)

Check how many pairs are pending for a directory:

```bash
python extract_ocr.py AC-184-Part-301-350 --dry-run
```

This lists the first 10 pending pairs without processing anything.

## Step 3: Validate on 1 Pair (Recommended First Time)

Test OCR quality on a single pair before bulk processing:

```bash
python extract_ocr.py AC-184-Part-301-350 --validate
```

Review the field-by-field output to confirm extraction quality.

## Step 4: Process a Limited Number of Pairs

Process a specific number of pairs (e.g., 10):

```bash
python extract_ocr.py AC-184-Part-301-350 --limit 10 --workers 4
```

- `--limit 10` — process only 10 pairs, then stop
- `--workers 4` — use 4 parallel workers (adjust based on CPU/RAM)
- Progress is checkpointed after each pair, so it's safe to interrupt

## Step 5: Process an Entire Directory

Omit `--limit` to process all remaining pairs:

```bash
python extract_ocr.py AC-184-Part-301-350 --workers 4
```

## Step 6: Process All Directories

```bash
python extract_ocr.py --all --workers 4
```

Processes all 8 batch directories sequentially.

## Step 7: Check Progress

```bash
bash check-progress.sh
```

Shows a table of total/done/pending pairs and record counts for each directory.

## Step 8: Review Output

Output CSVs are in `ocr/output/{directory}/`:

```
ocr/output/AC-184-Part-301-350/2026_EROLL_AC-184_Part-310.csv
```

Open in Excel or any CSV viewer. Files use BOM encoding for proper Tamil display.

## Resuming After Interruption

Simply re-run the same command. The script automatically skips already-processed pairs:

```bash
python extract_ocr.py AC-184-Part-301-350 --limit 10 --workers 4
```

## Resetting Progress

To start over for a directory (deletes checkpoint and output CSVs):

```bash
python extract_ocr.py AC-184-Part-301-350 --reset
```

You will be prompted for confirmation before anything is deleted.

## Available Batch Directories

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

## Quick Reference

```bash
# Dry run
python extract_ocr.py <directory> --dry-run

# Validate 1 pair
python extract_ocr.py <directory> --validate

# Process N pairs
python extract_ocr.py <directory> --limit N --workers 4

# Process all pairs in a directory
python extract_ocr.py <directory> --workers 4

# Process all directories
python extract_ocr.py --all --workers 4

# Check progress
bash check-progress.sh

# Reset a directory
python extract_ocr.py <directory> --reset
```

## Performance Notes

| Workers | Speed | RAM |
|---------|-------|-----|
| 1 | ~45 sec/pair | ~200 MB |
| 4 | ~12 sec/pair | ~800 MB |

With `--limit 10 --workers 4`, expect ~2 minutes total.
