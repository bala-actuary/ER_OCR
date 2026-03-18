"""Workflow job launchers: split, extract, merge, analyze, pipeline, and queue."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..api.deps import PYTHON, SCRIPTS, INPUT_DOWNLOADS_DIR, INPUT_SPLIT_DIR
from ..core.job_manager import job_manager
from ..core.queue_manager import queue_manager

router = APIRouter(tags=["workflow"])


# ── Request models ──────────────────────────────────────────────────────────

class SplitRequest(BaseModel):
    ac: str
    force: bool = False


class ExtractRequest(BaseModel):
    ac: str
    workers: int = 4
    part: str = ""
    cross_check: bool = False
    run_validate: bool = False
    dry_run: bool = False
    page: str = ""
    limit: int = 0
    reset: bool = False


class MergeRequest(BaseModel):
    ac: str
    force: bool = False


class AnalyzeRequest(BaseModel):
    ac: str


class PipelineRequest(BaseModel):
    ac: str
    workers: int = 4
    cross_check: bool = False
    force: bool = False


class QueueAddRequest(BaseModel):
    ac: str
    workers: int = 4
    cross_check: bool = False
    force: bool = False


# ── Individual steps ─────────────────────────────────────────────────────────

@router.post("/split")
async def run_split(req: SplitRequest):
    _check_active(req.ac)
    cmd = [PYTHON, str(SCRIPTS["split"]), "--ac", req.ac]
    if req.force:
        cmd.append("--force")
    job = await job_manager.start_job("split", cmd, req.ac)
    return {"job_id": job.job_id}


@router.post("/extract")
async def run_extract(req: ExtractRequest):
    _check_active(req.ac)
    cmd = [PYTHON, str(SCRIPTS["extract"]), req.ac, "--workers", str(req.workers)]
    if req.part:
        cmd += ["--part", req.part]
    if req.cross_check:
        cmd.append("--cross-check")
    if req.run_validate:
        cmd.append("--validate")
    if req.dry_run:
        cmd.append("--dry-run")
    if req.page:
        cmd += ["--page", req.page]
    if req.limit > 0:
        cmd += ["--limit", str(req.limit)]
    if req.reset:
        cmd += ["--reset", "--yes"]
    job = await job_manager.start_job("extract", cmd, req.ac)
    return {"job_id": job.job_id}


@router.post("/merge")
async def run_merge(req: MergeRequest):
    _check_active(req.ac)
    cmd = [PYTHON, str(SCRIPTS["merge"]), "--ac", req.ac]
    if req.force:
        cmd.append("--force")
    job = await job_manager.start_job("merge", cmd, req.ac)
    return {"job_id": job.job_id}


@router.post("/analyze")
async def run_analyze(req: AnalyzeRequest):
    cmd = [PYTHON, str(SCRIPTS["analyze"]), "--ac", req.ac]
    job = await job_manager.start_job("analyze", cmd, req.ac)
    return {"job_id": job.job_id}


@router.post("/pipeline")
async def run_pipeline(req: PipelineRequest):
    """Chain split → extract → merge for one AC via the queue."""
    _check_active(req.ac)
    queue_manager.add(
        ac=req.ac,
        workers=req.workers,
        cross_check=req.cross_check,
        force=req.force,
    )
    if not queue_manager.is_running():
        queue_manager.start()
    return {"queued": True, "ac": req.ac}


# ── Queue management ─────────────────────────────────────────────────────────

@router.get("/queue")
async def get_queue():
    return {
        "running": queue_manager.is_running(),
        "items": queue_manager.list_items(),
    }


@router.post("/queue")
async def add_to_queue(req: QueueAddRequest):
    queue_manager.add(
        ac=req.ac,
        workers=req.workers,
        cross_check=req.cross_check,
        force=req.force,
    )
    return {"queued": True}


@router.delete("/queue/{ac}")
async def remove_from_queue(ac: str):
    removed = queue_manager.remove(ac)
    return {"removed": removed}


@router.post("/queue/start")
async def start_queue():
    if queue_manager.is_running():
        return {"running": True, "message": "Already running"}
    queue_manager.start()
    return {"running": True}


@router.post("/queue/stop")
async def stop_queue():
    queue_manager.stop()
    return {"running": False, "message": "Will stop after current AC"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_active(ac: str) -> None:
    existing = job_manager.active_job_for_ac(ac)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Job {existing} is already running for {ac}. Kill it first.",
        )
