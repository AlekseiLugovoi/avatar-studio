"""Generate page — two-column layout with per-step validation panels.

Left column: Step 1 (image) + checks panel, Step 2 (audio) + checks panel, Step 3 (prompt).
Right column: bordered result frame + Run button + progress.
"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from app import jobs
from app.validation import (
    AUDIO_EMPTY_CHECKS,
    IMAGE_EMPTY_CHECKS,
    all_passed,
    validate_audio,
    validate_image,
)


MUTED = "#6a737d"  # gray for the constraint text

MOCK_OPTION = "Mock (sample video, ~10s)"
FAL_OPTION = "fal-ai/bytedance/omnihuman"
MODELS = [MOCK_OPTION, FAL_OPTION, "OmniAvatar 1.3B", "OmniAvatar 14B"]

# Map UI label → inference mode passed to generate()
MODEL_TO_MODE = {
    MOCK_OPTION: "mock",
    FAL_OPTION: "fal",
    "OmniAvatar 1.3B": "OmniAvatar 1.3B",
    "OmniAvatar 14B": "OmniAvatar 14B",
}


# Shimmer animation shown inside the result frame while generation is running.
# The 16:9 frame uses the padding-top hack (more reliable than CSS aspect-ratio
# inside Streamlit's bordered container — that overflows by a pixel or two).
LOADING_HTML = """
<style>
@keyframes av_shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@keyframes av_pulse {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 1; }
}
.av-frame {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 6px;
  overflow: hidden;
}
.av-loading {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, #2a323a 0%, #3a4450 50%, #2a323a 100%);
  background-size: 200% 100%;
  animation: av_shimmer 3.2s infinite linear;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: monospace;
  color: #cfd6dd;
  font-size: 13px;
}
.av-loading .dot {
  display: inline-block;
  width: 6px; height: 6px;
  margin: 0 3px;
  border-radius: 50%;
  background: #F11443;
  animation: av_pulse 1.8s infinite;
}
.av-loading .dot:nth-child(2) { animation-delay: .35s; }
.av-loading .dot:nth-child(3) { animation-delay: .7s; }
.av-frame-spacer {
  height: 16px;
}
</style>
<div class="av-frame"><div class="av-loading">
  <span class="dot"></span><span class="dot"></span><span class="dot"></span>
  &nbsp;&nbsp;generating
</div></div>
<div class="av-frame-spacer" aria-hidden="true"></div>
"""

EXPAND_ANIM = """
<style>
[data-testid="stExpanderDetails"] {
  animation: avExpand 1.1s cubic-bezier(.2,.7,.2,1);
  overflow: hidden;
}
@keyframes avExpand {
  from { max-height: 0;     opacity: 0; transform: translateY(-6px); }
  to   { max-height: 800px; opacity: 1; transform: translateY(0); }
}

/* Bordered containers clip any oversized markdown content (our shimmer
   placeholder rendered via st.markdown otherwise spills 2-4px past the
   border on the right). st.video already constrains itself correctly. */
[data-testid="stVerticalBlockBorderWrapper"] {
  overflow: hidden;
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdown"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] > div {
  width: 100%;
}

/* Keep the result frame at a fixed 16:9 shape — the video is letterboxed
   inside instead of resizing the surrounding box. */
