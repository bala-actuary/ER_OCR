"""Builds subprocess commands for installing dependencies.
Each function returns a list[str] command suitable for job_manager.start_job().
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
REQUIREMENTS_TXT = BASE_DIR / "requirements.txt"

# Where to write tessdata if admin rights are unavailable
PROJECT_TESSDATA_DIR = BASE_DIR / "tessdata"
DOT_ENV_PATH = BASE_DIR / ".env"

# Standard Windows Tesseract tessdata path
TESSERACT_TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")


def pip_install_command() -> list[str]:
    """pip install -r requirements.txt using the current Python interpreter."""
    return [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_TXT)]


def winget_tesseract_command() -> list[str]:
    """winget install Tesseract."""
    return ["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "--silent"]


def tessdata_download_command() -> list[str]:
    """Returns a Python one-liner command that downloads tam.traineddata.

    The script tries the system tessdata directory first; falls back to the
    project-local tessdata/ folder and writes TESSDATA_PREFIX=tessdata to .env.
    Progress is printed so job_manager can stream it.
    """
    script = r"""
import urllib.request, shutil, sys, pathlib

URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata"
DEST_CANDIDATES = [
    pathlib.Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
    pathlib.Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
]
PROJECT_DIR = pathlib.Path(r'{base_dir}')
FALLBACK = PROJECT_DIR / "tessdata"
DOT_ENV  = PROJECT_DIR / ".env"

dest_dir = None
for d in DEST_CANDIDATES:
    if d.exists():
        try:
            test_file = d / ".write_test"
            test_file.touch()
            test_file.unlink()
            dest_dir = d
            break
        except PermissionError:
            pass

if dest_dir is None:
    FALLBACK.mkdir(parents=True, exist_ok=True)
    dest_dir = FALLBACK
    # Write TESSDATA_PREFIX to .env so start.bat picks it up
    lines = []
    if DOT_ENV.exists():
        lines = [l for l in DOT_ENV.read_text().splitlines() if not l.startswith("TESSDATA_PREFIX=")]
    lines.append(f"TESSDATA_PREFIX={FALLBACK}")
    DOT_ENV.write_text("\n".join(lines) + "\n")
    print(f"[INFO] No write access to Program Files — downloading to {{dest_dir}}")
    print(f"[INFO] Added TESSDATA_PREFIX to .env — restart the server after download")

dest_file = dest_dir / "tam.traineddata"
print(f"Downloading tam.traineddata to {{dest_file}} ...")
sys.stdout.flush()

def progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, int(downloaded * 100 / total_size))
        print(f"\r  {{pct}}% ({{downloaded // 1024}} KB / {{total_size // 1024}} KB)", end="", flush=True)

urllib.request.urlretrieve(URL, dest_file, reporthook=progress)
print(f"\n[OK] Saved to {{dest_file}}")
""".format(base_dir=str(BASE_DIR).replace("\\", "\\\\"))

    return [sys.executable, "-c", script]
