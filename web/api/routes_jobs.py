"""Job status, SSE log streaming, and job kill endpoints."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..core.job_manager import job_manager

router = APIRouter(tags=["jobs"])


@router.get("")
async def list_jobs():
    return job_manager.list_jobs()


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/{job_id}/stream")
async def stream_job(job_id: str):
    """SSE endpoint — streams stdout/stderr of a running job.
    Replays buffered lines for clients that connect after the job starts.
    """
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        job_manager.stream_logs(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind a proxy
        },
    )


@router.delete("/{job_id}")
async def kill_job(job_id: str):
    killed = await job_manager.kill_job(job_id)
    if not killed:
        raise HTTPException(status_code=400, detail="Job not running or not found")
    return {"killed": True}
