"""In-memory job state + single-worker thread pool. Shared between the
Streamlit UI (direct calls) and the REST API (HTTP wrapper over the same
functions). One source of truth, no duplication."""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

from app.history import add_history
from app.inference import OUTPUTS, generate

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    status: str = "queued"        # queued | running | done | failed
    progress: float = 0.0
    message: str = ""
    prompt: str = ""
    mode: str = "auto"
    params: dict = field(default_factory=dict)
    error: Optional[str] = None
    result_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None

    def public(self) -> dict:
        d = asdict(self)
        d.pop("result_path", None)
        d["result_url"] = f"/api/jobs/{self.id}/result" if self.status == "done" else None
        return d


_jobs: dict[str, Job] = {}
# Per-job wakeup events: worker calls .set() on every progress update and on
# final status; consumers (the UI loop) `wait_for_update()` instead of polling.
# Kept out of the Job dataclass because asdict() can't deepcopy a Lock.
_events: dict[str, threading.Event] = {}
_lock = threading.Lock()
# Configurable pool size. For real GPU inference keep at 1 (single device
# can't run two models in parallel without OOM); for CPU-mock or multi-GPU
# setups raise it. The pool itself is a FIFO queue — parallel submits wait
# their turn behind whatever is currently running.
_WORKERS = max(1, int(os.getenv("WORKER_CONCURRENCY", "1")))
_executor = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="job-worker")
log.info("job pool started with %d worker(s)", _WORKERS)


def submit_job(
    image_bytes: bytes, image_mime: str,
    audio_bytes: bytes, audio_mime: str,
    prompt: str,
    mode: str = "auto",
    params: Optional[dict] = None,
) -> str:
    params = params or {}
    job = Job(id=uuid4().hex, prompt=prompt, mode=mode, params=params)
    with _lock:
        _jobs[job.id] = job
        _events[job.id] = threading.Event()
    _executor.submit(
        _run_job, job.id,
        image_bytes, image_mime, audio_bytes, audio_mime, prompt, mode, params,
    )
    log.info("job %s submitted (mode=%s, params=%s)", job.id, mode, params)
    return job.id


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def wait_for_update(job_id: str, timeout: float = 30.0) -> None:
    """Block until the worker pushes any state change for this job (or until
    timeout fires as a sanity bound). True event-based wakeup — no polling on
    the server side. State is always re-read from the dict by the caller."""
    ev = _events.get(job_id)
    if ev is None:
        return
    ev.wait(timeout)
    ev.clear()


def _run_job(job_id, image_bytes, image_mime, audio_bytes, audio_mime, prompt, mode, params):
    job = _jobs[job_id]
    event = _events.get(job_id)
    job.status = "running"
    job.started_at = datetime.utcnow().isoformat()
    started = time.time()

    def on_progress(pct: float, msg: str = "") -> None:
        job.progress = max(0.0, min(100.0, float(pct)))
        job.message = msg or ""
        if event is not None:
            event.set()  # push: wake any UI waiter immediately

    try:
        video_bytes = generate(
            image_bytes, image_mime, audio_bytes, audio_mime, prompt, on_progress,
            mode=mode, params=params,
        )
        if not video_bytes:
            raise RuntimeError("empty video bytes returned")

        OUTPUTS.mkdir(exist_ok=True)
        out_path = OUTPUTS / f"{job_id}.mp4"
        out_path.write_bytes(video_bytes)

        job.result_path = str(out_path)
        job.progress = 100.0
        job.status = "done"
        job.finished_at = datetime.utcnow().isoformat()
        job.elapsed_seconds = round(time.time() - started, 1)

        add_history({
            "id": job_id,
            "filename": out_path.name,
            "prompt": prompt,
            "created_at": job.created_at,
            "elapsed_seconds": job.elapsed_seconds,
        })
        log.info("job %s done in %.1fs", job_id, job.elapsed_seconds)
    except Exception as e:
        job.status = "failed"
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = datetime.utcnow().isoformat()
        job.elapsed_seconds = round(time.time() - started, 1)
        log.exception("job %s failed", job_id)
    finally:
        if event is not None:
            event.set()  # final wake so waiters see done/failed without timeout
