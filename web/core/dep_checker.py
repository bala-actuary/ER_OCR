"""Dependency detection — checks Python packages, Tesseract binary, and Tamil tessdata."""
import importlib
import os
import shutil
import subprocess
from pathlib import Path

# Packages required for OCR (import_name -> pip package name)
OCR_PACKAGES: dict[str, str] = {
    "fitz":        "PyMuPDF",
    "cv2":         "opencv-python-headless",
    "pytesseract": "pytesseract",
    "numpy":       "numpy",
    "PIL":         "Pillow",
    "pypdf":       "pypdf",
}

# Packages required for the web UI itself
WEB_PACKAGES: dict[str, str] = {
    "fastapi":   "fastapi",
    "uvicorn":   "uvicorn",
    "aiofiles":  "aiofiles",
}

# Well-known Tesseract install paths (Windows)
TESSERACT_DEFAULT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

# Well-known tessdata directories
TESSDATA_SEARCH_DIRS: list[Path] = [
    Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
    Path("/usr/share/tesseract-ocr/5/tessdata"),
    Path("/usr/share/tesseract-ocr/4.00/tessdata"),
    Path("/usr/local/share/tessdata"),
    Path("/opt/homebrew/share/tessdata"),
]


def _pkg_version(import_name: str) -> tuple[bool, str]:
    """Try to import a package and read its version. Returns (ok, version_str)."""
    try:
        mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", None)
        if ver is None:
            # Some packages expose version differently
            import importlib.metadata as meta
            pkg = import_name if import_name != "PIL" else "Pillow"
            pkg = pkg if import_name != "cv2" else "opencv-python-headless"
            try:
                ver = meta.version(pkg)
            except Exception:
                ver = "installed"
        return True, str(ver)
    except ImportError:
        return False, "not installed"


def _find_tesseract() -> tuple[bool, str, str]:
    """Returns (found, path, version_string)."""
    # Check PATH first
    tess = shutil.which("tesseract")
    if tess is None:
        for p in TESSERACT_DEFAULT_PATHS:
            if p.exists():
                tess = str(p)
                break

    if tess is None:
        return False, "", ""

    try:
        result = subprocess.run(
            [tess, "--version"],
            capture_output=True, text=True, timeout=5
        )
        ver_line = (result.stdout or result.stderr or "").splitlines()
        version = ver_line[0].strip() if ver_line else "unknown"
        return True, tess, version
    except Exception:
        return True, tess, "unknown"


def _find_tessdata() -> tuple[bool, str]:
    """Returns (found, directory_path)."""
    # Check env var first
    prefix = os.environ.get("TESSDATA_PREFIX", "")
    if prefix:
        p = Path(prefix)
        if (p / "tam.traineddata").exists():
            return True, str(p)
        if (p / "tessdata" / "tam.traineddata").exists():
            return True, str(p / "tessdata")

    # Check well-known directories
    for d in TESSDATA_SEARCH_DIRS:
        if (d / "tam.traineddata").exists():
            return True, str(d)

    # Check project-local tessdata/
    project_local = Path(__file__).parent.parent.parent / "tessdata"
    if (project_local / "tam.traineddata").exists():
        return True, str(project_local)

    return False, ""


def check_all() -> dict:
    """Run all dependency checks and return a unified status dict."""

    # --- OCR Python packages ---
    ocr_details: dict[str, dict] = {}
    ocr_all_ok = True
    for import_name, pkg_name in OCR_PACKAGES.items():
        ok, ver = _pkg_version(import_name)
        ocr_details[pkg_name] = {"ok": ok, "version": ver}
        if not ok:
            ocr_all_ok = False

    # --- Web packages ---
    web_details: dict[str, dict] = {}
    web_all_ok = True
    for import_name, pkg_name in WEB_PACKAGES.items():
        ok, ver = _pkg_version(import_name)
        web_details[pkg_name] = {"ok": ok, "version": ver}
        if not ok:
            web_all_ok = False

    # --- Tesseract binary ---
    tess_found, tess_path, tess_ver = _find_tesseract()
    tess_status = {
        "ok": tess_found,
        "path": tess_path,
        "version": tess_ver,
        "install_cmd": "winget install UB-Mannheim.TesseractOCR",
        "manual_url": "https://github.com/UB-Mannheim/tesseract/wiki",
    }

    # --- Tamil tessdata ---
    tam_found, tam_dir = _find_tessdata()
    tam_status = {
        "ok": tam_found,
        "tessdata_dir": tam_dir,
        "download_url": "https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata",
    }

    all_ok = ocr_all_ok and tess_found and tam_found

    return {
        "all_ok": all_ok,
        "checks": {
            "ocr_packages":     {"ok": ocr_all_ok,  "details": ocr_details},
            "web_packages":     {"ok": web_all_ok,  "details": web_details},
            "tesseract_binary": tess_status,
            "tamil_tessdata":   tam_status,
        },
    }
