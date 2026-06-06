"""Case-board schema rules per script_type.

Minimum-viable design — case_board is the player's working memory aid, not
a DM dashboard. Each field must drive a player decision. Everything else
goes through narrative or game_state.discovered_clues.

Three tiers:

- Tier 1 (always)      — current_objective, unresolved_questions,
                         npc_dynamic, time_pressure
- Tier 2 (mystery)     — suspects (name + suspicion_level + reason only;
                         motive / alibi / key_evidence go into reason as
                         natural language)
- Tier 3 (emotional)   — moral_dilemma_log, personal_cost_meter,
                         unrecovered_hooks

progress_phase is derived from narrative_arc.current_act and injected by
the API/client — Director must not write it.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Schema reference (informational; Director output is gated by case_board_ops,
# not by JSON-schema validation. Kept here so field shape is discoverable.)
# ---------------------------------------------------------------------------

TIER1_FIELDS: dict = {
    "current_objective": {
        "type": "string",
        "description": "一句话当前应该推进什么。",
    },
    "unresolved_questions": {
        "type": "array",
        "description": "核心未解疑问（≤5）。被回答时改 status=answered 并填 answer。",
        "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "answered"]},
                "answer": {"type": "string"},
            },
            "required": ["question", "status"],
        },
    },
    "npc_dynamic": {
        "type": "object",
        "description": (
            "NPC 状态-关系图，键为 NPC 名。每个 NPC 一个对象，字段："
            "trust(0-10) / mood / current_stance / last_shift_reason。"
        ),
        "additionalProperties": {
            "type": "object",
            "properties": {
                "trust": {"type": "integer", "minimum": 0, "maximum": 10},
                "mood": {"type": "string"},
                "current_stance": {"type": "string"},
                "last_shift_reason": {"type": "string"},
            },
        },
    },
    "time_pressure": {
        "type": "string",
        "enum": ["low", "medium", "high", "critical"],
        "description": "当下时间紧迫度。非 low 时前端会在头部显示徽章。",
    },
}

MYSTERY_FIELDS: dict = {
    "suspects": {
        "type": "array",
        "description": (
            "嫌疑人。name 必须与 npc_dynamic 中的 NPC 同名；"
            "reason 用一段自然语言写为什么怀疑——动机 / 不在场 / 关键证据都揉进 reason 里，"
            "不要拆成单独字段。"
        ),
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "suspicion_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "reason": {"type": "string"},
            },
            "required": ["name", "suspicion_level", "reason"],
        },
    },
}

EMOTIONAL_FIELDS: dict = {
    "moral_dilemma_log": {
        "type": "array",
        "description": "玩家面对的道德困境/抉择日志。每个困境一条。",
        "items": {
            "type": "object",
            "properties": {
                "round": {"type": "integer"},
                "dilemma": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "choice": {"type": "string", "description": "玩家最终选择；未抉择时空字符串。"},
                "fallout_hint": {"type": "string", "description": "选择后的余波伏笔。"},
            },
            "required": ["round", "dilemma"],
        },
    },
    "personal_cost_meter": {
        "type": "object",
        "description": "玩家个人代价仪表盘。",
        "properties": {
            "trust_with_npcs": {
                "type": "object",
                "description": "玩家与每个核心 NPC 的累计信任值（-10..10）。",
                "additionalProperties": {"type": "integer", "minimum": -10, "maximum": 10},
            },
            "exposure": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": "玩家秘密被外界知晓的程度。",
            },
            "transformation": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": "玩家自身转变程度，越高代表行为偏离初始定位越远。",
            },
        },
    },
    "unrecovered_hooks": {
        "type": "array",
        "description": "已抛出但未回收的叙事钩子。回收后 status=recovered；废弃时 abandoned。",
        "items": {
            "type": "object",
            "properties": {
                "round_raised": {"type": "integer"},
                "hook_text": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "recovered", "abandoned"]},
            },
            "required": ["round_raised", "hook_text", "status"],
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt rules — kept lean. Each rule is one player-facing decision the
# field unlocks; if you can't articulate that, the field shouldn't exist.
# ---------------------------------------------------------------------------

_TIER1_BLOCK = (
    "【案件面板 · 通用字段】\n"
    "- current_objective：一句话告诉玩家下一步关注什么。每轮重新评估。\n"
    "- unresolved_questions：核心未解疑问（≤5）。被回答时 upsert 改 status=answered 并填 answer。\n"
    '  status 必须是英文字面量 "open" / "answered"。\n'
    "- npc_dynamic.<npc_name>：每个相关 NPC 一个对象。\n"
    "  trust 0-10 整数；mood / current_stance 自由中文；last_shift_reason 写本轮变化的导火索。\n"
    "  关系发生显著变化（trust ±2 或 stance 翻转）才更新，避免每轮微调。\n"
    "- time_pressure：当下时间紧迫度。\n"
    '  必须是英文字面量 "low" / "medium" / "high" / "critical"。\n'
    "  默认 low；出现明确时限、倒计时、危机迫近时升级。"
)


_MYSTERY_BLOCK = (
    "【案件面板 · 推理型追加字段】\n"
    "- suspects：upsert 嫌疑人。name 与 npc_dynamic 同名。\n"
    '  suspicion_level 必须是英文字面量 "low" / "medium" / "high"。\n'
    "  reason 用一段自然语言写为什么怀疑——把动机、不在场证明、关键证据都揉进 reason 一段话里，\n"
    "  不要拆成 motive / alibi / key_evidence 等独立字段。\n"
    "  例：reason = \"他承认昨晚在西厢，但说不清何时离开；案发现场的脚印尺码与他吻合。\""
)


_EMOTIONAL_BLOCK = (
    "【案件面板 · 情感型追加字段】\n"
    "- moral_dilemma_log：玩家面临道德/情感抉择时 upsert 一条，标 round / dilemma / options。\n"
    "  玩家做出选择后再写 choice 与 fallout_hint。\n"
    "- personal_cost_meter：维护 trust_with_npcs（每个核心 NPC -10..10）、exposure(0..10)、transformation(0..10)。\n"
    "  代价显著变化时再更新，不要每轮微调。\n"
    '- unrecovered_hooks：抛出新伏笔时 upsert（status="open"）；回收时改 "recovered"；废弃时 "abandoned"。\n'
    '  status 必须是英文字面量 "open" / "recovered" / "abandoned"。'
)


_COMMON_TAIL = (
    "通用规则：\n"
    "- 只能通过 case_board_ops 更新案件面板，不要输出整份 case_board 快照。\n"
    "- 不写 progress_phase 字段；阶段进度由系统从 narrative_arc 派生。\n"
    "- 线索本身（discovered_clues）由 state_updates.new_clues 维护，不要在 case_board 重复存储。\n"
    "- 仅在变化发生时更新对应字段，没有显著变化的字段不写。"
)


def build_case_board_prompt_rules(script_type: str) -> str:
    """Return the Director prompt block describing which case_board fields to maintain.

    Falls back to Tier 1 only for unknown script_type / free mode.
    """
    blocks = [_TIER1_BLOCK]
    if script_type == "mystery":
        blocks.append(_MYSTERY_BLOCK)
    elif script_type == "emotional":
        blocks.append(_EMOTIONAL_BLOCK)
    blocks.append(_COMMON_TAIL)
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# progress_phase derivation (canonical mapping consumed by api/game.py).
# ---------------------------------------------------------------------------

_PROGRESS_PHASE_LABELS: dict[str, dict[str, str]] = {
    "mystery": {"intro": "初步调查", "middle": "深入追查", "climax": "真相浮现"},
    "emotional": {"intro": "相遇", "middle": "羁绊", "climax": "抉择"},
}
_DEFAULT_PROGRESS_PHASE_LABELS = {"intro": "序章", "middle": "发展", "climax": "高潮"}


def derive_progress_phase(script_type: str, current_act: str) -> str:
    """Map (script_type, current_act) → human-readable phase label."""
    if not current_act:
        return ""
    table = _PROGRESS_PHASE_LABELS.get(script_type) or _DEFAULT_PROGRESS_PHASE_LABELS
    return table.get(current_act, "")


# Back-compat shim — informational only, no longer wired into the tool schema.
_TYPE_FIELDS: dict[str, dict] = {
    "mystery": MYSTERY_FIELDS,
    "emotional": EMOTIONAL_FIELDS,
}


def build_case_board_tool_schema(script_type: str) -> dict:
    """Compose a JSON-schema-ish dict for the given script_type (informational)."""
    properties = {**TIER1_FIELDS}
    properties.update(_TYPE_FIELDS.get(script_type, {}))
    return {
        "type": "object",
        "description": f"案件面板（{script_type or 'tier1-only'}）",
        "properties": properties,
        "required": ["current_objective"],
    }