[data-testid="stVideo"], .stVideo {
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
[data-testid="stVideo"] video, .stVideo video {
  width: 100% !important;
  height: 100% !important;
  object-fit: contain !important;
}
</style>
"""

EMPTY_HTML = """
<div style="position: relative; box-sizing: border-box; width: 100%; aspect-ratio: 16 / 9; border-radius: 6px; overflow: hidden;">
  <div style="position: absolute; inset: 0; display: flex; align-items: center;
              justify-content: center; font-family: monospace; color: #6a737d; font-size: 13px;">
    Result will appear here
  </div>
</div>
<div style="height: 16px;" aria-hidden="true"></div>
"""


def _check_line(mark: str, name: str, value: str | None, constraint: str) -> str:
    head = f"{mark} **{name}**" if value is None else f"{mark} **{name}:** {value}"
    sub = (
        f"<div style='color:{MUTED}; font-size:12px; "
        f"margin: -4px 0 8px 26px;'>{constraint}</div>"
    )
    return head + sub


def _render_panel(file, validate_fn, empty_checks, preview_fn) -> bool:
    """Single expander structure for both states — empty (file is None) and
    filled. Keeping the same widget identity across reruns avoids ghost rows."""
    has_file = file is not None
    results = validate_fn(file) if has_file else None
    overall = all_passed(results) if results else False
    icon = "✅" if overall else ("❌" if has_file else "⚪")

    with st.expander(f"{icon} Validation", expanded=has_file):
        checks_col, preview_col = st.columns([1, 1])
        with checks_col:
            for i, (name, constraint) in enumerate(empty_checks):
                if results and i < len(results):
                    r = results[i]
                    mark = "✅" if r["passed"] else "❌"
                    st.markdown(
                        _check_line(mark, r["name"], r["value"], r["constraint"]),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        _check_line("⚪", name, None, constraint),
                        unsafe_allow_html=True,
                    )
        with preview_col:
            if has_file:
                preview_fn(file)
    return overall


def show_generate_page() -> None:
    st.markdown(EXPAND_ANIM, unsafe_allow_html=True)
    st.title("Generate")

    left, right = st.columns([1, 1])

    image_ok = False
    audio_ok = False

    # --------------------------------------------------------------------- #
    # Left column — inputs + validation
    # --------------------------------------------------------------------- #
    with left:
        st.subheader("Step 1: Reference Image")
        image_file = st.file_uploader(
            "Reference image",
            type=["jpg", "jpeg", "png", "webp"],
            label_visibility="collapsed",
            key="image_uploader",
        )
        image_ok = _render_panel(
            image_file,
            validate_image,
            IMAGE_EMPTY_CHECKS,
            lambda f: st.image(f, width=200),
        )

        st.subheader("Step 2: Audio")
        audio_file = st.file_uploader(
            "Audio",
            type=["mp3", "wav", "ogg", "webm"],
            label_visibility="collapsed",
            key="audio_uploader",
        )
        audio_ok = _render_panel(
            audio_file,
            validate_audio,
            AUDIO_EMPTY_CHECKS,
            lambda f: st.audio(f),
        )

        st.subheader("Step 3: Behavior Prompt")
        prompt = st.text_area(
            "Behavior prompt (optional)",
            placeholder="e.g. friendly, smiling, sometimes nodding",
            label_visibility="collapsed",
            height=140,
        )

    # --------------------------------------------------------------------- #
    # Right column — preview frame + Run + progress
    # --------------------------------------------------------------------- #
    with right:
        st.subheader("Step 4: Get Result")
        with st.container(border=True):
            result_slot = st.empty()
            last = st.session_state.get("last_result")
            if last and Path(last).exists():
                result_slot.video(last)
            else:
                result_slot.markdown(EMPTY_HTML, unsafe_allow_html=True)

        model_col, run_col = st.columns([3, 1])
        with model_col:
            model = st.selectbox("Model", MODELS, label_visibility="collapsed")
        with run_col:
            submit = st.button("Run", type="primary", use_container_width=True)

        progress_slot = st.empty()
        status_slot = st.empty()

    # --------------------------------------------------------------------- #
    # Submit handler
    # --------------------------------------------------------------------- #
    if submit:
        if not image_file:
            status_slot.error("Upload a reference image.")
        elif not audio_file:
            status_slot.error("Upload audio.")
        elif not image_ok or not audio_ok:
            status_slot.error("Fix validation issues before running.")
        else:
            mode = MODEL_TO_MODE.get(model, "auto")
            result_slot.markdown(LOADING_HTML, unsafe_allow_html=True)
            progress_bar = progress_slot.progress(0, text="Starting…")

            job_id = jobs.submit_job(
                image_file.getvalue(), image_file.type or "image/jpeg",
                audio_file.getvalue(), audio_file.type or "audio/mpeg",
                (prompt or "").strip(), mode,
            )

            # Server-side poll of in-memory job state. Streamlit pushes UI
            # updates over its own WebSocket — no browser polling.
            last_pct = -1.0
            while True:
                job = jobs.get_job(job_id)
                if job is None:
                    break
                if job.progress != last_pct:
                    txt = f"{int(job.progress)}% — {job.message}" if job.message else f"{int(job.progress)}%"
                    progress_bar.progress(min(int(job.progress), 100), text=txt)
                    last_pct = job.progress
                if job.status in ("done", "failed"):
                    break
                time.sleep(0.3)

            if job and job.status == "done" and job.result_path:
                progress_slot.empty()
                status_slot.success(f"✅ Done · `{job_id[:8]}` · {job.elapsed_seconds}s")
                result_slot.video(job.result_path)
                st.session_state.last_result = job.result_path
            else:
                progress_slot.empty()
                result_slot.markdown(EMPTY_HTML, unsafe_allow_html=True)
                err = (job.error if job else "job lost") or "unknown error"
                status_slot.error(f"❌ Failed: {err}")
