"""Per-event trigger progress — runtime v2 §10.

`condition_dsl.evaluate` returns bool; for director v2 we also want a
fractional progress 0..1 = #satisfied leaves / #total leaves so director
can see which scripted events are "almost ready to fire" and steer the
scene toward them.

Leaves are ``_FuncCall`` and ``_Compare`` nodes; ``_BinOp`` (AND/OR) and
``_Not`` are internal. NOT inverts its child's satisfaction state but does
not change the leaf count (NOT(X) is satisfied iff X is not, but X still
contributes 1 leaf).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from engine.condition_dsl import (
    ConditionDSLParseError,
    _BinOp,
    _Compare,
    _Expr,
    _FuncCall,
    _Not,
    _compare,
    _eval_func,
    _resolve_operand,
    parse as _dsl_parse,
)
from engine.state_manager import GameState

logger = structlog.get_logger()


@dataclass
class EventProgress:
    """Materialized progress info for a single events_data entry."""

    event_id: str
    name: str
    summary: str
    progress: float  # 0.0 .. 1.0
    total_leaves: int
    satisfied_leaves: int
    fired: bool


def _walk(expr: _Expr, state: GameState, *, negated: bool) -> tuple[int, int]:
    """Return (satisfied, total) leaf counts under *expr*.

    ``negated`` carries an enclosing NOT context: a leaf inside one NOT
    is "satisfied" when it evaluates False. Two NOTs cancel.
    """
    if isinstance(expr, _BinOp):
        s_l, t_l = _walk(expr.left, state, negated=negated)
        s_r, t_r = _walk(expr.right, state, negated=negated)
        return s_l + s_r, t_l + t_r
    if isinstance(expr, _Not):
        return _walk(expr.inner, state, negated=not negated)
    if isinstance(expr, _FuncCall):
        truth = _eval_func(expr.name, expr.arg, state)
        if negated:
            truth = not truth
        return (1 if truth else 0), 1
    if isinstance(expr, _Compare):
        left_val = _resolve_operand(expr.left, state)
        right_val = _resolve_operand(expr.right, state)
        truth = _compare(expr.op, left_val, right_val)
        if negated:
            truth = not truth
        return (1 if truth else 0), 1
    # Unknown node — count as 1 unsatisfied leaf so we don't silently
    # over-report progress.
    return 0, 1


def compute_event_progress(
    events_data: list[dict] | None,
    state: GameState,
) -> list[EventProgress]:
    """Build progress entries for every events_data row in *world_data*.

    Fired events get ``progress=1.0`` and ``fired=True``. Events with a
    missing / unparseable DSL get ``progress=0.0`` and one synthetic leaf
    (so they still appear in the list — director may want to manually fire
    something whose DSL is a stub).
    """
    out: list[EventProgress] = []
    if not events_data:
        return out

    triggered_ids: set[str] = state.triggered_event_ids or set()

    for event in events_data:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        if event.get("disabled"):
            continue

        name = str(event.get("name") or event.get("title") or event_id)
        summary = str(event.get("summary") or event.get("description") or "")

        if event_id in triggered_ids:
            out.append(
                EventProgress(
                    event_id=event_id,
                    name=name,
                    summary=summary,
                    progress=1.0,
                    total_leaves=0,
                    satisfied_leaves=0,
                    fired=True,
                )
            )
            continue

        dsl_source = ""
        trigger = event.get("trigger") or {}
        if isinstance(trigger, dict):
            dsl_source = str(trigger.get("condition_dsl") or "")

        if not dsl_source.strip():
            out.append(
                EventProgress(
                    event_id=event_id,
                    name=name,
                    summary=summary,
                    progress=0.0,
                    total_leaves=1,
                    satisfied_leaves=0,
                    fired=False,
                )
            )
            continue

        try:
            expr = _dsl_parse(dsl_source)
        except ConditionDSLParseError:
            logger.warning("event_progress.parse_failed", event_id=event_id, dsl=dsl_source)
            out.append(
                EventProgress(
                    event_id=event_id,
                    name=name,
                    summary=summary,
                    progress=0.0,
                    total_leaves=1,
                    satisfied_leaves=0,
                    fired=False,
                )
            )
            continue

        satisfied, total = _walk(expr, state, negated=False)
        # Defensive: a parse that produced zero leaves shouldn't ever happen
        # (DSL grammar enforces at least one comparison / func call) but
        # guard anyway.
        if total == 0:
            total = 1
        progress = satisfied / total
        out.append(
            EventProgress(
                event_id=event_id,
                name=name,
                summary=summary,
                progress=progress,
                total_leaves=total,
                satisfied_leaves=satisfied,
                fired=False,
            )
        )

    return out


def build_director_event_payload(
    events_data: list[dict] | None,
    state: GameState,
    *,
    min_progress: float = 0.0,
    max_active: int = 6,
) -> dict:
    """Render ``script_events`` block for Director input.

    Returns ``{"fired": [id, ...], "active": [{...}, ...]}``. ``active`` is
    sorted descending by progress and capped at ``max_active`` so the
    director prompt stays bounded on worlds with many scripted events.
    """
    progresses = compute_event_progress(events_data, state)
    fired_ids: list[str] = []
    active: list[dict] = []
    for p in progresses:
        if p.fired:
            fired_ids.append(p.event_id)
            continue
        if p.progress < min_progress:
            continue
        active.append(
            {
                "id": p.event_id,
                "name": p.name,
                "summary": p.summary,
                "progress": round(p.progress, 2),
                "satisfied_leaves": p.satisfied_leaves,
                "total_leaves": p.total_leaves,
            }
        )
    active.sort(key=lambda d: d["progress"], reverse=True)
    return {"fired": fired_ids, "active": active[:max_active]}


__all__ = [
    "EventProgress",
    "compute_event_progress",
    "build_director_event_payload",
]
