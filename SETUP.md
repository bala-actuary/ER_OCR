# Setup Instructions — OCR Extraction

Step-by-step guide to set up and run the OCR-based electoral roll extraction.

## Prerequisites

- **Python 3.10+** (tested with 3.12)
- **Windows 11** (paths are Windows-specific; adaptable to Linux/Mac)

## Step 1: Install Tesseract OCR

### Windows

```bash
winget install UB-Mannheim.TesseractOCR
```

This installs Tesseract to `C:\Program Files\Tesseract-OCR\`. The script auto-detects this path.

### Verify Installation

```bash
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
# Expected: tesseract v5.4.0.xxxxx
```

## Step 2: Install Tamil Language Data

Tesseract ships with English only. Tamil must be added manually.

### Download

Download `tam.traineddata` from:
https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata

### Install

Copy the file to Tesseract's tessdata folder. **Requires administrator privileges:**

1. Open Command Prompt **as Administrator**
2. Run:
   ```
   copy C:\Users\<your-user>\Downloads\tam.traineddata "C:\Program Files\Tesseract-OCR\tessdata\tam.traineddata"
   ```

Or use File Explorer: drag-and-drop `tam.traineddata` into `C:\Program Files\Tesseract-OCR\tessdata\` and approve the admin prompt.

### Verify

```bash
"C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
# Expected output should include:
#   eng
#   osd
#   tam
```

## Step 3: Install Python Dependencies

```bash
pip install pymupdf opencv-python-headless pytesseract numpy Pillow
```

### Verify

```bash
python -c "import fitz, cv2, pytesseract, numpy, PIL; print('All packages OK')"
```

## Step 4: Validate Setup

Navigate to the `ocr/` directory and run a validation test:

```bash
cd ocr/
python extract_ocr.py AC-184-Part-1-50 --validate
```

Expected output:
- `Found XXXX total pairs in AC-184-Part-1-50`
- `Extracted 30 records` (or close to 30)
- Field-by-field output showing Serial, EPIC ID, Names (EN/TA), etc.

If you see `Tesseract OCR not found`, check that the install path is correct in the script (`C:\Program Files\Tesseract-OCR\tesseract.exe`).

## Step 5: Run Extraction

### Single Directory

```bash
python extract_ocr.py AC-184-Part-1-50 --workers 4
```

### All Directories

```bash
python extract_ocr.py --all --workers 4
```

### Monitor Progress

In a separate terminal:

```bash
bash check-progress.sh
```

## Step 6: Review Output

Output CSVs are in `ocr/output/{directory}/`. Each file covers one part number:

```
ocr/output/AC-184-Part-1-50/2026_EROLL_AC-184_Part-10.csv
```

Open in Excel or any CSV viewer. The file uses BOM encoding for proper Tamil text display in Excel.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Tesseract OCR not found` | Verify install path; update `_tess_path` in `extract_ocr.py` if different |
| `No module named 'fitz'` | Run `pip install pymupdf` |
| Tamil names are empty | Verify `tam` appears in `tesseract --list-langs` |
| `Grid detection failed` | Falls back to proportional splitting; some pages may have fewer records |
| Processing is slow | Reduce `--workers` if RAM is limited; or increase for faster CPUs |
| `Permission denied` on tessdata | Copy `tam.traineddata` using an admin terminal |

## Resuming After Interruption

The script automatically resumes from where it left off. Checkpoints are saved in `ocr/checkpoints/`. Simply re-run the same command:

```bash
python extract_ocr.py AC-184-Part-1-50 --workers 4
```

## Resetting Progress

To start over for a directory:

```bash
python extract_ocr.py AC-184-Part-1-50 --reset
```

This deletes the checkpoint and all output CSVs for that directory (with confirmation).
