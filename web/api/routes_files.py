"""AC listing, status, CSV download, quality data, logs, and system info."""
import csv
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .deps import (
    BASE_DIR, INPUT_DOWNLOADS_DIR, INPUT_SPLIT_DIR,
    OUTPUT_AC_DIR, OUTPUT_SPLIT_DIR, LOGS_DIR,
    list_ac_dirs,
)

router = APIRouter(tags=["files"])


# ── System info ──────────────────────────────────────────────────────────────

@router.get("/system/info")
async def system_info():
    import shutil
    tess = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tess_ver = ""
    try:
        import subprocess
        r = subprocess.run([tess, "--version"], capture_output=True, text=True, timeout=3)
        tess_ver = (r.stdout or r.stderr or "").splitlines()[0]
    except Exception:
        pass

    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "base_dir": str(BASE_DIR),
        "tesseract_version": tess_ver,
    }


@router.get("/system/resources")
async def system_resources(ac: Optional[str] = None):
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(OUTPUT_AC_DIR.parent if OUTPUT_AC_DIR.parent.exists() else BASE_DIR))
        cpu_cores = psutil.cpu_count(logical=True) or 1
        ram_available_gb = mem.available / (1024 ** 3)
        disk_free_gb = disk.free / (1024 ** 3)

        # Recommend workers: min(cores-1, RAM/0.5GB per worker)
        recommended = max(1, min(cpu_cores - 1, int(ram_available_gb / 0.5)))

        # Disk estimation: ~50KB per pending pair
        estimated_output_mb = 0
        disk_warning = None
        if ac:
            split_dir = INPUT_SPLIT_DIR / ac / "english"
            cp_file = INPUT_SPLIT_DIR / ac / "checkpoint.json"
            total_pdfs = len(list(split_dir.glob("*.pdf"))) if split_dir.exists() else 0
            processed = 0
            if cp_file.exists():
                try:
                    data = json.loads(cp_file.read_text())
                    processed = len(data.get("processed", []))
                except Exception:
                    pass
            pending = max(0, total_pdfs - processed)
            estimated_output_mb = (pending * 50) / 1024  # 50KB per pair → MB
            if estimated_output_mb > 0:
                if disk_free_gb < (estimated_output_mb / 1024):
                    disk_warning = "danger"
                elif disk_free_gb < (2 * estimated_output_mb / 1024):
                    disk_warning = "warning"

        return {
            "cpu_cores": cpu_cores,
            "cpu_recommended_workers": recommended,
            "ram_total_gb": round(mem.total / (1024 ** 3), 1),
            "ram_available_gb": round(ram_available_gb, 1),
            "disk_free_gb": round(disk_free_gb, 1),
            "disk_path": str(OUTPUT_AC_DIR.parent),
            "estimated_output_mb": round(estimated_output_mb, 1),
            "disk_warning": disk_warning,
        }
    except ImportError:
        cpu = os.cpu_count() or 4
        return {
            "cpu_cores": cpu,
            "cpu_recommended_workers": max(1, cpu - 1),
            "ram_total_gb": None,
            "ram_available_gb": None,
            "disk_free_gb": None,
            "disk_path": str(OUTPUT_AC_DIR.parent),
            "estimated_output_mb": 0,
            "disk_warning": None,
        }


# ── AC listing and status ─────────────────────────────────────────────────────

@router.get("/acs")
async def list_acs():
    result = []
    for ac in list_ac_dirs():
        result.append(_ac_summary(ac))
    return result


class CreateAcRequest(BaseModel):
    ac: str


@router.post("/acs")
async def create_ac(req: CreateAcRequest):
    """Create a new AC input directory with english/ and tamil/ subfolders."""
    if not re.match(r'^AC-\d{1,3}$', req.ac):
        raise HTTPException(status_code=400, detail="AC must be in AC-xxx format (e.g., AC-188)")
    ac_dir = INPUT_DOWNLOADS_DIR / req.ac
    if ac_dir.exists():
        raise HTTPException(status_code=409, detail=f"{req.ac} already exists")
    (ac_dir / "english").mkdir(parents=True, exist_ok=True)
    (ac_dir / "tamil").mkdir(parents=True, exist_ok=True)
    return {"ac": req.ac, "created": True}


@router.get("/acs/{ac}/status")
async def ac_status(ac: str):
    return _ac_detail(ac)


@router.get("/acs/{ac}/progress")
async def ac_progress(ac: str):
    """Returns checkpoint progress and ETA data for the ETA estimator."""
    cp_file = INPUT_SPLIT_DIR / ac / "checkpoint.json"
    split_dir = INPUT_SPLIT_DIR / ac / "english"

    total = len(list(split_dir.glob("*.pdf"))) if split_dir.exists() else 0
    processed = 0
    if cp_file.exists():
        try:
            data = json.loads(cp_file.read_text())
            processed = len(data.get("processed", []))
        except Exception:
            pass

    pct = round(processed * 100 / total, 1) if total > 0 else 0
    return {
        "ac": ac,
        "processed": processed,
        "total": total,
        "pct": pct,
    }


