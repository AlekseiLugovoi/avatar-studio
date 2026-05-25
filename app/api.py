"""REST API — thin wrapper over app.jobs.

Auto-generated Swagger lives at /docs. The same job state is shared with the
Streamlit UI (both import app.jobs)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import jobs


app = FastAPI(
    title="Avatar Studio API",
    description="Submit talking-avatar generation jobs, poll status, fetch results.",
    version="0.1.0",
)


@app.post("/api/jobs", tags=["jobs"])
async def create_job(
    image: UploadFile = File(..., description="Reference image (JPEG / PNG / WebP)"),
    audio: UploadFile = File(..., description="Audio track (MP3 / WAV / OGG / WebM)"),
    prompt: str = Form("", description="Optional behavior prompt"),
    mode: str = Form("auto", description="mock | fal | OmniAvatar 1.3B | OmniAvatar 14B | auto"),
):
    """Submit a new generation job. Returns the job id; the worker runs
    asynchronously in a single-slot thread pool."""
    job_id = jobs.submit_job(
        await image.read(), image.content_type or "image/jpeg",
        await audio.read(), audio.content_type or "audio/mpeg",
        prompt.strip(), mode,
    )
    return {"job_id": job_id}


@app.get("/api/jobs", tags=["jobs"])
def list_jobs():
    """All jobs known to this process, newest first."""
    return [j.public() for j in jobs.list_jobs()]


@app.get("/api/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.public()


@app.get("/api/jobs/{job_id}/result", tags=["jobs"])
def get_result(job_id: str):
    """Download the generated mp4. 404 until the job is done."""
    job = jobs.get_job(job_id)
    if not job or not job.result_path:
        raise HTTPException(404, "no result yet")
    path = Path(job.result_path)
    if not path.exists():
        raise HTTPException(410, "result file missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
