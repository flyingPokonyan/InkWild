"""Structured NPC action — the runtime v2 replacement for free-text dialogue.

Each active NPC outputs one ``NPCAction`` per turn (see
docs/plans/runtime-architecture-overhaul-2026-05.md §4). Narrator weave
consumes a priority-sorted list of these instead of a flat ``{name: text}``
dialogue dict; intent_update / mood_shift / hidden_note feed back into
``game_state`` so the NPC retains agency across turns without director
having to write per-NPC instructions.

The dataclass is intentionally tolerant — ``validate_action`` accepts raw
dicts produced by the LLM, fills defaults, clamps/trims fields, and drops
the entry entirely (returning ``None``) when required fields are missing.
A dropped action is rendered as an *omitted-placeholder* by the orchestrator:
the NPC is in scene but has no visible output this turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# §4.1 — six action types. Anything outside this set causes the action to be
# dropped to an omitted-placeholder.
ACTION_TYPES = frozenset(
    {"speak", "withhold", "act", "observe", "scheme", "interject"}
)
# Subset that has a visible audible utterance.
SPEAKING_TYPES = frozenset({"speak", "withhold", "interject"})
# Subset that has a physical action (movement / give / take / strike / etc).
PHYSICAL_TYPES = frozenset({"act"})
# Subset that produces nothing visible — narrator only gets a one-line
# presence hint (review decision: do not let the NPC look entirely absent
# when director explicitly placed them in active_npcs).
INTERNAL_TYPES = frozenset({"observe", "scheme"})

TONE_VALUES = frozenset(
    {"sincere", "deceptive", "evasive", "aggressive", "vulnerable", "neutral"}
)
SCENE_ROLE_VALUES = frozenset({"primary", "secondary", "background"})
INTENT_PROGRESS_VALUES = frozenset({"advance", "stuck", "pivot", "complete"})

# Length caps — these are *trim* limits, not parse failures. The LLM
# routinely overshoots; we trim with a warn so the turn keeps moving.
DIALOGUE_MAX = 400
PHYSICAL_MAX = 200
HIDDEN_NOTE_MAX = 80
MOOD_REASON_MAX = 30


@dataclass
class IntentUpdate:
    """NPC's self-reported intent progress this turn."""

    progress: str  # advance | stuck | pivot | complete
    new_goal: str | None = None
    blocked_by: str | None = None
    stage_index_delta: int = 1

    def to_dict(self) -> dict:
        return {
            "progress": self.progress,
            "new_goal": self.new_goal,
            "blocked_by": self.blocked_by,
            "stage_index_delta": self.stage_index_delta,
        }


@dataclass
class MoodShift:
    from_mood: str
    to_mood: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "from": self.from_mood,
            "to": self.to_mood,
            "reason": self.reason,
        }


@dataclass
class NPCAction:
    """Structured output of one NPC's per-turn decision.

    Always tied to an ``npc_name`` (added by the validator from the calling
    context so the LLM doesn't have to self-identify). ``priority`` is what
    the narrator weave sorts on; higher = more prominent in the narration.
    """

    npc_name: str
    action_type: str
    priority: int = 5
    dialogue: str = ""
    physical: str = ""
    tone: str = "neutral"
    target_npc: str | None = None
    target: str | None = None
    intent_update: IntentUpdate | None = None
    mood_shift: MoodShift | None = None
    hidden_note: str = ""
    wait_for: str | None = None
    reason: str = ""
    usage: dict | None = None
    # Set to True when the action came back from the LLM but failed
    # mandatory-field validation (e.g. action_type=speak with no dialogue).
    # Orchestrator treats omitted actions as "NPC in scene but silent" rather
    # than rendering them.
    omitted: bool = False

    def is_visible(self) -> bool:
        """True iff this action produces something the narrator should
        render verbatim (dialogue or physical). Omitted / internal actions
        only get a one-line presence hint."""
        if self.omitted:
            return False
        if self.action_type in SPEAKING_TYPES and self.dialogue:
            return True
        if self.action_type in PHYSICAL_TYPES and self.physical:
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "npc_name": self.npc_name,
            "action_type": self.action_type,
            "priority": self.priority,
            "dialogue": self.dialogue,
            "physical": self.physical,
            "tone": self.tone,
            "target_npc": self.target_npc,
            "target": self.target,
            "intent_update": self.intent_update.to_dict() if self.intent_update else None,
            "mood_shift": self.mood_shift.to_dict() if self.mood_shift else None,
            "hidden_note": self.hidden_note,
            "wait_for": self.wait_for,
            "reason": self.reason,
            "omitted": self.omitted,
        }


