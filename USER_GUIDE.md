# Electoral Roll OCR — User Guide

**Version 1.4** | Last updated: 2026-03-17

---

## Table of Contents

1. [What This Tool Does](#1-what-this-tool-does)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
   - [Option A: Web UI Setup (Recommended)](#option-a-web-ui-setup-recommended)
   - [Option B: Automated Setup (setup.bat)](#option-b-automated-setup-setupbat)
   - [Option C: Manual Setup](#option-c-manual-setup)
   - [What If Setup Fails?](#what-if-setup-fails)
4. [Getting Started — Web UI](#4-getting-started--web-ui)
   - [Launching the Web UI](#launching-the-web-ui)
   - [Understanding the Layout](#understanding-the-layout)
5. [Step-by-Step Workflow](#5-step-by-step-workflow)
   - [Step 1: Prepare Input PDFs](#step-1-prepare-input-pdfs)
   - [Step 2: Create or Select an AC](#step-2-create-or-select-an-ac)
   - [Step 3: Split PDFs](#step-3-split-pdfs)
   - [Step 4: Extract Data (OCR)](#step-4-extract-data-ocr)
   - [Step 5: Merge Outputs](#step-5-merge-outputs)
   - [Step 6: Download Results](#step-6-download-results)
6. [Extract Options Explained](#6-extract-options-explained)
7. [Testing Before a Full Run](#7-testing-before-a-full-run)
8. [Overnight Queue](#8-overnight-queue)
9. [Monitoring Progress](#9-monitoring-progress)
10. [Understanding the Output CSV](#10-understanding-the-output-csv)
11. [CLI Reference (Advanced)](#11-cli-reference-advanced)
12. [Troubleshooting](#12-troubleshooting)
13. [FAQ](#13-faq)

---

## 1. What This Tool Does

This tool extracts voter data from Tamil Nadu electoral roll PDFs into structured CSV files. It processes **English and Tamil PDF pairs** for each Assembly Constituency (AC), using local OCR (Optical Character Recognition) — no internet or API costs required.

**What you get:** A CSV file per constituency with columns for Serial No, EPIC ID, Name (English & Tamil), Relation Name (English & Tamil), Relation Type, House No, Age, and Gender.

**What you need:** The electoral roll PDFs downloaded from [voters.eci.gov.in](https://voters.eci.gov.in/) in both English and Tamil.

---

## 2. Prerequisites

| Requirement | Details |
|-------------|---------|
| **Operating System** | Windows 10/11 (primary), Linux/macOS (supported) |
| **Python** | 3.10 or higher |
| **Tesseract OCR** | Version 5.4+ with Tamil language data |
| **Disk Space** | ~50 KB per page pair output; ~500 MB for Tesseract + dependencies |
| **RAM** | Minimum 2 GB free (4+ GB recommended for multi-worker) |

---

## 3. Installation

### Option A: Web UI Setup (Recommended)

The easiest way — the Web UI checks everything for you and installs missing components with one click.

1. Double-click **`start.bat`** (Windows) or run `bash start.sh` (Linux/macOS)
2. A browser window opens at `http://localhost:7000`
3. Click the **gear icon** (⚙ Setup) in the sidebar
4. The Setup panel shows three dependency checks:
   - **Python OCR Packages** — PyMuPDF, OpenCV, pytesseract, NumPy, Pillow, pypdf
   - **Tesseract Binary** — The OCR engine itself
   - **Tamil Tessdata** — Tamil language model for Tesseract
5. Click **Install** next to any item showing ❌
6. When all three show ✅, you're ready

### Option B: Automated Setup (setup.bat)

```batch
setup.bat
```

This script checks and installs Python, Tesseract, Tamil language data, and Python packages automatically. Follow the on-screen prompts.

### Option C: Manual Setup

#### Install Python 3.10+

Download from [python.org](https://www.python.org/downloads/). **Important:** Check "Add Python to PATH" during installation.

#### Install Tesseract OCR

```bash
winget install UB-Mannheim.TesseractOCR
```

During installation, check **"Additional language data"** and **"Additional script data"** to include Tamil support.

Verify:
```bash
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

#### Install Tamil Language Data (if not included)

Download [`tam.traineddata`](https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata) and copy to:
```
C:\Program Files\Tesseract-OCR\tessdata\tam.traineddata
```

#### Install Python Dependencies

```bash
pip install -r requirements.txt
```

### What If Setup Fails?

Here are the most common setup failures and how to fix them:

#### Python OCR Packages fail to install

| Problem | Solution |
|---------|----------|
| `pip` not found | Python wasn't added to PATH. Reinstall Python and check "Add Python to PATH" |
| Permission denied | Open Command Prompt as Administrator, then run `pip install -r requirements.txt` |
| `No module named 'fitz'` | Run `pip install pymupdf` directly |
| Package version conflict | Run `pip install --upgrade -r requirements.txt` to force upgrade |
| Build errors (C++ compiler) | Install Visual Studio Build Tools from [visualstudio.microsoft.com](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |

#### Tesseract fails to install

| Problem | Solution |
|---------|----------|
| `winget` not available | Your Windows version may not have it. Download Tesseract manually from [UB-Mannheim GitHub](https://github.com/UB-Mannheim/tesseract/wiki). Install the `.exe` to `C:\Program Files\Tesseract-OCR\` |
| Tesseract installed but not detected | Make sure `C:\Program Files\Tesseract-OCR\tesseract.exe` exists. If installed elsewhere, add its folder to your system PATH |
| Antivirus blocks install | Temporarily disable real-time protection, install, then re-enable |

#### Tamil Tessdata fails to download

| Problem | Solution |
|---------|----------|
| Permission denied on tessdata folder | The Web UI will automatically fall back to a project-local `tessdata/` folder. Alternatively, open Command Prompt as Administrator and copy the file manually |
| Download fails (no internet) | Download `tam.traineddata` on another machine from [this link](https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata), then copy it to `C:\Program Files\Tesseract-OCR\tessdata\` via USB |
| Tamil not showing in `--list-langs` | The file may be corrupted. Re-download (should be ~40 MB) |

#### Web UI itself fails to start

| Problem | Solution |
|---------|----------|
| `fastapi` not found | Run `pip install fastapi uvicorn aiofiles psutil` |
| Port 7000 in use | The launcher auto-tries ports 7000-7009. If all are in use, close other applications or check with `netstat -ano \| findstr :7000` |
| Unicode error on startup | This has been fixed in v1.4. If you see it, ensure you have the latest code |
| Browser doesn't open | Navigate manually to `http://localhost:7000` |

**General tip:** If all else fails, try the Web UI Setup panel — it provides the most user-friendly installation experience with real-time progress streaming.

---

## 4. Getting Started — Web UI

### Launching the Web UI

**Windows:**
```batch
start.bat
```

**Linux/macOS:**
```bash
bash start.sh
```

The browser opens automatically at `http://localhost:7000`. This is a local-only address — nothing is exposed to the network.

### Stopping the Web UI

When you're done, stop the server:

1. Find the **terminal/command prompt window** that opened when you ran `start.bat`
2. Press **`Ctrl+C`** in that window, or simply **close the window**
3. Close the browser tab

All your data, checkpoints, and queue state are saved to disk automatically. Next time you run `start.bat`, everything picks up where you left off.

### Understanding the Layout

The UI has a **sidebar** on the left (desktop) or a **bottom bar** (mobile/small screens):

| Section | Icon/Label | What it does |
|---------|-----------|--------------|
| **Setup** | ⚙ (gear) | Collapsible panel to check and install dependencies. Hidden by default — click to expand. |
| **Workflow** | ▶ Workflow | Main workspace. Select an AC, configure options, run the pipeline. |
| **Live Logs** | 📋 Live Logs | Watch real-time output from running jobs. Colour-coded log lines, ETA, kill button. |
| **Data** | 📁 Data | Overview of all ACs — progress, record counts, CSV download. |
| **History** | 🕐 History | Browse past log files and run summaries. |

---

## 5. Step-by-Step Workflow

### Step 1: Prepare Input PDFs

1. Go to [voters.eci.gov.in](https://voters.eci.gov.in/)
2. Select your state (Tamil Nadu), district, and Assembly Constituency
3. Download the electoral roll PDFs in **both English and Tamil**
4. Place them in the correct folder structure:

```
Input/ER_Downloads/AC-188/
    english/    <-- English PDFs (e.g., 2026-EROLLGEN-...-ENG-1-WI.pdf)
    tamil/      <-- Tamil PDFs (e.g., 2026-EROLLGEN-...-TAM-1-WI.pdf)
```

**Important:** The number of English and Tamil PDFs should match. If they don't, the UI will show a yellow warning with a link to re-download.

### Step 2: Create or Select an AC

**If the AC already has PDFs:**
- Open the **Workflow** tab
- Select your AC from the dropdown (e.g., `AC-188 (0%)`)

**If you need to create a new AC:**
1. Click the green **`+`** button next to the AC dropdown
2. Enter the AC number in `AC-xxx` format (e.g., `AC-188`)
3. The tool creates the directory structure automatically
4. Copy your PDF files into the newly created `english/` and `tamil/` folders
5. Click the **↺** refresh button to update the dropdown

### Step 3: Split PDFs

**What this does:** Splits each multi-page PDF into individual page files. All pages are split — non-data pages (metadata, summary, maps) are automatically skipped during extraction later.

1. In the Pipeline section, find **1. Split PDFs**
2. (Optional) Check `--force` if you want to overwrite existing split files
3. Click **▶ Run**
4. The job opens in Live Logs — wait for completion

**Tip:** Click the **ℹ** button next to the step name to see a detailed explanation.

### Step 4: Extract Data (OCR)

**What this does:** Runs Tesseract OCR on each page pair (English + Tamil) and extracts voter records into CSV files.

1. Find **2. Extract (OCR)** in the Pipeline
2. Set your desired options:
   - **Workers slider** (left panel): Controls parallel processing. The slider shows green/yellow/red based on your system resources.
   - **--part**: Leave empty for all parts, or enter a range (e.g., `1-50`)
   - **--page**: Leave empty for all pages, or enter specific pages (e.g., `1-10`)
   - **--limit**: Leave as 0 for all, or set a number to process only that many pairs
   - **--cross-check**: Enable to add validation columns to the CSV
3. Click **▶ Run**
4. Monitor progress in Live Logs

**For your first run**, we recommend testing a few pages first — see [Testing Before a Full Run](#7-testing-before-a-full-run).

### Step 5: Merge Outputs

**What this does:** Combines individual page CSVs into part-level and AC-level files.

1. Find **3. Merge Outputs**
2. (Optional) Check `--force` if you're re-merging after additional extractions
3. Click **▶ Run**

### Step 6: Download Results

1. Go to the **Data** tab
2. Find your AC in the list
3. Click **⬇ Download CSV** to get the merged AC-level CSV file
4. Open in Excel, Google Sheets, or any spreadsheet application

**Or use Full Pipeline:** Instead of running steps individually, click **⚡ Run Full Pipeline (Split → Extract → Merge)** to run all three steps automatically.

---

## 6. Extract Options Explained

| Option | Format | Example | What it does |
|--------|--------|---------|-------------|
| **--part** | Number or range | `101`, `50-100`, `1,5,10-20` | Process only specific parts. Leave empty for all. |
| **--page** | Number or range | `4`, `1-10`, `1,5,10-20` | Process only specific pages within a part. Requires --part. |
| **--limit** | Number | `10` | Stop after processing this many pairs. 0 = no limit. |
| **--cross-check** | Checkbox | — | Cross-validates English vs Tamil data. Adds two extra columns: `Cross_Check` (OK/REVIEW) and `Cross_Check_Notes`. |
| **--reset** | Checkbox (yellow) | — | Clears the checkpoint for the specified part, allowing re-processing. **Use with care** — a confirmation dialog will appear. |

### Utility Buttons

| Button | What it does |
|--------|-------------|
| **Dry Run** | Shows what file pairs would be processed, without actually processing them. Useful to verify before committing. |
| **Validate Page** | Tests extraction on specific pages and shows detailed output in Live Logs. Respects the --part and --page settings. |
| **Test 1 Page** (bottom) | Quick one-page test with inline preview table. Great for checking OCR quality. |

---

## 7. Testing Before a Full Run

Before committing to a full AC extraction (which can take hours), it's wise to test:

### Quick Test (1 page with preview)

1. Select your AC
2. Click **🔍 Test 1 Page** at the bottom of the Pipeline section
3. A preview table appears showing extracted records — verify names, EPIC IDs, ages look correct

### Targeted Test (specific pages)

1. Set **--part** to a part number (e.g., `1`)
2. Set **--page** to a page range (e.g., `1-5`)
3. Click **Validate Page**
4. Check the Live Logs for detailed output

### Dry Run (see what will be processed)

1. Click **Dry Run**
2. Check Live Logs — it lists all pending file pairs without processing them
3. Useful to verify the right files are queued

---

## 8. Overnight Queue

For processing multiple ACs unattended:

1. Select an AC and configure workers/options
2. Click **Add Selected AC** in the Overnight Queue section
3. Repeat for other ACs
4. Click **Start Queue**
5. The tool runs Split → Extract → Merge for each AC sequentially
6. A browser notification fires when each AC completes

**Queue features:**
- Queue state is saved to disk — if the server restarts, the queue resumes
- Click **Stop After Current** to gracefully pause (finishes the current AC)
- Remove waiting items with the **X** button

---

## 9. Monitoring Progress

### During Extraction

- **Live Logs tab**: Real-time colour-coded output. Red = errors, yellow = warnings, green = success.
- **ETA indicator**: Shows percentage complete and page count (e.g., "45% done (130/290 pages)")
- **Kill button**: Red button to stop a running job immediately

### Overall Progress

- **Workflow tab**: AC status card shows extraction progress bar, record count, and step completion (Downloads ✓, Split ✓, Merged ✓)
- **Data tab**: Overview of all ACs with progress bars and record counts

---

## 10. Understanding the Output CSV

The merged CSV has **14 columns** by default:

| Column | Description | Example |
|--------|------------|---------|
| AC No | Assembly Constituency number | `188` |
| Part No | Part number within the AC | `33` |
| Serial No | Voter serial number | `211` |
| EPIC ID | Voter ID card number | `RVJ1612993` |
| Name (English) | Voter name in English | `Kavitha` |
| Name (Tamil) | Voter name in Tamil | `கவிதா` |
| Relation Name (English) | Father/Husband name in English | `Murugesan` |
| Relation Name (Tamil) | Father/Husband name in Tamil | `முருகேசன்` |
| Relation Type | Relationship | `Father` |
| House No | House/door number | `1-192` |
| Age | Voter age | `30` |
| Gender | Male or Female | `Female` |
| DOB | Date of birth (always blank) | |
| ContactNo | Contact number (always blank) | |

**With `--cross-check` enabled**, two extra columns are added:

| Column | Values | Meaning |
|--------|--------|---------|
| Cross_Check | `OK` or `REVIEW` | `REVIEW` = at least one field disagreed between English and Tamil |
| Cross_Check_Notes | Text | Details of mismatches (e.g., `EPIC mismatch EN=WXJ1234567 TA=WXJ1234568`) |

**File details:**
- Encoding: UTF-8 with BOM (opens correctly in Excel)
- House numbers prefixed with `'` to prevent Excel auto-formatting
- Records sorted by Serial No ascending

---

## 11. CLI Reference (Advanced)

All operations available in the Web UI can also be run from the command line:

### Split PDFs
```bash
python split_pdfs.py --ac AC-188
python split_pdfs.py --ac AC-188 --force    # Overwrite existing
```

### Extract Data
```bash
python extract_ocr.py AC-188 --workers 4                      # Full AC
python extract_ocr.py AC-188 --part 101                        # Specific part
python extract_ocr.py AC-188 --part 50-100                     # Part range
python extract_ocr.py AC-188 --part 3 --page 1-10              # Page range within part
python extract_ocr.py AC-188 --part 3 --page 1,5,10-20         # Specific pages
python extract_ocr.py AC-188 --limit 10 --workers 4            # First 10 pairs only
python extract_ocr.py AC-188 --validate                        # Test 1 pair
python extract_ocr.py AC-188 --part 3 --page 4 --validate      # Test specific page
python extract_ocr.py AC-188 --dry-run                          # Show pending pairs
python extract_ocr.py AC-188 --reset --part 101                 # Reset checkpoint for part
python extract_ocr.py AC-188 --cross-check --workers 4          # With cross-validation
python extract_ocr.py --all --workers 4                         # All ACs
```

### Merge Outputs
```bash
python merge_outputs.py --ac AC-188
python merge_outputs.py --ac AC-188 --force    # Re-merge all parts
```

### Quality Analysis
```bash
python analyze_quality.py --ac AC-188
```

---

## 12. Troubleshooting

| Problem | Solution |
|---------|----------|
| **Setup: Tesseract not found** | Verify `C:\Program Files\Tesseract-OCR\tesseract.exe` exists. If installed elsewhere, add to PATH. |
| **Setup: Tamil not available** | Download `tam.traineddata` and copy to Tesseract's `tessdata` folder. See [Installation](#3-installation). |
| **Setup: Python packages fail** | Try `pip install --upgrade -r requirements.txt`. If permission errors, run as Administrator. |
| **Web UI won't start** | Run `pip install fastapi uvicorn aiofiles psutil`. Check if port 7000 is free. |
| **"Method Not Allowed" error** | The server is running old code. Restart: close the server terminal, run `start.bat` again. |
| **Count mismatch warning** | English and Tamil PDF counts differ. Check your downloads at [voters.eci.gov.in](https://voters.eci.gov.in/). |
| **Tamil names are empty** | Verify `tam` in `tesseract --list-langs`. Re-download `tam.traineddata` if needed. |
| **Processing is slow** | Reduce `--workers` if RAM-limited. Each worker uses ~200 MB RAM. |
| **Merge missing pages** | Use `--force` when merging: the merge does a full rewrite, not append. |
| **Job shows error immediately** | Check Live Logs — the subprocess exit message shows the cause. |
| **Server changes not taking effect** | Restart the web server. Python code changes require a server restart. |
| **Grid detection failed** | Automatic fallback handles this. If data quality is poor, try `--validate` on the specific page. |

---

## 13. FAQ

**Q: Does this tool need internet access?**
A: No. Once installed, everything runs locally. The only time internet is needed is for initial setup (downloading Tesseract and Python packages).

**Q: How long does processing take?**
A: About 60 seconds per page pair. A full AC with ~720 pairs takes 3-4 hours with 4 workers. Multiple ACs can be queued for overnight processing.

**Q: Is my data sent anywhere?**
A: No. All processing happens on your machine. No data leaves your computer.

**Q: Can I stop and resume later?**
A: Yes. The tool saves a checkpoint after each page pair. When you run extraction again, it picks up where it left off automatically.

**Q: What if I need to re-process some pages?**
A: Use `--reset` with `--part` to clear the checkpoint for specific parts. Or use `--page` with `--validate` to re-inspect individual pages without affecting the checkpoint.

**Q: What accuracy can I expect?**
A: 99.87% cell-level accuracy based on validation of 1,118 records. Occasional EPIC ID letter/digit confusion may occur due to source PDF resolution (115 DPI).

**Q: Can multiple people work on different ACs simultaneously?**
A: Yes. Each AC has its own checkpoint. Different users can process different ACs at the same time (on different machines or terminals).

**Q: What's the `--cross-check` option for?**
A: It re-reads Tamil cells to independently verify EPIC IDs, house numbers, and serial numbers against the English data. Records with disagreements are flagged as `REVIEW` — useful for quality auditing.

**Q: How do I update to a newer version?**
A: Pull the latest code (if using git) or download the updated files. Restart the web server. Your existing data and checkpoints are preserved.

---

*This guide covers the Electoral Roll OCR Tool v1.4. For technical details, see [README.md](README.md). For developer reference, see [CLAUDE.md](CLAUDE.md).*
