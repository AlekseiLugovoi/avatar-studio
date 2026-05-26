"""Inference: fal.ai (when FAL_API_KEY set) or mock (offline sample).

fal.ai's omnihuman endpoint requires real URLs for image_url / audio_url; data-URLs
are rejected with `file_download_error`. We upload inputs through fal's storage
API (via fal_client) to get back HTTPS URLs, then submit the job.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import requests

log = logging.getLogger(__name__)

OUTPUTS = Path("outputs")
MODELS_DIR = Path("models")
FAL_KEY = os.getenv("FAL_API_KEY", "").strip() or os.getenv("FAL_KEY", "").strip()
FAL_MODEL = "fal-ai/bytedance/omnihuman"

# Reference: https://github.com/Omni-Avatar/OmniAvatar
OMNIAVATAR_VARIANTS = {
    "OmniAvatar 1.3B": {
        "repo_id": "OmniAvatar/OmniAvatar-1.3B",
        "vram_gb": 8,
    },
    "OmniAvatar 14B": {
        "repo_id": "OmniAvatar/OmniAvatar-14B",
        "vram_gb": 32,
    },
}

# fal_client reads FAL_KEY from env. Mirror our FAL_API_KEY into it so users only
# need to set one variable in .env.
if FAL_KEY:
    os.environ["FAL_KEY"] = FAL_KEY

ProgressCb = Callable[[float, str], None]


def run_fal(image_bytes, image_mime, audio_bytes, audio_mime, prompt, on_progress: ProgressCb) -> bytes:
    """Upload inputs, subscribe to fal queue, return video bytes."""
    import fal_client  # imported lazily so mock-only setups don't need it

    on_progress(5, "uploading image")
    image_url = fal_client.upload(image_bytes, content_type=image_mime)
    on_progress(10, "uploading audio")
    audio_url = fal_client.upload(audio_bytes, content_type=audio_mime)

    arguments = {"image_url": image_url, "audio_url": audio_url}
    if prompt:
        arguments["prompt"] = prompt

    on_progress(15, "submitting to fal queue")

    def on_queue_update(update):
        if isinstance(update, fal_client.Queued):
            on_progress(20, f"in queue (position {update.position})")
        elif isinstance(update, fal_client.InProgress):
            last = ""
            if update.logs:
                last = (update.logs[-1].get("message") or "")[:100]
            on_progress(60, last or "running inference")

    result = fal_client.subscribe(
        FAL_MODEL,
        arguments=arguments,
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_url = (result.get("video") or {}).get("url")
    if not video_url:
        raise RuntimeError(f"No video URL in fal response: {result}")

    on_progress(95, "downloading result")
    return requests.get(video_url, timeout=120).content


# --------------------------------------------------------------------------- #
# OmniAvatar local pipeline (Stage 2 — STUBS for now)
# --------------------------------------------------------------------------- #


def download_omniavatar_weights(variant: str, cache_dir: Path = MODELS_DIR) -> Path:
    """STUB. On the GPU server (Stage 2 of the assignment) this downloads the
    OmniAvatar checkpoint from HuggingFace into ``cache_dir`` and returns the
    local path. Reference repo: https://github.com/Omni-Avatar/OmniAvatar

    Real implementation will look like::

        from huggingface_hub import snapshot_download
        return Path(snapshot_download(cfg["repo_id"], cache_dir=cache_dir))
    """
    cfg = OMNIAVATAR_VARIANTS[variant]
    log.info(
        "STUB download_omniavatar_weights: would fetch %s (~%d GB VRAM) into %s",
        cfg["repo_id"], cfg["vram_gb"], cache_dir,
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / variant.replace(" ", "_")


def load_omniavatar_pipeline(variant: str):
    """STUB. Loads the OmniAvatar model into GPU memory and returns a callable
    inference pipeline. On Stage 2 this becomes a torch/diffusers model load
    followed by ``.to("cuda")``."""
    log.info("STUB load_omniavatar_pipeline: would load %s on GPU", variant)
    return None


def run_omniavatar(
    variant: str,
    image_bytes: bytes,
    image_mime: str,
    audio_bytes: bytes,
    audio_mime: str,
    prompt: str,
    on_progress: ProgressCb,
    params: Optional[dict] = None,
) -> bytes:
    """STUB. Runs local OmniAvatar inference. For now falls back to the mock
    backend so the UI flow works end-to-end. On Stage 2::

        weights = download_omniavatar_weights(variant)
        pipeline = load_omniavatar_pipeline(variant)
        return pipeline(
            image=image_bytes, audio=audio_bytes, prompt=prompt,
            num_steps=params.get("num_steps", 30),
            guidance_scale=params.get("guidance_scale", 5.0),
            audio_scale=params.get("audio_scale", 3.0),
        )
    """
    log.warning(
        "STUB run_omniavatar(variant=%s, params=%s) — running mock fallback",
        variant, params or {},
    )
    return run_mock(on_progress)


# --------------------------------------------------------------------------- #
# Mock — works offline, returns a cached public sample MP4.
# --------------------------------------------------------------------------- #


def _ensure_sample_mp4(path: Path) -> bytes:
    """Generate a 3-second 320x240 black H.264 MP4 once and cache it. Uses the
    portable ffmpeg binary bundled with imageio-ffmpeg, so no system ffmpeg /
    no internet is required."""
    if path.exists() and path.stat().st_size > 1024:
        return path.read_bytes()
    try:
        import imageio.v3 as iio
        import numpy as np
        frames = np.zeros((90, 240, 320, 3), dtype=np.uint8)  # 3s @ 30fps
        iio.imwrite(str(path), frames, fps=30, codec="libx264")
        return path.read_bytes()
    except Exception as e:
        log.warning("failed to generate sample mp4: %s", e)
        return b""


def run_mock(on_progress: ProgressCb) -> bytes:
    """Imitate inference (~10 seconds), return a locally-generated black MP4."""
    steps = 20
    step_sleep = float(os.getenv("MOCK_STEP_SECONDS", "0.5"))
    for i in range(1, steps + 1):
        time.sleep(step_sleep)
        on_progress(i * 100 / steps, f"mock step {i}/{steps}")

    OUTPUTS.mkdir(exist_ok=True)
    return _ensure_sample_mp4(OUTPUTS / ".sample_3s_black.mp4")


def generate(
    image_bytes,
    image_mime,
    audio_bytes,
    audio_mime,
    prompt,
    on_progress: ProgressCb,
    mode: str = "auto",
    params: Optional[dict] = None,
) -> bytes:
    """Dispatch by ``mode``:
      - "mock" → run_mock (params ignored)
      - "fal"  → run_fal (omnihuman black-box: image+audio only, params ignored)
      - "OmniAvatar 1.3B" / "OmniAvatar 14B" → run_omniavatar with params
        (num_steps, guidance_scale, audio_scale; currently STUB falls back to mock)
      - "auto" → fal if FAL_KEY is set, otherwise mock
    """
    params = params or {}
    if mode == "mock":
        return run_mock(on_progress)
    if mode in OMNIAVATAR_VARIANTS:
        return run_omniavatar(
            mode, image_bytes, image_mime, audio_bytes, audio_mime, prompt, on_progress,
            params=params,
        )
    if mode == "fal" or (mode == "auto" and FAL_KEY):
        # fal/bytedance/omnihuman accepts only image_url + audio_url — no
        # tunable knobs exposed. Params are intentionally dropped here.
        return run_fal(image_bytes, image_mime, audio_bytes, audio_mime, prompt, on_progress)
    return run_mock(on_progress)
