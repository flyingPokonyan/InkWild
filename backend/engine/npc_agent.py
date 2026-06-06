from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from engine.npc_action import NPC_ACTION_SCHEMA, NPCAction, validate_action
from engine.npc_tools import (
    FINALIZE_ACTION_TOOL_NAME,
    ToolContext,
    build_finalize_action_tool,
    execute_tool,
    npc_query_tools,
)
from engine.prompts import build_npc_system, build_npc_system_v2
from llm.router import LLMRouter

logger = structlog.get_logger()


@dataclass
class NPCResult:
    npc_name: str
    dialogue: str
    usage: dict | None = None


class NPCAgent:
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def run(
        self,
        npc_name: str,
        npc_personality: str,
        npc_secret: str | None,
        instruction: str,
        recent_messages: list[dict],
        npc_memories: list[dict] | None = None,
        npc_relation: dict | None = None,
        reflection: str | None = None,
        voice_anchor: list[str] | None = None,
        voice_style: str | None = None,
        world_setting: str | None = None,
        knowledge: list[str] | None = None,
        scene_context: dict | None = None,
        current_intent: dict | None = None,
        peer_dialogues_so_far: list[dict] | None = None,
        peer_relations: list[dict] | None = None,
        recent_player_actions: list[dict] | None = None,
        player_identity: dict | None = None,
        # v2 NPC injection fields (§7.1)
        relevant_lore: list[dict] | None = None,
        involved_shared_events: list[dict] | None = None,
        relevant_rumors: list[str] | None = None,
    ) -> NPCResult:
        relation = npc_relation or {}
        system = build_npc_system(
            npc_name=npc_name,
            npc_personality=npc_personality,
            npc_secret=npc_secret,
            instruction=instruction,
            player_identity=player_identity,
            memories=npc_memories or [],
            trust=int(relation.get("trust", 3)),
            mood=str(relation.get("mood", "正常")),
            reflection=reflection,
            voice_anchor=voice_anchor, voice_style=voice_style,
            world_setting=world_setting,
            knowledge=knowledge,
            scene_context=scene_context,
            current_intent=current_intent,
            peer_dialogues_so_far=peer_dialogues_so_far,
            peer_relations=peer_relations,
            recent_player_actions=recent_player_actions,
            relevant_lore=relevant_lore,
            involved_shared_events=involved_shared_events,
            relevant_rumors=relevant_rumors,
        )
        messages = [*recent_messages[-4:], {"role": "user", "content": f"导演指令：{instruction}"}]

        dialogue_parts: list[str] = []
        usage_data = None

        async for event in self.llm_router.stream_with_tools(messages=messages, tools=[], system=system):
            if event["type"] == "text_delta":
                dialogue_parts.append(event.get("text", ""))
            elif event["type"] == "usage":
                usage_data = event

        return NPCResult(npc_name=npc_name, dialogue="".join(dialogue_parts), usage=usage_data)

    # ------------------------------------------------------------------
    # v2: structured action with tool use
    # ------------------------------------------------------------------

    async def run_v2(
        self,
        *,
        npc_name: str,
        npc_personality: str,
        npc_secret: str | None,
        scene_brief: str,
        per_npc_focus: str,
        scene_role: str,
        dramatic_intensity: str,
        recent_messages: list[dict],
        tool_context: ToolContext,
        npc_memories: list[dict] | None = None,
        npc_relation: dict | None = None,
        reflection: str | None = None,
        voice_anchor: list[str] | None = None,
        voice_style: str | None = None,
        world_setting: str | None = None,
        knowledge: list[str] | None = None,
        scene_context: dict | None = None,
        current_intent: dict | None = None,
        peer_relations: list[dict] | None = None,
        recent_player_actions: list[dict] | None = None,
        player_identity: dict | None = None,
        relevant_lore: list[dict] | None = None,
        involved_shared_events: list[dict] | None = None,
        relevant_rumors: list[str] | None = None,
        peer_dialogues_last_turn: list[dict] | None = None,
        active_npcs: list[str] | None = None,
        known_npcs: set[str] | None = None,
        max_tool_calls: int = 3,
    ) -> NPCAction:
        """v2 NPC turn: structured NPCAction with optional tool calls.

        Selective depth — driven by ``dramatic_intensity``:
        - low/medium → single LLM call, no tools (tools attached only as
          finalize_action; if model still calls a query tool we honour it
          but baseline path doesn't advertise them)
        - high → tools enabled, up to ``max_tool_calls`` queries before
          finalize
        - climax → reflect-step then act-step, both with tools

        Failures fall back to an omitted ``NPCAction`` (NPC visibly silent).
        """
        # Climax reflect+act (2 LLM chains) is reserved for the dramatic focus
        # (scene_role="primary"). Secondary/background NPCs at climax fall
        # through to a single-pass call — they're reacting, not the deep
        # decision point, so doubling their round-trips isn't worth the latency.
        if dramatic_intensity == "climax" and scene_role == "primary":
            return await self._run_v2_climax(
                npc_name=npc_name,
                npc_personality=npc_personality,
                npc_secret=npc_secret,
                player_identity=player_identity,
                scene_brief=scene_brief,
                per_npc_focus=per_npc_focus,
                scene_role=scene_role,
                dramatic_intensity=dramatic_intensity,
                recent_messages=recent_messages,
                tool_context=tool_context,
                npc_memories=npc_memories,
                npc_relation=npc_relation,
                reflection=reflection,
                voice_anchor=voice_anchor, voice_style=voice_style,
                world_setting=world_setting,
                knowledge=knowledge,
                scene_context=scene_context,
                current_intent=current_intent,
                peer_relations=peer_relations,
                recent_player_actions=recent_player_actions,
                relevant_lore=relevant_lore,
                involved_shared_events=involved_shared_events,
                relevant_rumors=relevant_rumors,
                peer_dialogues_last_turn=peer_dialogues_last_turn,
                active_npcs=active_npcs,
                known_npcs=known_npcs,
                max_tool_calls=max_tool_calls,
            )

        use_tools = dramatic_intensity in {"high", "climax"}
        return await self._run_v2_single(
            npc_name=npc_name,
            npc_personality=npc_personality,
            npc_secret=npc_secret,
            player_identity=player_identity,
            scene_brief=scene_brief,
            per_npc_focus=per_npc_focus,
            scene_role=scene_role,
            dramatic_intensity=dramatic_intensity,
            recent_messages=recent_messages,
            tool_context=tool_context,
            npc_memories=npc_memories,
            npc_relation=npc_relation,
            reflection=reflection,
            voice_anchor=voice_anchor, voice_style=voice_style,
            world_setting=world_setting,
            knowledge=knowledge,
            scene_context=scene_context,
            current_intent=current_intent,
            peer_relations=peer_relations,
            recent_player_actions=recent_player_actions,
            relevant_lore=relevant_lore,
            involved_shared_events=involved_shared_events,
            relevant_rumors=relevant_rumors,
            peer_dialogues_last_turn=peer_dialogues_last_turn,
            active_npcs=active_npcs,
            known_npcs=known_npcs,
            use_tools=use_tools,
            max_tool_calls=max_tool_calls,
            enable_climax_reflect=False,
        )

    async def _run_v2_single(
        self,
        *,
        npc_name: str,
        npc_personality: str,
        npc_secret: str | None,
        player_identity: dict | None = None,
        scene_brief: str,
        per_npc_focus: str,
        scene_role: str,
        dramatic_intensity: str,
        recent_messages: list[dict],
        tool_context: ToolContext,
        npc_memories: list[dict] | None,
        npc_relation: dict | None,
        reflection: str | None,
        voice_anchor: list[str] | None,
        voice_style: str | None,
        world_setting: str | None,
        knowledge: list[str] | None,
        scene_context: dict | None,
        current_intent: dict | None,
        peer_relations: list[dict] | None,
        recent_player_actions: list[dict] | None,
        relevant_lore: list[dict] | None,
        involved_shared_events: list[dict] | None,
        relevant_rumors: list[str] | None,
        peer_dialogues_last_turn: list[dict] | None,
        active_npcs: list[str] | None,
        known_npcs: set[str] | None,
        use_tools: bool,
        max_tool_calls: int,
        enable_climax_reflect: bool,
        extra_user_prefix: str | None = None,
    ) -> NPCAction:
        relation = npc_relation or {}
        system = build_npc_system_v2(
            npc_name=npc_name,
            npc_personality=npc_personality,
            npc_secret=npc_secret,
            player_identity=player_identity,
            scene_brief=scene_brief,
            per_npc_focus=per_npc_focus,
            scene_role=scene_role,
            dramatic_intensity=dramatic_intensity,
            memories=npc_memories or [],
            trust=int(relation.get("trust", 3)),
            mood=str(relation.get("mood", "正常")),
            relationship_note=(str(relation.get("note") or "").strip() or None),
            reflection=reflection,
            voice_anchor=voice_anchor, voice_style=voice_style,
            world_setting=world_setting,
            knowledge=knowledge,
            scene_context=scene_context,
            current_intent=current_intent,
            peer_relations=peer_relations,
            recent_player_actions=recent_player_actions,
            relevant_lore=relevant_lore,
            involved_shared_events=involved_shared_events,
            relevant_rumors=relevant_rumors,
            peer_dialogues_last_turn=peer_dialogues_last_turn,
            use_tools=use_tools,
            enable_climax_reflect=enable_climax_reflect,
        )

        tools: list[dict] = []
        if use_tools:
            tools.extend(npc_query_tools())
        tools.append(build_finalize_action_tool(NPC_ACTION_SCHEMA))

        opening = extra_user_prefix or (
            f"请按你 ({npc_name}) 的判断决定本轮行动，然后调用 finalize_action 提交。"
        )
        messages = [
            *recent_messages[-4:],
            {"role": "user", "content": opening},
        ]

        finalize_payload: dict | None = None
        usage_data: dict | None = None
        tool_query_count = 0

        # Up to 4 iterations: query → query → query → finalize (cap).
        for _ in range(max_tool_calls + 2):
            event_tool_use: list[dict] = []
            try:
                async for event in self.llm_router.stream_with_tools(
                    messages=messages,
                    tools=tools,
                    system=system,
                ):
                    if event["type"] == "tool_use":
                        event_tool_use.append(event)
                    elif event["type"] == "usage":
                        usage_data = event
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "npc_agent_v2.stream_failed",
                    npc=npc_name,
                    error=str(exc),
                )
                break

            if not event_tool_use:
                # Model produced no tool call — treat as omitted.
                logger.warning("npc_agent_v2.no_tool_call", npc=npc_name)
                break

            finalize_seen = False
            for event in event_tool_use:
                name = event.get("name", "")
                tool_input = event.get("input") or {}
                if name == FINALIZE_ACTION_TOOL_NAME:
                    finalize_payload = tool_input
                    finalize_seen = True
                    break
                # query tool
                if tool_query_count >= max_tool_calls:
                    logger.info(
                        "npc_agent_v2.tool_call_cap_hit",
                        npc=npc_name,
                        cap=max_tool_calls,
                    )
                    continue
                tool_query_count += 1
                result = await execute_tool(name, tool_input, tool_context)
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"[{name} 结果] {result}",
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "查询完成。如还需查询请继续；否则**立刻**调用 finalize_action 提交本轮行动。"
                            if tool_query_count < max_tool_calls
                            else "你已用完查询次数。请**立刻**调用 finalize_action 提交本轮行动。"
                        ),
                    }
                )

            if finalize_seen:
                break

        # Probe: each query tool call is a sequential LLM round-trip, so a
        # high count is a prime suspect when an NPC turn is slow (the NPC
        # block is gated by the slowest NPC's chain). Lets us confirm whether
        # late-game high-intensity turns blow up on tool rounds.
        logger.info(
            "npc_v2.tool_rounds",
            npc=npc_name,
            tool_query_count=tool_query_count,
            finalized=finalize_payload is not None,
        )

        action = validate_action(
            npc_name=npc_name,
            raw=finalize_payload,
            scene_role=scene_role,
            known_npcs=known_npcs,
            active_npcs=set(active_npcs or []),
            usage=usage_data,
        )
        return action

    async def _run_v2_climax(self, **kwargs) -> NPCAction:
        """Climax: reflect step then act step. Reflect failure → fall back
        to baseline; act failure → omitted."""
        from config import settings

        reflect_user = (
            f"这是 climax 时刻。先以**内部独白**评估：你面临什么 stake？"
            f"最坏情况是什么？你有哪些选项？最终策略是什么？"
            f"评估结束后调用 finalize_action 时，请用 action_type=scheme 并把策略写进 hidden_note "
            f"（≤80 字，「我打算 X，理由 Y」）。"
        )

        timeout = settings.npc_climax_step_timeout_seconds
        npc_name = kwargs["npc_name"]

        # --- step 1: reflect ---
        try:
            reflect_action = await asyncio.wait_for(
                self._run_v2_single(
                    enable_climax_reflect=True,
                    use_tools=True,
                    extra_user_prefix=reflect_user,
                    **kwargs,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("npc_agent_v2.climax_reflect_timeout", npc=npc_name)
            reflect_action = None
        except Exception:  # noqa: BLE001
            logger.warning("npc_agent_v2.climax_reflect_failed", npc=npc_name, exc_info=True)
            reflect_action = None

        strategy = ""
        if reflect_action and reflect_action.hidden_note:
            strategy = reflect_action.hidden_note

        # --- step 2: act ---
        act_user = (
            f"刚才你已完成内部评估：「{strategy}」。" if strategy else
            "（评估步骤跳过，直接决断。）"
        ) + " 现在请决定本轮实际行动并调用 finalize_action 提交。"

        try:
            act_action = await asyncio.wait_for(
                self._run_v2_single(
                    enable_climax_reflect=False,
                    use_tools=True,
                    extra_user_prefix=act_user,
                    **kwargs,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("npc_agent_v2.climax_act_timeout", npc=npc_name)
            return validate_action(
                npc_name=npc_name,
                raw=None,
                scene_role=kwargs.get("scene_role"),
                known_npcs=kwargs.get("known_npcs"),
                active_npcs=set(kwargs.get("active_npcs") or []),
            )
        except Exception:  # noqa: BLE001
            logger.warning("npc_agent_v2.climax_act_failed", npc=npc_name, exc_info=True)
            return validate_action(
                npc_name=npc_name,
                raw=None,
                scene_role=kwargs.get("scene_role"),
                known_npcs=kwargs.get("known_npcs"),
                active_npcs=set(kwargs.get("active_npcs") or []),
            )

        # Stitch reflect's hidden_note onto act so the strategy persists.
        if strategy and not act_action.hidden_note:
            act_action.hidden_note = strategy[:80]
        return act_action