@router.get("/acs/{ac}/preview")
async def ac_preview(ac: str):
    """Return the first few rows from the most recent page CSV for quick validation."""
    csv_dir = OUTPUT_SPLIT_DIR / ac
    if not csv_dir.exists():
        return {"rows": [], "message": "No output CSVs yet"}

    csvs = sorted(csv_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not csvs:
        return {"rows": [], "message": "No output CSVs yet"}

    rows = []
    try:
        with open(csvs[0], encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= 10:
                    break
                rows.append(row)
    except Exception as e:
        return {"rows": [], "message": str(e)}

    return {"rows": rows, "source_file": csvs[0].name}


@router.get("/acs/{ac}/csv")
async def download_csv(ac: str):
    csv_file = OUTPUT_AC_DIR / f"{ac}.csv"
    if not csv_file.exists():
        raise HTTPException(status_code=404, detail=f"Merged CSV for {ac} not found")
    return FileResponse(
        path=str(csv_file),
        filename=f"{ac}.csv",
        media_type="text/csv",
    )


# ── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
async def list_logs():
    if not LOGS_DIR.exists():
        return []
    logs = []
    for f in sorted(LOGS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix in (".log", ".json"):
            logs.append({
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified": f.stat().st_mtime,
            })
    return logs[:100]


@router.get("/logs/{filename}")
async def get_log(filename: str):
    # Sanitize — only allow simple filenames
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    log_file = LOGS_DIR / filename
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    if filename.endswith(".json"):
        return json.loads(log_file.read_text(encoding="utf-8"))

    # Return last 500 lines for .log files
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": lines[-500:], "total_lines": len(lines)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ac_summary(ac: str) -> dict:
    has_downloads = (INPUT_DOWNLOADS_DIR / ac).exists()
    has_split_en = (INPUT_SPLIT_DIR / ac / "english").exists()
    merged_csv = OUTPUT_AC_DIR / f"{ac}.csv"
    has_merged = merged_csv.exists()
    record_count = 0
    if has_merged:
        try:
            with open(merged_csv, encoding="utf-8-sig") as f:
                record_count = sum(1 for _ in f) - 1  # minus header
        except Exception:
            pass

    # Checkpoint progress
    cp_file = INPUT_SPLIT_DIR / ac / "checkpoint.json"
    total_pdfs = 0
    processed = 0
    if has_split_en:
        total_pdfs = len(list((INPUT_SPLIT_DIR / ac / "english").glob("*.pdf")))
    if cp_file.exists():
        try:
            data = json.loads(cp_file.read_text())
            processed = len(data.get("processed", []))
        except Exception:
            pass
    pct = round(processed * 100 / total_pdfs, 1) if total_pdfs > 0 else 0

    # Validation
    validation = _validate_ac_files(ac)

    return {
        "ac": ac,
        "has_downloads": has_downloads,
        "has_split": has_split_en,
        "has_merged": has_merged,
        "record_count": record_count,
        "total_pdfs": total_pdfs,
        "processed": processed,
        "checkpoint_pct": pct,
        "validation": validation,
    }


def _ac_detail(ac: str) -> dict:
    summary = _ac_summary(ac)
    # Add last log summary if available
    summary_files = sorted(
        LOGS_DIR.glob(f"extract_{ac}*_summary.json"),
        key=lambda f: f.stat().st_mtime, reverse=True
    ) if LOGS_DIR.exists() else []
    if summary_files:
        try:
            summary["last_run_summary"] = json.loads(summary_files[0].read_text())
        except Exception:
            pass
    return summary


def _validate_ac_files(ac: str) -> dict:
    """Check English/Tamil PDF counts match and folders are non-empty."""
    en_dir = INPUT_DOWNLOADS_DIR / ac / "english"
    ta_dir = INPUT_DOWNLOADS_DIR / ac / "tamil"

    en_count = len(list(en_dir.glob("*.pdf"))) if en_dir.exists() else 0
    ta_count = len(list(ta_dir.glob("*.pdf"))) if ta_dir.exists() else 0

    issues = []
    if en_count == 0:
        issues.append("No English PDFs found")
    if ta_count == 0:
        issues.append("No Tamil PDFs found")
    if en_count > 0 and ta_count > 0 and en_count != ta_count:
        issues.append(f"Count mismatch: English={en_count}, Tamil={ta_count}")

    return {
        "ok": len(issues) == 0,
        "en_count": en_count,
        "ta_count": ta_count,
        "issues": issues,
    }
