"""Electoral Roll OCR — Web UI (FastAPI application)."""
import socket
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_setup, routes_jobs, routes_workflow, routes_files

app = FastAPI(
    title="Electoral Roll OCR",
    version="1.3",
    docs_url="/api/docs",
    redoc_url=None,
)

# Static files (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API routers
app.include_router(routes_setup.router,    prefix="/api/setup")
app.include_router(routes_jobs.router,     prefix="/api/jobs")
app.include_router(routes_workflow.router, prefix="/api/jobs")
app.include_router(routes_files.router,    prefix="/api")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def find_free_port(preferred: int = 7000) -> int:
    """Return preferred port if bindable, else try next 9."""
    for port in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


if __name__ == "__main__":
    import uvicorn
    port = find_free_port(7000)
    print(f"\n  Electoral Roll OCR UI -> http://localhost:{port}\n")
    uvicorn.run("web.app:app", host="127.0.0.1", port=port, reload=False)
