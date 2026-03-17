"""Dependency check and installation endpoints."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..core.dep_checker import check_all
from ..core.installer import pip_install_command, winget_tesseract_command, tessdata_download_command
from ..core.job_manager import job_manager

router = APIRouter(tags=["setup"])


@router.get("/check")
async def setup_check():
    """Run all dependency checks synchronously and return status."""
    return check_all()


@router.post("/install/packages")
async def install_packages():
    """pip install -r requirements.txt — streams output via job."""
    cmd = pip_install_command()
    job = await job_manager.start_job(step="install_packages", command=cmd, ac=None)
    return {"job_id": job.job_id}


@router.post("/install/tesseract")
async def install_tesseract():
    """winget install Tesseract — streams output via job."""
    cmd = winget_tesseract_command()
    job = await job_manager.start_job(step="install_tesseract", command=cmd, ac=None)
    return {"job_id": job.job_id}


@router.post("/install/tessdata")
async def install_tessdata():
    """Download tam.traineddata — streams output via job."""
    cmd = tessdata_download_command()
    job = await job_manager.start_job(step="install_tessdata", command=cmd, ac=None)
    return {"job_id": job.job_id}
