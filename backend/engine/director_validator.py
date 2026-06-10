"""Director v2 output validators — runtime v2 §5.6 / §13.2.

Catches the most common "director slipped back into god-mode" failures so
we can iterate prompt without dropping silently. None of these raise:
they all log structlog warnings + clean the payload so the turn proceeds.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# Words that indicate director is telling an NPC how to react — exactly the
# "AI 写戏" feel we're trying to kill (§5.6). Detection is keyword-level
# and approximate: a false positive just logs a warn, it doesn't block.
DIRECTIVE_LEAK_WORDS: tuple[str, ...] = (
    "应该",
    "需要",
    "可以",
    "不要",
    "记得",
    "小心",
    "保持",
    "试图",
    "建议",
    "最好",
    "必须",
    "请你",
    "去做",
)

PER_NPC_FOCUS_MAX_CHARS = 80
DIRECTOR_SCENE_BRIEF_MAX_CHARS = 180


def check_focus_objectivity(npc: str, focus: str) -> list[str]:
    """Return the directive-leak words found inside *focus* text.

    Empty list = clean. Caller is expected to structlog warn so we can
    audit how often the director prompt leaks reaction instructions.
    """
    if not focus:
        return []
    return [w for w in DIRECTIVE_LEAK_WORDS if w in focus]


def validate_active_npcs(
    active_npcs: list[str],
    known_npcs: set[str],
    *,
    max_active: int = 4,
) -> list[str]:
    """Drop names that aren't in the world; truncate to ``max_active``."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in active_npcs:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        if known_npcs and name not in known_npcs:
            logger.info("director_v2.active_npc_unknown", npc=name)
            continue
        cleaned.append(name)
        seen.add(name)
    if len(cleaned) > max_active:
        logger.info(
            "director_v2.active_npcs_truncated",
            received=len(cleaned),
            kept=max_active,
        )
        cleaned = cleaned[:max_active]
    return cleaned


def validate_per_npc_focus(
    focus_map: dict[str, str],
    active_npcs: list[str],
) -> dict[str, str]:
    """Filter focus map to active NPCs only; fill missing entries with a
    neutral default; trim entries; log directive-leak warnings.

    The default for missing entries is intentionally minimal — director
    should be explicit, but a missing focus shouldn't block the turn.
    """
    active_set = set(active_npcs)
    out: dict[str, str] = {}
    for npc, focus in focus_map.items():
        name = str(npc or "").strip()
        if not name or name not in active_set:
            continue
        text = str(focus or "").strip()
        if len(text) > PER_NPC_FOCUS_MAX_CHARS:
            logger.info(
                "director_v2.per_npc_focus.truncated",
                npc=name,
                received_chars=len(text),
                kept_chars=PER_NPC_FOCUS_MAX_CHARS,
            )
            text = text[:PER_NPC_FOCUS_MAX_CHARS].rstrip()
        # warn-only — do not strip directive words. Prompt should fix this.
        leak = check_focus_objectivity(name, text)
        if leak:
            logger.info(
                "director_v2.per_npc_focus.directive_leak",
                npc=name,
                words=leak,
                focus_preview=text[:60],
            )
        out[name] = text

    for name in active_npcs:
        if name not in out:
            logger.info("director_v2.per_npc_focus.missing", npc=name)
            out[name] = "在场"
    return out


def validate_scene_role(
    role_map: dict[str, str],
    active_npcs: list[str],
    valid_roles: set[str],
) -> dict[str, str]:
    """Ensure every active NPC has a scene_role; default to secondary."""
    active_set = set(active_npcs)
    out: dict[str, str] = {}
    for npc, role in role_map.items():
        name = str(npc or "").strip()
        if not name or name not in active_set:
            continue
        normalized = str(role or "").strip().lower()
        if normalized not in valid_roles:
            normalized = "secondary"
        out[name] = normalized
    for name in active_npcs:
        if name not in out:
            out[name] = "secondary"
    return out


def validate_offstage_active(
    offstage: list[str],
    active_npcs: list[str],
    known_npcs: set[str],
    *,
    max_offstage: int = 3,
) -> list[str]:
    """Drop names that overlap active_npcs (mutually exclusive) or are
    unknown; truncate to ``max_offstage``."""
    active_set = set(active_npcs)
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in offstage:
        name = str(name or "").strip()
        if not name or name in seen:
            continue
        if name in active_set:
            logger.info("director_v2.offstage_active_overlap", npc=name)
            continue
        if known_npcs and name not in known_npcs:
            logger.info("director_v2.offstage_active_unknown", npc=name)
            continue
        cleaned.append(name)
        seen.add(name)
        if len(cleaned) >= max_offstage:
            break
    return cleaned


def validate_event_fire_intent(
    intent: list[str],
    fired_ids: set[str],
    known_event_ids: set[str],
) -> list[str]:
    """Drop already-fired or unknown event ids; preserve order."""
    out: list[str] = []
    seen: set[str] = set()
    for event_id in intent:
        eid = str(event_id or "").strip()
        if not eid or eid in seen:
            continue
        if eid in fired_ids:
            logger.info("director_v2.event_fire_intent.already_fired", event_id=eid)
            continue
        if known_event_ids and eid not in known_event_ids:
            logger.info("director_v2.event_fire_intent.unknown", event_id=eid)
            continue
        out.append(eid)
        seen.add(eid)
    return out


__all__ = [
    "DIRECTIVE_LEAK_WORDS",
    "check_focus_objectivity",
    "validate_active_npcs",
    "validate_per_npc_focus",
    "validate_scene_role",
    "validate_offstage_active",
    "validate_event_fire_intent",
]
