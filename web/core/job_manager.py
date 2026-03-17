"""Async job registry — launches subprocesses and streams their output via SSE."""
import asyncio
import os
import signal
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Literal, Optional


JobStatus = Literal["pending", "running", "done", "error", "killed"]


@dataclass
class Job:
    job_id: str
    command: list[str]
    step: str
    ac: Optional[str] = None
    status: JobStatus = "pending"
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    # Ring buffer of last 2000 lines — replayed to late SSE clients
    log_lines: deque = field(default_factory=lambda: deque(maxlen=2000))
    # Live queue consumed by SSE generator; None = sentinel (process exited)
    log_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _process: object = field(default=None, repr=False)
    _pid: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "step": self.step,
            "ac": self.ac,
            "status": self.status,
            "command": " ".join(self.command),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "exit_code": self.exit_code,
            "log_lines": list(self.log_lines),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # Maps ac -> job_id for the currently running job on that AC
        self._active_ac: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict]:
        sorted_jobs = sorted(
            self._jobs.values(), key=lambda j: j.started_at, reverse=True
        )
        return [j.to_dict() for j in sorted_jobs[:limit]]

    def active_job_for_ac(self, ac: str) -> Optional[str]:
        jid = self._active_ac.get(ac)
        if jid and self._jobs.get(jid, None) and self._jobs[jid].status == "running":
            return jid
        return None

    async def start_job(
        self,
        step: str,
        command: list[str],
        ac: Optional[str] = None,
    ) -> Job:
        if ac and self.active_job_for_ac(ac):
            raise RuntimeError(
                f"Job {self._active_ac[ac]} is already running for {ac}"
            )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"{step}_{ac or 'setup'}_{ts}"
        job = Job(job_id=job_id, command=command, step=step, ac=ac)

        self._jobs[job_id] = job
        if ac:
            self._active_ac[ac] = job_id

        # Keep registry from growing unbounded
        if len(self._jobs) > 100:
            oldest_id = sorted(self._jobs, key=lambda k: self._jobs[k].started_at)[0]
            if self._jobs[oldest_id].status != "running":
                del self._jobs[oldest_id]

        asyncio.create_task(self._run(job))
        return job

    async def kill_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status != "running":
            return False
        try:
            if sys.platform == "win32":
                import subprocess as _sp
                _sp.call(
                    ["taskkill", "/F", "/T", "/PID", str(job._pid)],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                )
            else:
                os.killpg(os.getpgid(job._pid), signal.SIGTERM)
        except Exception:
            pass
        job.status = "killed"
        job.finished_at = datetime.now()
        await job.log_queue.put(None)  # wake SSE generator
        return True

    async def stream_logs(self, job_id: str) -> AsyncIterator[str]:
        """Yields SSE-formatted lines; replays buffer for late clients."""
        job = self._jobs.get(job_id)
        if not job:
            yield "data: [job not found]\n\n"
            return

        # Replay buffered lines
        for line in list(job.log_lines):
            yield f"data: {line}\n\n"

        # If job already finished, we're done
        if job.status not in ("running", "pending"):
            yield "event: done\ndata: {}\n\n"
            return

        # Stream live output
        while True:
            try:
                line = await asyncio.wait_for(job.log_queue.get(), timeout=15.0)
                if line is None:  # sentinel: process exited
                    break
                yield f"data: {line}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                if job.status not in ("running", "pending"):
                    break

        yield "event: done\ndata: {}\n\n"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(self, job: Job) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "env": env,
        }

        if sys.platform == "win32":
            import subprocess as _sp
            kwargs["creationflags"] = _sp.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        try:
            proc = await asyncio.create_subprocess_exec(*job.command, **kwargs)
        except Exception as exc:
            job.status = "error"
            job.finished_at = datetime.now()
            msg = f"[launch error] {exc}"
            job.log_lines.append(msg)
            await job.log_queue.put(msg)
            await job.log_queue.put(None)
            return

        job._process = proc
        job._pid = proc.pid
        job.status = "running"

        # Read lines until EOF
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                job.log_lines.append(line)
                await job.log_queue.put(line)
        except Exception as exc:
            err = f"[reader error] {exc}"
            job.log_lines.append(err)
            await job.log_queue.put(err)

        await proc.wait()
        job.exit_code = proc.returncode
        job.finished_at = datetime.now()
        job.status = "done" if job.exit_code == 0 else "error"
        await job.log_queue.put(None)  # signal SSE consumers


# Module-level singleton shared by all routes
job_manager = JobManager()
