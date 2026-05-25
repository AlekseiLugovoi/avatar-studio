"""Streamlit entrypoint. Sidebar = title + description + gallery. Single page.
Also spawns the FastAPI server in a background thread so the REST API and the
UI share the same in-memory job state."""

import logging
import os
import sys
import threading
from itertools import groupby
from pathlib import Path

# Make `app` importable when launched as `streamlit run app/main.py` —
# Streamlit puts the script's dir on sys.path, not the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from app.history import clear_history, load_history
from app.inference import OUTPUTS
from app.pages import show_generate_page


st.set_page_config(page_title="Avatar Studio", page_icon="🎬", layout="wide")


@st.cache_resource
def _start_api_server():
    """Run FastAPI alongside Streamlit in a daemon thread. Cached so it only
    starts once per process (Streamlit reruns the script on every interaction)."""
    import uvicorn
    from app.api import app as api_app

    port = int(os.getenv("API_PORT", "7860"))
    config = uvicorn.Config(api_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="fastapi").start()
    return server


_start_api_server()


def render_sidebar() -> None:
    with st.sidebar:
        st.title("🎬 Avatar Studio")
        st.caption(
            "Talking-avatar video generation from a reference image, audio "
            "and an optional behavior prompt."
        )
        st.divider()

        history = load_history()
        items = [(it, OUTPUTS / it["filename"]) for it in history]
        items = [(it, p) for it, p in items if p.exists()]

        title_col, clear_col = st.columns([5, 1])
        with title_col:
            st.subheader("Gallery")
        with clear_col:
            if items and st.button(
                "🗑",
                key="clear_gallery",
                help="Clear all generated videos",
                use_container_width=True,
            ):
                clear_history()
                st.session_state.pop("last_result", None)
                st.rerun()

        if not items:
            st.caption("No generated videos yet.")
            return

        # Group consecutive entries by date (history is already sorted newest first).
        def date_key(pair):
            return (pair[0].get("created_at") or "")[:10] or "—"

        for idx, (day, group) in enumerate(groupby(items, key=date_key)):
            group = list(group)
            with st.expander(f"{day}  ·  {len(group)}", expanded=(idx == 0)):
                cols = st.columns(2)
                for i, (item, path) in enumerate(group):
                    with cols[i % 2]:
                        st.video(str(path))
                        if item.get("prompt"):
                            st.caption(item["prompt"][:40])


render_sidebar()
show_generate_page()
