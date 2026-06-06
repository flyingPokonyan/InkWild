"""Append-only JSONL writer for the case-board research mode.

Enabled by ``settings.case_board_research``. Each turn the Director may
emit an optional ``research_note`` capturing what info would be worth
showing to the player; we append one JSON line per turn to
``{settings.case_board_research_dir}/{session_id}.jsonl`` so the
auto_play harness (and any post-hoc analyzer) can cluster signals
across sessions without joining the live DB.

Best-effort: failures are logged + swallowed so research never breaks
a real turn.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def _research_dir() -> Path | None:
    try:
        from config import settings
    except Exception:  # noqa: BLE001
        return None
    if not getattr(settings, "case_board_research", False):
        return None
    base = Path(getattr(settings, "case_board_research_dir", "research"))
    if not base.is_absolute():
        # Resolve relative to the backend working dir at runtime — the
        # harness always starts backend from backend/.
        base = Path.cwd() / base
    return base


def append_turn_note(
    session_id: str,
    round_number: int,
    note: dict,
    *,
    player_input: str | None = None,
    script_type: str | None = None,
    game_mode: str | None = None,
    extras: dict[str, Any] | None = None,
) -> None:
    """Append one JSONL row for this turn. No-op if research mode off."""
    base = _research_dir()
    if base is None or not note:
        return
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{session_id}.jsonl"
        row = {
            "ts": time.time(),
            "session_id": session_id,
            "round": round_number,
            "player_input": player_input,
            "script_type": script_type,
            "game_mode": game_mode,
            "note": note,
        }
        if extras:
            row["extras"] = extras
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_log_write_failed", error=str(exc), sid=session_id)


def write_summary(session_id: str, content: str) -> Path | None:
    """Write the end-of-session synthesis markdown. Returns the path."""
    base = _research_dir()
    if base is None:
        return None
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{session_id}-summary.md"
        path.write_text(content, encoding="utf-8")
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_summary_write_failed", error=str(exc), sid=session_id)
        return None


__all__ = ["append_turn_note", "write_summary"]
