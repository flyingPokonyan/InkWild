from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from engine.context_builder import build_messages, director_state_view


def _find_last_outer_comma(buf: str) -> int:
    """位于顶层 object 内（depth==1）的最后一个 comma 索引，
    用于截断 partial JSON 以便补 `}` 解析。

    严格跳过字符串内部的字符（含转义），并按 {/[ +- } 维护嵌套深度。
    返回 -1 表示尚未进入顶层 object，或顶层还没有任何 key:value 完成。
    """
    depth = 0
    in_string = False
    escape = False
    last = -1
    for i, ch in enumerate(buf):
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{" or ch == "[":
            depth += 1
        elif ch == "}" or ch == "]":
            depth -= 1
        elif ch == "," and depth == 1:
            last = i
    return last


def try_partial_parse(buf: str) -> dict | None:
    """尝试从流式 tool_use 累计的 partial JSON 解析出**目前已完结**的 key 子集。

    策略：
      1. 先尝试直接 json.loads（buf 完整时走通路）
      2. 不行则找最后一个顶层 comma，截断，补 `}` 再 json.loads
    解析失败统一返回 None，调用方 swallow / 等下一次 delta。
    """
    if not buf:
        return None
    stripped = buf.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        result = json.loads(buf)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        pass
    comma = _find_last_outer_comma(buf)
    if comma < 0:
        return None
    truncated = buf[:comma] + "}"
    try:
        result = json.loads(truncated)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None



from engine.director_validator import (
    validate_active_npcs,
    validate_event_fire_intent,
    validate_offstage_active,
    validate_per_npc_focus,
    validate_scene_role,
)
from engine.event_progress import build_director_event_payload
from engine.prompts import (
    DIRECTOR_TOOL,
    RECALL_MEMORY_TOOL,
    build_director_json_instruction,
    build_director_system,
    build_director_system_v2,
    build_director_tool,
    build_director_tool_v2,
)
from engine.state_manager import GameState
from engine.structural_grounding import normalize_claim
from llm.model_capabilities import StructuredOutputMode, capability_for
from llm.router import LLMRouter
from llm.usage_context import current_usage_context

logger = structlog.get_logger()


def _record_director_outcome(
    outcome: str,
    retry_count: int,
    model_id: str,
) -> None:
    """Fire-and-forget: write a synthetic ``token_usage`` row tagging this
    Director call's outcome. Lets admin dashboards compute per-model
    parse-failure rate (rows where outcome='parse_failure') without
    correlating across the multiple usage rows the AOP already writes for
    each call attempt.

    Token counts on this row are zero — it's a summary, not a billing row.
    """
    ctx = current_usage_context()
    if ctx is None or not ctx.purpose:
        return
    if not ctx.session_id and not ctx.task_id:
        return

    # Imported lazily to avoid pulling services into the engine import graph
    # at module-load time (engine should not depend on services).
    import asyncio
    try:
        from database import async_session
        from models.game import TokenUsage
        from config import settings
    except Exception:  # noqa: BLE001
        return

    async def _write() -> None:
        try:
            async with async_session() as db:
                db.add(TokenUsage(
                    session_id=ctx.session_id,
                    task_id=ctx.task_id,
                    purpose=ctx.purpose or "game",
                    phase="director_outcome",
                    provider=settings.llm_provider,
                    model=model_id or settings.llm_default_model,
                    provider_name=None,
                    model_id=model_id or None,
                    input_tokens=0,
                    output_tokens=0,
                    image_count=0,
                    cost_cents=0,
                    outcome=outcome,
                    retry_count=retry_count,
                ))
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("director.outcome_record_failed", error=str(exc))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write())
    except RuntimeError:
        # No running loop (sync path) — drop silently rather than block.
        pass

# Reasoning models (DeepSeek V4 Pro, Qwen thinking, etc.) sometimes emit
# `<think>...</think>` or `<reasoning>...</reasoning>` blocks before the
# actual JSON payload even when response_format=json_object is set. Strip
# them before json.loads.
_THINKING_TAG_RE = re.compile(
    r"<(think|reasoning|thinking)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)


def _extract_json_from_text(raw: str) -> dict | None:
    """Pull the first valid top-level JSON object out of a raw LLM stream.

    Handles three real-world LLM quirks observed on DeepSeek V4 Pro:
    - <think>...</think> / <reasoning>...</reasoning> blocks before the JSON
    - ```json fences wrapping the payload
    - "Extra data" — a second JSON object (or stray text) trails the first;
      raw_decode takes the first object and ignores the rest

    Returns None for empty input, non-dict top-level, or unparseable text.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    raw = _THINKING_TAG_RE.sub("", raw).strip()
    if not raw:
        return None

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()

    if not raw.startswith("{"):
        first_brace = raw.find("{")
        if first_brace == -1:
            return None
        raw = raw[first_brace:]

    try:
        obj, _ = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError:
        return None

    return obj if isinstance(obj, dict) else None


class DirectorParseError(RuntimeError):
    """Director failed to produce a usable tool_use payload after retries.

    Phase 2.A.3 — distinguish "LLM responded but its structured output is
    unusable" from generic LLM errors so orchestrator can surface a typed
    SSE `llm_parse` error and the UI can offer a "retry round" button instead
    of falling back silently to a degraded scene.
    """


@dataclass
class DirectorResult:
    # ---- v1 fields (still produced in legacy path) ----
    involved_npcs: list[str] = field(default_factory=list)
    npc_instructions: dict[str, str] = field(default_factory=dict)
    scene_direction: str = ""
    state_updates: dict = field(default_factory=dict)
    quick_actions: list[str] = field(default_factory=list)
    ending_triggered: dict | None = None
    memory_extracts: list[dict] = field(default_factory=list)
    case_board_ops: list[dict] = field(default_factory=list)
    # Research mode (CASE_BOARD_RESEARCH=1) — Director's per-turn observation
    # about what info would be worth showing on the case board. Persisted to
    # backend/research/{sid}.jsonl by the orchestrator. None in normal runs.
    research_note: dict | None = None
    # Phase 0.A.3 余项 — Director 主动写入某 NPC 私有记忆。
    inform_npc_calls: list[dict] = field(default_factory=list)
    # NPC-1 — Director-decided speaking order for this turn (v1 only).
    npc_speech_order: list[str] = field(default_factory=list)
    # Phase 1.B.5 — typed structured action describing what the player did
    # this turn. Used by both v1 and v2 paths.
    player_action: dict | None = None
    usage: dict | None = None

    # ---- v2 fields (runtime architecture overhaul) ----
    # When ``runtime_architecture_v2_enabled`` is True the v2 fields are the
    # source of truth. ``involved_npcs`` is still set (== active_npcs) so the
    # rest of orchestrator's setup code (memory batch / reflection) doesn't
    # need a separate path.
    scene_brief: str = ""
    active_npcs: list[str] = field(default_factory=list)
    per_npc_focus: dict[str, str] = field(default_factory=dict)
    scene_role: dict[str, str] = field(default_factory=dict)
    dramatic_intensity: str = "medium"
    offstage_active: list[str] = field(default_factory=list)
    narrative_pressure: str = "advance"
    event_fire_intent: list[str] = field(default_factory=list)

    # Structural evolution (spec 2026-06-03 grounded redesign). Cheap boolean
    # hint: "does this turn touch world底色 (a structural change attempted or
    # possibly enacted)?" Rare-fires the grounding pipeline. The Director makes
    # NO legitimacy judgment — it only PARSES the player's assertion into a claim.
    structural_in_play: bool = False
    # When structural_in_play, the parsed claim + premise (schema mirrors
    # structural_grounding.parse_claim output): {claim_key, claim_text, kind,
    # target_ref, premise:{type, required_entity, requires, detail}}. None otherwise.
    structural_claim: dict | None = None


class DirectorAgent:
    def __init__(self, llm_router: LLMRouter, *, prefer_json_mode: bool | None = None):
        self.llm_router = llm_router
        # ``prefer_json_mode`` is retained as a compat kwarg for older callers
        # (tests, orchestrator) but the actual dispatch decision now comes
        # from the per-model capability matrix at run() time. When the kwarg
        # is set, it acts as an explicit override:
        #   True  → force JSON mode regardless of capability
        #   False → force tool_use_auto (legacy path)
        #   None  → use capability_for(router.current_model_id())
        self.prefer_json_mode = prefer_json_mode

    @staticmethod
    def _coerce_string_list(value: object, default: list[str] | None = None) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value]
        return list(default or [])

    @staticmethod
    def _fallback_quick_actions(active_npcs: list[str]) -> list[str]:
        """Context-aware fallback for when the director omits quick_actions.

        These chips exist to give a stuck player a concrete next move. When the
        director drops the field, reference the NPCs actually on stage instead
        of generic filler ("继续观察" etc.) so the safety net still points
        somewhere real. The caller logs when this fires so we can track how
        often the director skips the field.
        """
        if active_npcs:
            primary = active_npcs[0]
            second = active_npcs[1] if len(active_npcs) > 1 else None
            return [
                f"找{primary}问话",
                f"留意{second}" if second else f"问{primary}近况",
                "查看现场线索",
            ]
        return ["四下查看", "回想线索", "主动开口"]

    @staticmethod
    def _coerce_string_dict(value: object) -> dict[str, str]:
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
        return {}

    @staticmethod
    def _coerce_nested_dict(value: object) -> dict:
        if not isinstance(value, dict):
            return {}

        normalized: dict[str, object] = {}

        if isinstance(value.get("location"), str) and value["location"].strip():
            normalized["location"] = value["location"]

        if isinstance(value.get("time_advance"), bool):
            normalized["time_advance"] = value["time_advance"]

        new_clues = DirectorAgent._coerce_string_list(value.get("new_clues"))
        if new_clues:
            normalized["new_clues"] = new_clues

        npc_updates = value.get("npc_updates")
        if isinstance(npc_updates, dict):
            normalized["npc_updates"] = {
                str(name): update
                for name, update in npc_updates.items()
                if isinstance(update, dict)
            }

        inventory_changes = value.get("inventory_changes")
        if isinstance(inventory_changes, dict):
            normalized_inventory: dict[str, list[str]] = {}
            add_items = DirectorAgent._coerce_string_list(inventory_changes.get("add"))
            remove_items = DirectorAgent._coerce_string_list(inventory_changes.get("remove"))
            if add_items:
                normalized_inventory["add"] = add_items
            if remove_items:
                normalized_inventory["remove"] = remove_items
            if normalized_inventory:
                normalized["inventory_changes"] = normalized_inventory

        return normalized

    @staticmethod
    def _coerce_optional_dict(value: object) -> dict | None:
        return value if isinstance(value, dict) else None

    @staticmethod
    def _coerce_memory_extracts(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _coerce_case_board_ops(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _coerce_research_note(value: object) -> dict | None:
        if not isinstance(value, dict):
            return None
        important = value.get("important")
        if not isinstance(important, list) or not important:
            return None
        return {
            "important": [str(x) for x in important if x],
            "would_display_as": [str(x) for x in value.get("would_display_as") or []],
            "why": str(value.get("why") or ""),
        }

    @staticmethod
    def _coerce_speech_order(value: object, involved_npcs: list[str]) -> list[str]:
        """Filter to names ∈ involved_npcs, dedupe preserving order.

        Empty result means caller should fall back to involved_npcs order.
        Names the LLM hallucinated (not in involved_npcs) are dropped silently
        — Director sometimes echoes a peer NPC by mistake.
        """
        if not isinstance(value, list):
            return []
        allowed = set(involved_npcs)
        seen: set[str] = set()
        order: list[str] = []
        for item in value:
            name = str(item or "").strip()
            if not name or name in seen or name not in allowed:
                continue
            seen.add(name)
            order.append(name)
        return order

    # Phase 1.B.5 — keep in sync with DIRECTOR_TOOL.input_schema.player_action.
    _ALLOWED_PLAYER_ACTION_TYPES = frozenset(
        {
            "visit_location",
            "ask_about",
            "tell_npc",
            "give_item",
            "take_item",
            "examine",
            "confront",
            "wait",
            "other",
        }
    )

    @staticmethod
    def _coerce_player_action(value: object) -> dict | None:
        """Normalize Director's player_action payload into a stable shape.

        Drops the field entirely if the LLM gave us nothing usable; orchestrator
        treats ``None`` as "no action recorded this turn" (won't append to
        game_state.player_actions).
        """
        if not isinstance(value, dict):
            return None
        action_type = str(value.get("action_type") or "").strip()
        if action_type not in DirectorAgent._ALLOWED_PLAYER_ACTION_TYPES:
            action_type = "other"
        summary = str(value.get("summary") or "").strip()
        if not summary:
            # Without a summary the entry has no value for NPC cross-turn
            # awareness — drop it rather than persist a placeholder.
            return None
        # Trim summary to keep state size bounded; NPC prompt rendering also
        # benefits from a tight upper bound.
        if len(summary) > 80:
            summary = summary[:80].rstrip()
        target_npc = str(value.get("target_npc") or "").strip()
        target = str(value.get("target") or "").strip()
        return {
            "action_type": action_type,
            "target_npc": target_npc,
            "target": target,
            "summary": summary,
        }

    @staticmethod
    def _coerce_inform_npc_calls(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        cleaned: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            npc = str(item.get("npc") or "").strip()
            info = str(item.get("info") or "").strip()
            if not npc or not info:
                continue
            importance = str(item.get("importance") or "high").strip().lower()
            if importance not in {"high", "medium", "low"}:
                importance = "high"
            cleaned.append({"npc": npc, "info": info, "importance": importance})
        return cleaned

    # ---- v2 helpers ----

    @staticmethod
    def _coerce_str(value: object, default: str = "") -> str:
        if isinstance(value, str):
            return value.strip()
        return default

    @staticmethod
    def _coerce_string_value_dict(value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(k): str(v).strip()
            for k, v in value.items()
            if str(k).strip() and isinstance(v, str)
        }

    def _build_result_v2(
        self,
        tool_input: dict,
        usage_data: dict | None,
        *,
        known_npcs: set[str],
        known_event_ids: set[str],
        fired_event_ids: set[str],
    ) -> DirectorResult:
        """Parse v2 director output. Falls back to safe defaults on missing
        fields — orchestrator is expected to still drive the turn rather than
        bail when one field is malformed."""
        scene_brief = self._coerce_str(tool_input.get("scene_brief"))
        active_npcs = validate_active_npcs(
            self._coerce_string_list(tool_input.get("active_npcs")),
            known_npcs,
        )
        per_npc_focus = validate_per_npc_focus(
            self._coerce_string_value_dict(tool_input.get("per_npc_focus")),
            active_npcs,
        )
        scene_role = validate_scene_role(
            self._coerce_string_value_dict(tool_input.get("scene_role")),
            active_npcs,
            valid_roles={"primary", "secondary", "background"},
        )

        intensity = self._coerce_str(tool_input.get("dramatic_intensity"), "medium").lower()
        if intensity not in {"low", "medium", "high", "climax"}:
            intensity = "medium"

        pressure = self._coerce_str(tool_input.get("narrative_pressure"), "advance").lower()
        if pressure not in {"advance", "build_tension", "breathing_room"}:
            pressure = "advance"

        offstage = validate_offstage_active(
            self._coerce_string_list(tool_input.get("offstage_active")),
            active_npcs,
            known_npcs,
        )

        event_intent = validate_event_fire_intent(
            self._coerce_string_list(tool_input.get("event_fire_intent")),
            fired_event_ids,
            known_event_ids,
        )

        quick_actions = self._coerce_string_list(tool_input.get("quick_actions"))
        if not quick_actions:
            quick_actions = self._fallback_quick_actions(active_npcs)
            logger.warning("director_quick_actions_fallback", active_npcs=list(active_npcs))

        return DirectorResult(
            # v1 compat — keep involved_npcs == active_npcs so the rest of
            # the orchestrator that consults involved_npcs (reflection,
            # memory batch) still works.
            involved_npcs=list(active_npcs),
            npc_instructions={},
            scene_direction=self._coerce_str(
                tool_input.get("scene_direction"),
                "局势暂时平静，先观察周围的变化。",
            ),
            state_updates=self._coerce_nested_dict(tool_input.get("state_updates")),
            quick_actions=quick_actions,
            ending_triggered=self._coerce_optional_dict(tool_input.get("ending_triggered")),
            memory_extracts=self._coerce_memory_extracts(tool_input.get("memory_extracts")),
            case_board_ops=self._coerce_case_board_ops(tool_input.get("case_board_ops")),
            research_note=self._coerce_research_note(tool_input.get("research_note")),
            inform_npc_calls=[],
            npc_speech_order=[],
            player_action=self._coerce_player_action(tool_input.get("player_action")),
            usage=usage_data,
            # v2 fields
            scene_brief=scene_brief,
            active_npcs=active_npcs,
            per_npc_focus=per_npc_focus,
            scene_role=scene_role,
            dramatic_intensity=intensity,
            offstage_active=offstage,
            narrative_pressure=pressure,
            event_fire_intent=event_intent,
            structural_in_play=bool(tool_input.get("structural_in_play")),
            structural_claim=(
                normalize_claim(tool_input.get("structural_claim"))
                if tool_input.get("structural_in_play")
                else None
            ),
        )

    def _build_result(self, tool_input: dict, usage_data: dict | None) -> DirectorResult:
        if any(
            not isinstance(tool_input.get(field), expected)
            for field, expected in (
                ("npc_instructions", dict),
                ("state_updates", dict),
                ("ending_triggered", dict),
            )
            if tool_input.get(field) is not None
        ):
            logger.warning("director_tool_payload_malformed", payload=tool_input)

        quick_actions = self._coerce_string_list(
            tool_input.get("quick_actions"),
            default=["继续观察", "和周围的人聊聊", "检查线索"],
        )

        involved_npcs = self._coerce_string_list(tool_input.get("involved_npcs"))
        return DirectorResult(
            involved_npcs=involved_npcs,
            npc_instructions=self._coerce_string_dict(tool_input.get("npc_instructions")),
            scene_direction=str(tool_input.get("scene_direction") or "局势暂时平静，先观察周围的变化。"),
            state_updates=self._coerce_nested_dict(tool_input.get("state_updates")),
            quick_actions=quick_actions,
            ending_triggered=self._coerce_optional_dict(tool_input.get("ending_triggered")),
            memory_extracts=self._coerce_memory_extracts(tool_input.get("memory_extracts")),
            case_board_ops=self._coerce_case_board_ops(tool_input.get("case_board_ops")),
            research_note=self._coerce_research_note(tool_input.get("research_note")),
            inform_npc_calls=self._coerce_inform_npc_calls(tool_input.get("inform_npc_calls")),
            npc_speech_order=self._coerce_speech_order(
                tool_input.get("npc_speech_order"), involved_npcs
            ),
            player_action=self._coerce_player_action(tool_input.get("player_action")),
            usage=usage_data,
        )

    async def run(
        self,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        user_input: str,
        game_mode: str,
        memory_context: str = "",
        authors_note: str | None = None,
        recall_fn: Callable[[str, int], list[dict]] | None = None,
        script_type: str = "",
    ) -> DirectorResult:
        base_system = build_director_system(
            base_setting=world_data.get("base_setting", ""),
            script_setting=world_data.get("script_setting", ""),
            npc_descriptions=world_data.get("npc_descriptions", ""),
            ending_conditions=world_data.get("ending_conditions", ""),
            game_mode=game_mode,
            memory_context=memory_context,
            script_type=script_type,
        )
        if authors_note:
            base_system = "\n\n".join([base_system, f"## Author's Note\n{authors_note}"])

        messages = build_messages(game_state, recent_messages, context_summary, user_input)
        # Mirrors case_board._discovered_clue_ids — keep in sync if either changes.
        discovered_clue_ids = [
            clue["id"]
            for clue in (getattr(game_state, "discovered_clues", None) or [])
            if isinstance(clue, dict) and isinstance(clue.get("id"), str)
        ]
        director_tool = build_director_tool(
            script_type, game_mode, discovered_clue_ids=discovered_clue_ids,
        )

        # Resolve dispatch mode from the model bound to this router's slot.
        # Reasoning models (DeepSeek V4 Pro, Qwen thinking, etc.) get
        # JSON_OBJECT; strong tool-use models (Claude, GPT) get FORCED_TOOL;
        # everything else stays on TOOL_USE_AUTO. The legacy `prefer_json_mode`
        # kwarg, if set, overrides capability lookup.
        model_id = self.llm_router.current_model_id()
        if self.prefer_json_mode is True:
            mode = StructuredOutputMode.JSON_OBJECT
        elif self.prefer_json_mode is False:
            mode = StructuredOutputMode.TOOL_USE_AUTO
        else:
            mode = capability_for(model_id).structured_output_mode

        # JSON mode is materially more reliable for reasoning models such as
        # DeepSeek V4 Pro. Do not force those models back to tool_use merely
        # because recall_fn is available; recent context and memory_context
        # are already in the prompt. Models whose capability is tool-use based
        # can still use recall_memory through _run_tool_use below.

        # Phase 8 — 3 attempts with prompt mutation. Each failed attempt
        # appends explicit feedback to the system prompt, so the retry
        # changes the input rather than repeating the same call.
        last_feedback = ""
        for attempt in range(3):
            mutated_system = base_system
            if last_feedback:
                mutated_system = (
                    base_system
                    + "\n\n## 上一次输出的问题\n"
                    + last_feedback
                    + "\n请这次严格按 schema 输出，避免重复同样的问题。"
                )
            try:
                if mode == StructuredOutputMode.JSON_OBJECT:
                    result = await self._run_json_mode(
                        system=mutated_system,
                        messages=messages,
                        schema=director_tool["input_schema"],
                    )
                    if result is None:
                        raise DirectorParseError("JSON mode produced no valid output")
                    _record_director_outcome(
                        outcome="success" if attempt == 0 else "retried_success",
                        retry_count=attempt,
                        model_id=model_id,
                    )
                    return result
                elif mode == StructuredOutputMode.FORCED_TOOL:
                    result = await self._run_tool_use(
                        system=mutated_system,
                        messages=messages,
                        director_tool=director_tool,
                        recall_fn=recall_fn,
                        tool_choice={
                            "type": "function",
                            "function": {"name": director_tool["name"]},
                        },
                    )
                else:  # TOOL_USE_AUTO
                    result = await self._run_tool_use(
                        system=mutated_system,
                        messages=messages,
                        director_tool=director_tool,
                        recall_fn=recall_fn,
                        tool_choice=None,
                    )
                _record_director_outcome(
                    outcome="success" if attempt == 0 else "retried_success",
                    retry_count=attempt,
                    model_id=model_id,
                )
                return result
            except DirectorParseError as exc:
                last_feedback = (
                    f"- 上次输出无法解析：{exc}。"
                    "请直接产出合法 JSON 对象（或调用 director_decide 工具）；"
                    "不要任何前导文本、思考标签或 markdown 包裹。"
                )
                logger.warning(
                    "director.parse_failure_retrying",
                    attempt=attempt + 1,
                    mode=mode.value,
                    reason=str(exc),
                )
                continue

        logger.warning(
            "director.parse_failure_final",
            mode=mode.value,
            model_id=model_id,
        )
        _record_director_outcome(
            outcome="parse_failure",
            retry_count=3,
            model_id=model_id,
        )
        raise DirectorParseError(
            f"Director produced no usable output after 3 attempts (mode={mode.value})"
        )

    async def run_v2(
        self,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        user_input: str,
        game_mode: str,
        memory_context: str = "",
        world_pulse_directive: str = "",
        authors_note: str | None = None,
        recall_fn: Callable[[str, int], list[dict]] | None = None,
        script_type: str = "",
        on_partial: Callable[[dict], None] | None = None,
        *,
        player_input_weak: bool = False,
        multi_step_input: bool = False,
    ) -> DirectorResult:
        """v2 entrypoint — uses build_director_system_v2 + DIRECTOR_TOOL_V2.

        Shape-identical retry/dispatch logic to ``run()``; only the prompt
        builder and tool schema differ. Caller is the orchestrator's v2 path
        (gated by ``settings.runtime_architecture_v2_enabled``).
        """
        # Surface fired/active scripted events so the prompt can steer toward
        # them when progress is high.
        events_payload = build_director_event_payload(
            world_data.get("events_data"), game_state
        )

        base_system = build_director_system_v2(
            base_setting=world_data.get("base_setting", ""),
            script_setting=world_data.get("script_setting", ""),
            npc_descriptions=world_data.get("npc_descriptions", ""),
            ending_conditions=world_data.get("ending_conditions", ""),
            game_mode=game_mode,
            world_pulse_directive=world_pulse_directive,
            script_type=script_type,
            script_events=events_payload if game_mode == "script" else None,
            player_input_weak=player_input_weak,
            multi_step_input=multi_step_input,
            endings=world_data.get("endings") if game_mode == "script" else None,
        )
        if authors_note:
            base_system = "\n\n".join([base_system, f"## Author's Note\n{authors_note}"])

        # memory_context（事实块）作为单独的 user 消息塞在 player_input 之前，
        # 不再进 system prompt，避免破坏 system 的 prefix cache。
        messages = build_messages(
            game_state, recent_messages, context_summary, user_input,
            memory_context=memory_context,
            state_view=director_state_view(game_state),
        )
        discovered_clue_ids = [
            clue["id"]
            for clue in (getattr(game_state, "discovered_clues", None) or [])
            if isinstance(clue, dict) and isinstance(clue.get("id"), str)
        ]
        director_tool = build_director_tool_v2(
            script_type, game_mode, discovered_clue_ids=discovered_clue_ids,
        )

        known_npcs = {
            str(npc.get("name") or "").strip()
            for npc in (world_data.get("npcs") or [])
            if isinstance(npc, dict) and npc.get("name")
        }
        known_event_ids = {
            str(ev.get("id") or "").strip()
            for ev in (world_data.get("events_data") or [])
            if isinstance(ev, dict) and ev.get("id")
        }
        fired_event_ids = set(game_state.triggered_event_ids or set())

        model_id = self.llm_router.current_model_id()
        if self.prefer_json_mode is True:
            mode = StructuredOutputMode.JSON_OBJECT
        elif self.prefer_json_mode is False:
            mode = StructuredOutputMode.TOOL_USE_AUTO
        else:
            mode = capability_for(model_id).structured_output_mode

        last_feedback = ""
        for attempt in range(3):
            mutated_system = base_system
            if last_feedback:
                mutated_system = (
                    base_system
                    + "\n\n## 上一次输出的问题\n"
                    + last_feedback
                    + "\n请这次严格按 schema 输出，避免重复同样的问题。"
                )
            try:
                if mode == StructuredOutputMode.JSON_OBJECT:
                    tool_input = await self._run_json_mode_raw(
                        system=mutated_system,
                        messages=messages,
                        schema=director_tool["input_schema"],
                        on_partial=on_partial,
                        # Rotate provider/key each retry so a parse failure
                        # doesn't re-hit the same misbehaving endpoint.
                        provider_offset=attempt,
                    )
                    if tool_input is None:
                        raise DirectorParseError("JSON mode produced no valid output")
                    usage_data, payload = tool_input
                    _record_director_outcome(
                        outcome="success" if attempt == 0 else "retried_success",
                        retry_count=attempt,
                        model_id=model_id,
                    )
                    return self._build_result_v2(
                        payload,
                        usage_data,
                        known_npcs=known_npcs,
                        known_event_ids=known_event_ids,
                        fired_event_ids=fired_event_ids,
                    )
                else:
                    if mode == StructuredOutputMode.FORCED_TOOL:
                        tool_choice = {
                            "type": "function",
                            "function": {"name": director_tool["name"]},
                        }
                    else:
                        tool_choice = None
                    payload, usage_data = await self._run_tool_use_raw(
                        system=mutated_system,
                        messages=messages,
                        director_tool=director_tool,
                        recall_fn=recall_fn,
                        tool_choice=tool_choice,
                        on_partial=on_partial,
                    )
                    _record_director_outcome(
                        outcome="success" if attempt == 0 else "retried_success",
                        retry_count=attempt,
                        model_id=model_id,
                    )
                    return self._build_result_v2(
                        payload,
                        usage_data,
                        known_npcs=known_npcs,
                        known_event_ids=known_event_ids,
                        fired_event_ids=fired_event_ids,
                    )
            except DirectorParseError as exc:
                last_feedback = (
                    f"- 上次输出无法解析：{exc}。"
                    "请直接产出合法 JSON 对象（或调用 director_decision 工具）。"
                )
                logger.warning(
                    "director_v2.parse_failure_retrying",
                    attempt=attempt + 1,
                    mode=mode.value,
                    reason=str(exc),
                )
                continue

        logger.warning(
            "director_v2.parse_failure_final",
            mode=mode.value,
            model_id=model_id,
        )
        _record_director_outcome(
            outcome="parse_failure",
            retry_count=3,
            model_id=model_id,
        )
        raise DirectorParseError(
            f"Director v2 produced no usable output after 3 attempts (mode={mode.value})"
        )

    async def _run_tool_use_raw(
        self,
        *,
        system: str,
        messages: list[dict],
        director_tool: dict,
        recall_fn: Callable[[str, int], list[dict]] | None,
        tool_choice: str | dict | None = None,
        on_partial: Callable[[dict], None] | None = None,
    ) -> tuple[dict, dict | None]:
        """Same plumbing as ``_run_tool_use`` but returns the raw tool_input
        dict + usage instead of a built DirectorResult, so v2 can route the
        payload through ``_build_result_v2``.

        ``on_partial`` 可选回调：每收到一段 input_json_delta 后尝试 partial-parse 累计
        的 director_decision JSON，将能 parse 出的 key 子集传给 callback。callback
        通常用于让 orchestrator 在 Director 完成前就调度下游（如 NPC pre-fetch）。
        callback 失败不影响主流程（swallow）。
        """
        tools = [director_tool]
        if recall_fn:
            tools.append(RECALL_MEMORY_TOOL)
        effective_tool_choice = tool_choice
        if recall_fn and isinstance(tool_choice, dict):
            effective_tool_choice = None

        usage_data = None
        for _ in range(3):
            tool_input: dict | None = None
            recall_request: dict | None = None
            # Per-tool-call streaming accumulators for partial parse (B: 早绑 NPC)
            current_tool_name: str | None = None
            partial_buf = ""
            partial_already_signaled: set[str] = set()
            stream_kwargs: dict = {
                "messages": messages,
                "tools": tools,
                "system": system,
            }
            if effective_tool_choice is not None:
                stream_kwargs["tool_choice"] = effective_tool_choice
            async for event in self.llm_router.stream_with_tools(**stream_kwargs):
                etype = event.get("type")
                if etype == "tool_use_start":
                    current_tool_name = event.get("name")
                    partial_buf = ""
                    partial_already_signaled = set()
                elif etype == "input_json_delta" and on_partial and current_tool_name == director_tool["name"]:
                    partial_buf += event.get("partial_json", "") or ""
                    parsed = try_partial_parse(partial_buf)
                    if parsed:
                        # 只在新出现 key 时回调，避免每个 delta 都重复触发
                        new_keys = set(parsed.keys()) - partial_already_signaled
                        if new_keys:
                            partial_already_signaled |= new_keys
                            try:
                                on_partial(parsed)
                            except Exception:  # noqa: BLE001
                                logger.warning("director.on_partial_failed", exc_info=True)
                elif etype == "tool_use" and event.get("name") == director_tool["name"]:
                    tool_input = event.get("input") or {}
                elif etype == "tool_use" and event.get("name") == RECALL_MEMORY_TOOL["name"]:
                    recall_request = event.get("input") or {}
                elif etype == "usage":
                    usage_data = event

            if tool_input:
                return tool_input, usage_data

            if recall_request and recall_fn:
                keyword = str(recall_request.get("keyword") or "")
                max_results = int(recall_request.get("max_results") or 3)
                results = recall_fn(keyword, max_results)
                recall_text = (
                    "\n".join(f"[第{item.get('round', '?')}轮] {item.get('content', '')}" for item in results)
                    if results
                    else "未找到相关记录"
                )
                messages.append({"role": "assistant", "content": f"[recall_memory 结果]\n{recall_text}"})
                messages.append({"role": "user", "content": "请根据以上信息做出决策。"})
                continue
            break

        raise DirectorParseError("Director v2 produced no tool_use payload after 3 attempts")

    async def _run_json_mode_raw(
        self,
        *,
        system: str,
        messages: list[dict],
        schema: dict,
        on_partial: Callable[[dict], None] | None = None,
        provider_offset: int = 0,
    ) -> tuple[dict | None, dict] | None:
        """JSON-mode counterpart of ``_run_tool_use_raw``.

        ``on_partial`` 可选回调：每收到一段 text_delta（JSON mode 下整个 JSON 物体
        以纯文本形式 stream 出来）后尝试 partial-parse 累计的 buffer，触发回调。
        给 orchestrator 提前调度下游用（B：早绑 NPC）。
        """
        from config import settings

        json_system = "\n\n".join([system, build_director_json_instruction(schema)])
        text_parts: list[str] = []
        usage_data = None
        finish_reason: str | None = None
        partial_signaled: set[str] = set()
        try:
            async for event in self.llm_router.stream_json(
                messages=messages,
                system=json_system,
                # The v2 director schema is large; an undersized budget makes
                # DeepSeek JSON mode truncate → invalid JSON. See settings note.
                max_tokens=settings.director_json_max_tokens,
                provider_offset=provider_offset,
            ):
                if event["type"] == "text_delta":
                    text_parts.append(event.get("text", ""))
                    if on_partial:
                        accumulated = "".join(text_parts)
                        # JSON 可能包在 markdown ```json fence 里——剥掉前导
                        if accumulated.lstrip().startswith("```"):
                            stripped = accumulated.lstrip()
                            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
                            accumulated = stripped
                        parsed = try_partial_parse(accumulated)
                        if parsed:
                            new_keys = set(parsed.keys()) - partial_signaled
                            if new_keys:
                                partial_signaled |= new_keys
                                try:
                                    on_partial(parsed)
                                except Exception:  # noqa: BLE001
                                    logger.warning(
                                        "director.on_partial_failed", exc_info=True
                                    )
                elif event["type"] == "usage":
                    usage_data = event
                    finish_reason = event.get("finish_reason")
        except Exception as exc:  # noqa: BLE001
            logger.warning("director_v2.json_mode_provider_failed", error=str(exc))
            return None

        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
            # Truncation salvage: the streaming path already partial-parses the
            # buffer (on_partial above). Reuse it at the terminal state so a
            # mid-stream cut (gateway clipping the climax payload, finish_reason
            # =length) still yields the FRONT of the JSON — 救回 scene_brief /
            # ending_triggered，把整回合软失败降级成记账丢失，并让结局 AI 层复活。
            # 只在抢救出 load-bearing 字段时采用，否则照常走下面的重试。
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            salvaged = try_partial_parse(salvage_src)
            if salvaged and (salvaged.get("scene_brief") or salvaged.get("ending_triggered")):
                logger.warning(
                    "director_v2.json_mode_salvaged",
                    finish_reason=finish_reason,
                    output_chars=len(raw),
                    salvaged_keys=sorted(salvaged.keys()),
                )
                return usage_data, salvaged
            # Distinguish the failure modes the DeepSeek docs call out so the
            # admin parse-failure metric is actionable, not a black box:
            # truncation (finish_reason=length) vs empty content (known
            # probabilistic API issue) vs malformed JSON.
            if finish_reason == "length":
                reason = "truncated"
            elif not raw.strip():
                reason = "empty"
            else:
                reason = "malformed"
            logger.warning(
                "director_v2.json_mode_parse_failed",
                failure=reason,
                finish_reason=finish_reason,
                output_chars=len(raw),
                preview=raw[:200] if raw else "<empty>",
            )
            return None
        return usage_data, tool_input

    async def _run_tool_use(
        self,
        *,
        system: str,
        messages: list[dict],
        director_tool: dict,
        recall_fn: Callable[[str, int], list[dict]] | None,
        tool_choice: str | dict | None = None,
    ) -> DirectorResult:
        tools = [director_tool]
        if recall_fn:
            tools.append(RECALL_MEMORY_TOOL)
        # When a tool_choice is forced AND recall is enabled, we cannot
        # force a specific tool — the model needs auto to pick recall when
        # it wants. Fall back to auto in that case.
        effective_tool_choice = tool_choice
        if recall_fn and isinstance(tool_choice, dict):
            effective_tool_choice = None

        usage_data = None
        for _ in range(3):
            tool_input: dict | None = None
            recall_request: dict | None = None

            stream_kwargs: dict = {
                "messages": messages,
                "tools": tools,
                "system": system,
            }
            if effective_tool_choice is not None:
                stream_kwargs["tool_choice"] = effective_tool_choice

            async for event in self.llm_router.stream_with_tools(**stream_kwargs):
                if event["type"] == "tool_use" and event.get("name") == director_tool["name"]:
                    tool_input = event.get("input") or {}
                elif event["type"] == "tool_use" and event.get("name") == RECALL_MEMORY_TOOL["name"]:
                    recall_request = event.get("input") or {}
                elif event["type"] == "usage":
                    usage_data = event

            if tool_input:
                return self._build_result(tool_input, usage_data)

            if recall_request and recall_fn:
                keyword = str(recall_request.get("keyword") or "")
                max_results = int(recall_request.get("max_results") or 3)
                results = recall_fn(keyword, max_results)
                recall_text = (
                    "\n".join(f"[第{item.get('round', '?')}轮] {item.get('content', '')}" for item in results)
                    if results
                    else "未找到相关记录"
                )
                messages.append({"role": "assistant", "content": f"[recall_memory 结果]\n{recall_text}"})
                messages.append({"role": "user", "content": "请根据以上信息做出决策。"})
                continue

            break

        # Phase 2.A.3 — three internal attempts produced no tool_use payload.
        # Surface as a typed parse error so orchestrator can emit an SSE
        # `llm_parse` error instead of silently degrading to a placeholder
        # scene. Caller (`Director.run`) does one agent-level retry before
        # the error propagates further.
        logger.warning(
            "director.parse_failure",
            attempts=3,
            reason="no_tool_use_payload",
        )
        raise DirectorParseError("Director produced no tool_use payload after 3 attempts")

    async def _run_json_mode(
        self,
        *,
        system: str,
        messages: list[dict],
        schema: dict,
    ) -> DirectorResult | None:
        """Native JSON mode for reasoning models.

        Uses ``llm_router.stream_json()`` (provider-native ``response_format``
        with no tool plumbing). Strips ``<think>...</think>`` blocks that
        reasoning models emit before the actual JSON. Returns None on parse
        failure so caller can retry with mutated prompt.
        """
        json_system = "\n\n".join([system, build_director_json_instruction(schema)])
        text_parts: list[str] = []
        usage_data = None
        try:
            async for event in self.llm_router.stream_json(
                messages=messages,
                system=json_system,
                max_tokens=4096,
            ):
                if event["type"] == "text_delta":
                    text_parts.append(event.get("text", ""))
                elif event["type"] == "usage":
                    usage_data = event
        except Exception as exc:  # noqa: BLE001
            logger.warning("director.json_mode_provider_failed", error=str(exc))
            return None

        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            salvaged = try_partial_parse(salvage_src)
            if salvaged and (salvaged.get("scene_brief") or salvaged.get("ending_triggered")):
                logger.warning(
                    "director.json_mode_salvaged",
                    salvaged_keys=sorted(salvaged.keys()),
                )
                return self._build_result(salvaged, usage_data)
            logger.warning(
                "director.json_mode_parse_failed",
                preview=raw[:200] if raw else "<empty>",
            )
            return None

        return self._build_result(tool_input, usage_data)

    async def generate_case_board_ops(
        self,
        *,
        scene_brief: str,
        new_clues: list,
        current_board: dict,
        script_type: str,
        discovered_clue_ids: list[str],
    ) -> list[dict]:
        """Two-pass case board — a lean standalone JSON call producing
        case_board_ops off the player's critical path. Runs after `done`, so a
        truncation here only affects the case board (non-fatal), never the
        narrative or ending. Returns [] on any failure."""
        import json as _json

        from engine.prompts import (
            build_case_board_generation_prompt,
            build_case_board_ops_schema,
        )

        schema = build_case_board_ops_schema()
        system = (
            build_case_board_generation_prompt(script_type, discovered_clue_ids)
            + "\n\n### JSON Schema\n```\n"
            + _json.dumps(schema, ensure_ascii=False)
            + "\n```"
        )
        user = _json.dumps(
            {
                "scene_brief": scene_brief,
                "new_clues": new_clues,
                "current_case_board": current_board,
            },
            ensure_ascii=False,
        )
        text_parts: list[str] = []
        try:
            async for event in self.llm_router.stream_json(
                messages=[{"role": "user", "content": user}],
                system=system,
                max_tokens=2048,
            ):
                if event["type"] == "text_delta":
                    text_parts.append(event.get("text", ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning("case_board_two_pass.provider_failed", error=str(exc))
            return []

        raw = "".join(text_parts)
        parsed = _extract_json_from_text(raw)
        if parsed is None:
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            parsed = try_partial_parse(salvage_src) or {}
        ops = parsed.get("case_board_ops")
        return ops if isinstance(ops, list) else []
