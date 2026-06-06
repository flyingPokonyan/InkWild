"""Multi-step player action segmentation — runtime v2 §11.

BUG #21: "潜入工棚取木匣 → 藏入怀中携出工地 → 回大理寺再细察" got compressed
into a single montage by narrator, with the last step being silently
performed by an NPC. The engine-level fix is to detect multi-step
declarations and only execute the first step this turn, parking the rest
in ``game_state.pending_player_segments`` so the next turn re-pops them.

Pure regex/heuristics — no LLM.
"""

from __future__ import annotations

import re

# Arrow separators (full-width or half-width).
_ARROW_RE = re.compile(r"\s*(?:→|⇒|->|=>)\s*")
# Numbered list at line start, e.g. "1. 取匣  2. 藏入怀中  3. 回大理寺"
_NUMBERED_RE = re.compile(r"(?<!\d)(?:\d+[.、])\s*")
# Sequence connectives — "然后/再/之后/接着" etc. We split when these appear
# AFTER at least 4 chars of content and have at least 4 chars of content
# AFTER them; otherwise it's a transition particle inside one step, not a
# step boundary.
_SEQUENCE_PARTICLES: tuple[str, ...] = (
    "然后",
    "再",  # treated as soft particle — require longer pre/post
    "之后",
    "接着",
    "接下来",
    "随后",
    "完了",
    "完了之后",
)

# Minimum length of each side of a connective to be considered a step.
_MIN_STEP_CHAR = 4
# Cap on number of segments — past this we lump the tail back into one
# segment to keep the queue bounded.
MAX_SEGMENTS = 5


def _split_by_arrow(text: str) -> list[str]:
    parts = [p.strip() for p in _ARROW_RE.split(text) if p.strip()]
    return parts


def _split_by_numbered(text: str) -> list[str]:
    """Split "1. X 2. Y 3. Z" into ["X", "Y", "Z"].

    Returns the original text wrapped in a list if no numbered markers
    appear at the front of at least 2 distinct segments.
    """
    matches = list(_NUMBERED_RE.finditer(text))
    # Require at least 2 numbered markers, the first within the leading 6
    # chars (otherwise it's a content number like "在第 3 间屋子").
    if len(matches) < 2 or matches[0].start() > 6:
        return [text.strip()]

    segments: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip(" ，。；")
        if chunk:
            segments.append(chunk)
    return segments if len(segments) >= 2 else [text.strip()]


def _split_by_particles(text: str) -> list[str]:
    """Split on sequence particles when both sides have ≥ _MIN_STEP_CHAR.

    Walks left-to-right so the first valid split point is the cut. We
    deliberately recurse: each chunk gets re-fed so a 4-step input still
    splits correctly. Termination: every recursive call splits at a
    position strictly inside the input and yields strictly shorter chunks.
    """
    text = text.strip()
    if not text:
        return []

    for particle in _SEQUENCE_PARTICLES:
        # Find the earliest particle that has enough content on both sides.
        search_from = _MIN_STEP_CHAR
        while True:
            idx = text.find(particle, search_from)
            if idx == -1:
                break
            left = text[:idx].strip(" ，。；,.;")
            right = text[idx + len(particle) :].strip(" ，。；,.;")
            if len(left) >= _MIN_STEP_CHAR and len(right) >= _MIN_STEP_CHAR:
                # Recurse on the right side only — left is already the first
                # step. Avoids cascading the same particle search on left
                # which would just rediscover the same split.
                return [left, *_split_by_particles(right)]
            search_from = idx + len(particle)

    return [text]


def segment_player_action(text: str | None) -> list[str]:
    """Return the player's input split into discrete action steps.

    Single-step inputs return ``[text]`` (or ``[]`` for empty). Multi-step
    inputs return 2+ entries; orchestrator executes [0] this turn and
    parks [1:] in ``pending_player_segments``.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    # 1. Arrow split has highest priority (it's an explicit "step" marker).
    arrow_parts = _split_by_arrow(raw)
    if len(arrow_parts) >= 2:
        return arrow_parts[:MAX_SEGMENTS]

    # 2. Numbered list "1. X 2. Y" — also explicit.
    numbered_parts = _split_by_numbered(raw)
    if len(numbered_parts) >= 2:
        return numbered_parts[:MAX_SEGMENTS]

    # 3. Sequence particles ("然后" / "再" / "之后" / ...). Soft: needs both
    # sides to be substantive.
    particle_parts = _split_by_particles(raw)
    if len(particle_parts) >= 2:
        return particle_parts[:MAX_SEGMENTS]

    return [raw]


def consume_pending_segment(
    pending: list[str], current_input: str | None
) -> tuple[str | None, list[str], bool]:
    """Decide what to play this turn given pending segments + new input.

    Returns ``(effective_input, new_pending, used_pending)``:
    - If current_input is empty / a "continue"-style prompt → pop pending[0]
      and use it; new_pending is pending[1:]; used_pending=True.
    - If current_input is substantive → ignore pending entirely (player
      changed their mind); new_pending=[]; used_pending=False.
    - If pending is empty and current_input is empty → ("", [], False).
    """
    raw = (current_input or "").strip()
    continue_signals = {"继续", "下一步", "接着来", "go", "next", "continue", ""}

    if pending and raw in continue_signals:
        head, *rest = pending
        return head, list(rest), True

    # Substantive new input wins. Clear pending.
    return raw or None, [], False


__all__ = [
    "MAX_SEGMENTS",
    "segment_player_action",
    "consume_pending_segment",
]
