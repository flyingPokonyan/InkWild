"""Offstage NPC scheduler — runtime v2 §7.3.

For NPCs the director marks as ``offstage_active`` (in the background but
still acting), we accumulate ``offstage_event_log`` entries each turn so
the next catch-up call has fresh material. Trigger detection is simple
keyword matching against active NPC dialogues + player action targets —
no NER, no LLM.

This module *only* updates the log. The actual fire-and-forget LLM call
that consumes the log and rewrites L3 inner state is invoked from the
orchestrator background task (and uses ``npc_catchup.run_catchup`` under
the hood with the offstage log as input).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


# Each offstage NPC keeps at most this many events between catch-ups.
# Older entries get dropped to keep state size bounded.
OFFSTAGE_LOG_MAX_PER_NPC = 12


@dataclass
class OffstageTrigger:
    """Why we decided this offstage NPC needs a log entry this turn."""

    npc_name: str
    reason: str  # "mentioned" | "event_fired" | "player_targeted" | "tick"
    content: str
    source: str


def detect_mentions(
    text: str,
    offstage_npcs: set[str],
    *,
    exclude: str | None = None,
) -> set[str]:
    """Plain substring search — keep it cheap. NPCs whose name appears
    in ``text`` get returned. ``exclude`` (typically the speaker) is
    skipped so a NPC mentioning themselves doesn't count."""
    found: set[str] = set()
    if not text or not offstage_npcs:
        return found
    for name in offstage_npcs:
        if exclude and name == exclude:
            continue
        if name in text:
            found.add(name)
    return found


def collect_triggers(
    *,
    offstage_npcs: list[str],
    npc_actions: list,  # list[NPCAction]
    player_action: dict | None,
    fired_events: list[dict],
    round_number: int,
) -> list[OffstageTrigger]:
    """Decide which offstage NPCs deserve a log entry this turn.

    Sources:
    - active NPC dialogue/physical mentions an offstage NPC by name
    - player_action.target_npc == an offstage NPC
    - a fired script event has involved_npcs that include an offstage NPC
    """
    triggers: list[OffstageTrigger] = []
    offstage_set = set(offstage_npcs or [])
    if not offstage_set:
        return triggers

    # 1. Active NPC dialogues / physical actions mention offstage NPC.
    for action in npc_actions or []:
        speaker = getattr(action, "npc_name", "")
        for blob in (getattr(action, "dialogue", ""), getattr(action, "physical", "")):
            if not blob:
                continue
            mentioned = detect_mentions(blob, offstage_set, exclude=speaker)
            for npc in mentioned:
                triggers.append(
                    OffstageTrigger(
                        npc_name=npc,
                        reason="mentioned",
                        content=f"{speaker} 提到/牵涉到你：「{blob[:80]}」",
                        source=speaker,
                    )
                )

    # 2. Player targeted an offstage NPC.
    if isinstance(player_action, dict):
        target = str(player_action.get("target_npc") or "").strip()
        summary = str(player_action.get("summary") or "").strip()
        if target in offstage_set:
            triggers.append(
                OffstageTrigger(
                    npc_name=target,
                    reason="player_targeted",
                    content=f"玩家本回合的行动针对你：{summary}",
                    source="player",
                )
            )

    # 3. Fired script events mention offstage NPC.
    for event in fired_events or []:
        if not isinstance(event, dict):
            continue
        involved = event.get("involved_npcs") or []
        name_field = str(event.get("name") or event.get("id") or "")
        summary = str(event.get("summary") or event.get("description") or "")
        for npc in involved:
            if str(npc).strip() in offstage_set:
                triggers.append(
                    OffstageTrigger(
                        npc_name=str(npc).strip(),
                        reason="event_fired",
                        content=f"事件「{name_field}」涉及到你：{summary[:80]}",
                        source=f"event:{name_field}",
                    )
                )

    return triggers


def append_log_entries(
    state,  # GameState
    triggers: list[OffstageTrigger],
) -> int:
    """Append trigger entries to ``state.offstage_event_log[npc]``.

    Returns the number of log entries written. Each NPC's list is capped
    at ``OFFSTAGE_LOG_MAX_PER_NPC``; older entries are dropped.
    """
    if not triggers:
        return 0
    written = 0
    for t in triggers:
        log = state.offstage_event_log.setdefault(t.npc_name, [])
        log.append(
            {
                "round": state.round_number,
                "content": t.content,
                "source": t.source,
                "reason": t.reason,
            }
        )
        if len(log) > OFFSTAGE_LOG_MAX_PER_NPC:
            del log[: len(log) - OFFSTAGE_LOG_MAX_PER_NPC]
        state.offstage_event_log[t.npc_name] = log
        written += 1
    return written


def should_run_periodic_tick(
    npc_name: str,
    state,  # GameState
    *,
    tick_rounds: int,
) -> bool:
    """Periodic catch-up tick — even with no event triggers, an offstage
    NPC gets refreshed every ``tick_rounds`` rounds so their inner state
    doesn't drift completely out of sync with the world."""
    last_active = (state.last_active_round or {}).get(npc_name)
    if last_active is None:
        return False
    return (state.round_number - int(last_active)) >= tick_rounds


__all__ = [
    "OFFSTAGE_LOG_MAX_PER_NPC",
    "OffstageTrigger",
    "detect_mentions",
    "collect_triggers",
    "append_log_entries",
    "should_run_periodic_tick",
]
