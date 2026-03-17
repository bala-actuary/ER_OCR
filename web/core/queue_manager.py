"""Overnight AC queue — runs split→extract→merge for each AC sequentially."""
import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from .job_manager import job_manager
from ..api.deps import PYTHON, SCRIPTS

QUEUE_STATE_FILE = Path(__file__).parent.parent / "queue_state.json"

QueueItemStatus = Literal["waiting", "running", "done", "error", "skipped"]


@dataclass
class QueueItem:
    ac: str
    workers: int = 4
    cross_check: bool = False
    force: bool = False
    status: QueueItemStatus = "waiting"
    current_step: str = ""
    error_msg: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class QueueManager:
    def __init__(self) -> None:
        self._items: list[QueueItem] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_items(self) -> list[dict]:
        return [i.to_dict() for i in self._items]

    def add(self, ac: str, workers: int = 4, cross_check: bool = False, force: bool = False) -> None:
        # Avoid duplicates
        if any(i.ac == ac and i.status == "waiting" for i in self._items):
            return
        self._items.append(QueueItem(ac=ac, workers=workers, cross_check=cross_check, force=force))
        self._save()

    def remove(self, ac: str) -> bool:
        before = len(self._items)
        self._items = [i for i in self._items if not (i.ac == ac and i.status == "waiting")]
        self._save()
        return len(self._items) < before

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_queue())

    def stop(self) -> None:
        """Request graceful stop — current AC will finish, then queue halts."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_queue(self) -> None:
        try:
            for item in self._items:
                if not self._running:
                    break
                if item.status != "waiting":
                    continue

                item.status = "running"
                item.started_at = datetime.now().isoformat()
                self._save()

                try:
                    await self._run_pipeline(item)
                    item.status = "done"
                except Exception as exc:
                    item.status = "error"
                    item.error_msg = str(exc)

                item.finished_at = datetime.now().isoformat()
                self._save()

                # Send browser notification hint (picked up by SSE polling)
                self._notify(item)
        finally:
            self._running = False
            self._save()

    async def _run_pipeline(self, item: QueueItem) -> None:
        steps = [
            ("split",   [PYTHON, str(SCRIPTS["split"]),   "--ac", item.ac]
                        + (["--force"] if item.force else [])),
            ("extract", [PYTHON, str(SCRIPTS["extract"]), item.ac,
                         "--workers", str(item.workers)]
                        + (["--cross-check"] if item.cross_check else [])),
            ("merge",   [PYTHON, str(SCRIPTS["merge"]),   "--ac", item.ac]
                        + (["--force"] if item.force else [])),
        ]

        for step_name, cmd in steps:
            item.current_step = step_name
            self._save()

            job = await job_manager.start_job(step=step_name, command=cmd, ac=item.ac)

            # Wait for job to finish
            while job.status in ("pending", "running"):
                await asyncio.sleep(1)

            if job.status == "error":
                raise RuntimeError(f"{step_name} failed (exit {job.exit_code})")

        item.current_step = ""

    def _notify(self, item: QueueItem) -> None:
        """Write a notification hint to queue_state.json so the SSE endpoint can relay it."""
        # The frontend polls /api/queue; status change is sufficient notification.
        pass

    def _save(self) -> None:
        try:
            data = {
                "running": self._running,
                "items": [i.to_dict() for i in self._items],
            }
            QUEUE_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        if not QUEUE_STATE_FILE.exists():
            return
        try:
            data = json.loads(QUEUE_STATE_FILE.read_text(encoding="utf-8"))
            for d in data.get("items", []):
                item = QueueItem(**{k: v for k, v in d.items() if k in QueueItem.__dataclass_fields__})
                # Reset running items to waiting on server restart
                if item.status == "running":
                    item.status = "waiting"
                    item.current_step = ""
                self._items.append(item)
        except Exception:
            pass


# Module-level singleton
queue_manager = QueueManager()