def _clamp_priority(value: Any, scene_role: str | None) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = 5
    priority = max(1, min(10, priority))
    # §4.3 — background NPCs can't dominate the scene. Clamp to 5 (not 7) so
    # they sit clearly below secondary/primary NPCs in the weave ordering.
    if scene_role == "background" and priority >= 8:
        logger.info(
            "npc_action.priority_clamped",
            reason="background_scene_role",
            original=priority,
        )
        priority = 5
    return priority


def _trim(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def _coerce_intent_update(value: Any) -> IntentUpdate | None:
    if not isinstance(value, dict):
        return None
    progress = str(value.get("progress") or "").strip()
    if progress not in INTENT_PROGRESS_VALUES:
        return None
    new_goal = value.get("new_goal")
    blocked_by = value.get("blocked_by")
    stage_index_delta_raw = value.get("stage_index_delta", 1)
    try:
        stage_index_delta = int(stage_index_delta_raw)
    except (TypeError, ValueError):
        stage_index_delta = 1
    stage_index_delta = max(0, min(2, stage_index_delta))
    # pivot requires new_goal — without it the update is meaningless.
    if progress == "pivot" and not (isinstance(new_goal, str) and new_goal.strip()):
        return None
    return IntentUpdate(
        progress=progress,
        new_goal=str(new_goal).strip() if isinstance(new_goal, str) and new_goal.strip() else None,
        blocked_by=str(blocked_by).strip() if isinstance(blocked_by, str) and blocked_by.strip() else None,
        stage_index_delta=stage_index_delta,
    )


def _coerce_mood_shift(value: Any) -> MoodShift | None:
    if not isinstance(value, dict):
        return None
    from_mood = str(value.get("from") or "").strip()
    to_mood = str(value.get("to") or "").strip()
    if not from_mood or not to_mood or from_mood == to_mood:
        return None
    return MoodShift(
        from_mood=from_mood,
        to_mood=to_mood,
        reason=_trim(value.get("reason"), MOOD_REASON_MAX),
    )


def validate_action(
    npc_name: str,
    raw: dict | None,
    *,
    scene_role: str | None = None,
    known_npcs: set[str] | None = None,
    active_npcs: set[str] | None = None,
    usage: dict | None = None,
) -> NPCAction:
    """Coerce a raw LLM dict into an NPCAction.

    The return is always an ``NPCAction`` — failures are surfaced via the
    ``omitted=True`` flag plus a structlog warn. The orchestrator collects
    omitted actions but skips them in narrator weave (the NPC is "in scene
    but silent" — see §4.3).

    ``scene_role`` enables the background-can't-grandstand clamp; ``known_npcs``
    validates ``target_npc`` references; ``active_npcs`` validates ``wait_for``.
    """
    known_npcs = known_npcs or set()
    active_npcs = active_npcs or set()

    if not isinstance(raw, dict):
        logger.warning("npc_action.invalid_payload", npc=npc_name)
        return NPCAction(
            npc_name=npc_name,
            action_type="observe",
            omitted=True,
            usage=usage,
        )

    action_type = str(raw.get("action_type") or "").strip().lower()
    if action_type not in ACTION_TYPES:
        logger.warning(
            "npc_action.unknown_action_type",
            npc=npc_name,
            received=action_type or "<empty>",
        )
        return NPCAction(npc_name=npc_name, action_type="observe", omitted=True, usage=usage)

    # background NPCs can't interject. Demote to observe (silent presence)
    # rather than dropping outright — the NPC was still placed on stage.
    if action_type == "interject" and scene_role == "background":
        logger.info("npc_action.interject_demoted_background", npc=npc_name)
        action_type = "observe"

    priority = _clamp_priority(raw.get("priority"), scene_role)
    dialogue = _trim(raw.get("dialogue"), DIALOGUE_MAX)
    physical = _trim(raw.get("physical"), PHYSICAL_MAX)
    hidden_note = _trim(raw.get("hidden_note"), HIDDEN_NOTE_MAX)
    reason = _trim(raw.get("reason"), 120)

    tone = str(raw.get("tone") or "neutral").strip().lower()
    if tone not in TONE_VALUES:
        tone = "neutral"
    # Internal-only actions have no visible output, so a tone is meaningless.
    if action_type in INTERNAL_TYPES:
        tone = "neutral"

    target_npc = raw.get("target_npc")
    if isinstance(target_npc, str):
        target_npc = target_npc.strip() or None
        if target_npc and known_npcs and target_npc not in known_npcs:
            logger.info("npc_action.target_npc_unknown", npc=npc_name, target=target_npc)
            target_npc = None
    else:
        target_npc = None

    target = raw.get("target")
    target = target.strip() if isinstance(target, str) and target.strip() else None

    wait_for = raw.get("wait_for")
    if isinstance(wait_for, str):
        wait_for = wait_for.strip() or None
        if wait_for and (wait_for == npc_name or (active_npcs and wait_for not in active_npcs)):
            wait_for = None
    else:
        wait_for = None

    intent_update = _coerce_intent_update(raw.get("intent_update"))
    mood_shift = _coerce_mood_shift(raw.get("mood_shift"))

    # §4.3 — internal actions (scheme/observe) cannot carry dialogue.
    if action_type in INTERNAL_TYPES and dialogue:
        logger.info(
            "npc_action.dialogue_dropped_internal_action",
            npc=npc_name,
            action_type=action_type,
        )
        dialogue = ""

    # §4.3 — required-field gates. Failing these makes the action omitted.
    omitted = False
    if action_type in SPEAKING_TYPES and not dialogue:
        logger.warning(
            "npc_action.missing_dialogue",
            npc=npc_name,
            action_type=action_type,
        )
        omitted = True
    elif action_type == "act" and not physical:
        logger.warning("npc_action.missing_physical", npc=npc_name)
        omitted = True

    return NPCAction(
        npc_name=npc_name,
        action_type=action_type,
        priority=priority,
        dialogue=dialogue,
        physical=physical,
        tone=tone,
        target_npc=target_npc,
        target=target,
        intent_update=intent_update,
        mood_shift=mood_shift,
        hidden_note=hidden_note,
        wait_for=wait_for,
        reason=reason,
        usage=usage,
        omitted=omitted,
    )


# ----------------------------------------------------------------------------
# JSON Schema fragment — used by NPC LLM tool / JSON-mode prompt
# ----------------------------------------------------------------------------

NPC_ACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action_type": {
            "type": "string",
            "enum": sorted(ACTION_TYPES),
            "description": (
                "你这一轮的行动类型。speak=主动开口；withhold=被期待发言时回避/敷衍；"
                "act=做物理动作（移动/给物/抓人/动手）；observe=只默默观察不出声；"
                "scheme=只在心里盘算（看不见的内部行动）；interject=别人没主推但你想插话/打断。"
            ),
        },
        "priority": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "本轮你这条行动在场上的重要程度。1-3=可有可无；4-6=正常参与；7-8=关键发言；9-10=决定性时刻。背景角色不要给自己 ≥8。",
        },
        "dialogue": {
            "type": "string",
            "description": "你要说的话（speak/withhold/interject 必填，≤400 字）。withhold 时填敷衍/转移话题的台词。",
        },
        "physical": {
            "type": "string",
            "description": "你要做的物理动作（act 必填，≤200 字）。其他动作类型也可以填一个伴随的小动作。",
        },
        "tone": {
            "type": "string",
            "enum": sorted(TONE_VALUES),
            "description": "你的语气基调。observe/scheme 无视此字段。",
        },
        "target_npc": {"type": "string", "description": "若动作针对某 NPC，填其名"},
        "target": {"type": "string", "description": "若动作针对物/地点/话题，填名称"},
        "intent_update": {
            "type": "object",
            "description": "你对自己当前目标的进度自评。无变化时省略。",
            "properties": {
                "progress": {
                    "type": "string",
                    "enum": sorted(INTENT_PROGRESS_VALUES),
                    "description": "advance=推进一步；stuck=被挡住；pivot=换目标（须填 new_goal）；complete=已完成",
                },
                "new_goal": {"type": "string"},
                "blocked_by": {"type": "string"},
                "stage_index_delta": {"type": "integer", "minimum": 0, "maximum": 2},
            },
            "required": ["progress"],
        },
        "mood_shift": {
            "type": "object",
            "description": "本轮情绪转变。无变化时省略。",
            "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["from", "to"],
        },
        "hidden_note": {
            "type": "string",
            "description": "只有你自己未来轮能看到的内心备注，≤80 字（写理由、计划、警惕点）",
        },
        "wait_for": {
            "type": "string",
            "description": "你希望叙事把你放在某人之后写（仅影响排序提示，不阻塞调用）",
        },
        "reason": {
            "type": "string",
            "description": "interject 时建议解释「我为什么要插话」",
        },
    },
    "required": ["action_type", "priority"],
}


__all__ = [
    "ACTION_TYPES",
    "SPEAKING_TYPES",
    "PHYSICAL_TYPES",
    "INTERNAL_TYPES",
    "TONE_VALUES",
    "SCENE_ROLE_VALUES",
    "INTENT_PROGRESS_VALUES",
    "DIALOGUE_MAX",
    "PHYSICAL_MAX",
    "HIDDEN_NOTE_MAX",
    "NPC_ACTION_SCHEMA",
    "IntentUpdate",
    "MoodShift",
    "NPCAction",
    "validate_action",
]
