"""In-memory job state + single-worker thread pool. Shared between the
Streamlit UI (direct calls) and the REST API (HTTP wrapper over the same
functions). One source of truth, no duplication."""

from __future__ import annotations

import logging
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
_lock = threading.Lock()
# max_workers=1 → real queue; GPU inference must be serialized. Parallel
# submits from the API queue up behind whatever is running.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job-worker")


def submit_job(
    image_bytes: bytes, image_mime: str,
    audio_bytes: bytes, audio_mime: str,
    prompt: str,
    mode: str = "auto",
) -> str:
    job = Job(id=uuid4().hex, prompt=prompt, mode=mode)
    with _lock:
        _jobs[job.id] = job
    _executor.submit(
        _run_job, job.id,
        image_bytes, image_mime, audio_bytes, audio_mime, prompt, mode,
    )
    log.info("job %s submitted (mode=%s)", job.id, mode)
    return job.id


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def _run_job(job_id, image_bytes, image_mime, audio_bytes, audio_mime, prompt, mode):
    job = _jobs[job_id]
    job.status = "running"
    job.started_at = datetime.utcnow().isoformat()
    started = time.time()

    def on_progress(pct: float, msg: str = "") -> None:
        job.progress = max(0.0, min(100.0, float(pct)))
        job.message = msg or ""

    try:
        video_bytes = generate(
            image_bytes, image_mime, audio_bytes, audio_mime, prompt, on_progress, mode=mode,
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
