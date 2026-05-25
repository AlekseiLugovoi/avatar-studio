"""Input file validation. Each check has a name (Size / Format / Dimensions /
Duration), the actual measured value, and the constraint shown in muted color.
The list of checks doubles as the empty-state row labels."""

from __future__ import annotations

import io
from pathlib import Path
from typing import TypedDict


MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_DIM = 1800
MAX_AUDIO_SECONDS = 10.0
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
ALLOWED_AUDIO_EXT = {"mp3", "wav", "ogg", "webm"}

SIZE_CONSTRAINT = "max 50 MB"
IMAGE_FORMAT_CONSTRAINT = "available: JPEG / PNG / WebP"
IMAGE_DIM_CONSTRAINT = f"max {MAX_IMAGE_DIM}×{MAX_IMAGE_DIM}"
AUDIO_FORMAT_CONSTRAINT = "available: WAV / MP3 / OGG / WebM"
AUDIO_DURATION_CONSTRAINT = f"max {int(MAX_AUDIO_SECONDS)} s"

# (name, constraint) — rendered as ⚪ "Name (constraint)" when no file uploaded.
IMAGE_EMPTY_CHECKS = [
    ("Size", SIZE_CONSTRAINT),
    ("Format", IMAGE_FORMAT_CONSTRAINT),
    ("Dimensions", IMAGE_DIM_CONSTRAINT),
]
AUDIO_EMPTY_CHECKS = [
    ("Size", SIZE_CONSTRAINT),
    ("Format", AUDIO_FORMAT_CONSTRAINT),
    ("Duration", AUDIO_DURATION_CONSTRAINT),
]


class CheckResult(TypedDict):
    name: str
    value: str
    constraint: str
    passed: bool


def validate_image(file) -> list[CheckResult]:
    data = file.getvalue()
    results: list[CheckResult] = [
        {
            "name": "Size",
            "value": f"{len(data) / (1024 * 1024):.2f} MB",
            "constraint": SIZE_CONSTRAINT,
            "passed": len(data) <= MAX_FILE_BYTES,
        },
        _ext_result(file.name, ALLOWED_IMAGE_EXT, IMAGE_FORMAT_CONSTRAINT),
    ]
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        results.append({
            "name": "Dimensions",
            "value": f"{w}×{h}",
            "constraint": IMAGE_DIM_CONSTRAINT,
            "passed": w <= MAX_IMAGE_DIM and h <= MAX_IMAGE_DIM,
        })
    except Exception as e:
        results.append({
            "name": "Dimensions",
            "value": f"failed to read ({e})",
            "constraint": IMAGE_DIM_CONSTRAINT,
            "passed": False,
        })
    return results


def validate_audio(file) -> list[CheckResult]:
    data = file.getvalue()
    results: list[CheckResult] = [
        {
            "name": "Size",
            "value": f"{len(data) / (1024 * 1024):.2f} MB",
            "constraint": SIZE_CONSTRAINT,
            "passed": len(data) <= MAX_FILE_BYTES,
        },
        _ext_result(file.name, ALLOWED_AUDIO_EXT, AUDIO_FORMAT_CONSTRAINT),
    ]
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(io.BytesIO(data))
        if audio is None or audio.info is None:
            raise ValueError("could not parse audio")
        duration = float(audio.info.length)
        results.append({
            "name": "Duration",
            "value": f"{duration:.1f} s",
            "constraint": AUDIO_DURATION_CONSTRAINT,
            "passed": duration <= MAX_AUDIO_SECONDS,
        })
    except Exception as e:
        results.append({
            "name": "Duration",
            "value": f"failed to read ({e})",
            "constraint": AUDIO_DURATION_CONSTRAINT,
            "passed": False,
        })
    return results


def _ext_result(filename: str, allowed: set[str], constraint: str) -> CheckResult:
    ext = Path(filename or "").suffix.lower().lstrip(".")
    return {
        "name": "Format",
        "value": ext.upper() or "(no extension)",
        "constraint": constraint,
        "passed": ext in allowed,
    }


def all_passed(results: list[CheckResult]) -> bool:
    return all(r["passed"] for r in results)
