"""Generation history persisted as a JSON file inside outputs/."""

from __future__ import annotations

import json
from pathlib import Path

OUTPUTS = Path("outputs")
HISTORY_FILE = OUTPUTS / "_history.json"


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def add_history(item: dict) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    items = load_history()
    items.insert(0, item)
    HISTORY_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def clear_history() -> int:
    """Wipe history.json and unlink every referenced mp4 from disk. Returns
    the number of files removed."""
    items = load_history()
    for i in items:
        try:
            (OUTPUTS / i.get("filename", "")).unlink(missing_ok=True)
        except OSError:
            pass
    HISTORY_FILE.unlink(missing_ok=True)
    return len(items)
