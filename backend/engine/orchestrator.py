from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import structlog

from engine.compressor import (
    build_compression_prompt,
    claim_compression_round,
    estimate_messages_token_count,
    estimate_token_count,
    merge_context_summary,
)
from config import settings
from engine.action_segmentation import (
    consume_pending_segment,
    segment_player_action,
)
from engine.case_board import CaseBoardError, apply_case_board_ops
from engine.content_filter import check_input_moderated, check_output_moderated
from engine.director_agent import (
    DirectorAgent,
    DirectorParseError,
    DirectorResult,
    DirectorUpstreamError,
)
from engine.ending_system import check_forced_ending, check_hard_endings, merge_ai_ending_judgment
from engine.event_system import apply_event_effects, check_events
from engine.memory_manager import MemoryManager
from engine.narrative_arc import ACT_CLIMAX, ArcData, NarrativeArcTracker
from engine.narrator_agent import NarratorAgent
from engine.narrator_context import filter_recent_messages_for_narrator
from engine.npc_action import NPCAction
from engine.npc_agent import NPCAgent, NPCResult
from engine.npc_catchup import apply_catchup_to_state, run_catchup
from engine.npc_tools import ToolContext
from engine.offstage_scheduler import (
    append_log_entries,
    collect_triggers,
    should_run_periodic_tick,
)
from engine.player_input_guard import assess_input_strength
from engine.processing_hint import build_phase_hint, build_processing_hint
from engine.prompts import (
    _extract_time_slot,
    build_npc_schedule_context,
    build_resolution_directive,
    build_world_pulse_directive,
)
from engine.state_manager import (
    PLAYER_ACTIONS_HISTORY_LIMIT,
    GameState,
    append_discovered_clue,
    apply_state_updates,
)
from engine.world_simulator import TickResult, WorldSimulator
from llm.usage_context import usage_context

logger = structlog.get_logger()


def _merge_usage(*usages: dict | None) -> dict | None:
    """Sum input/output tokens across multiple usage events; return None if all None.

    Preserves the first non-empty ``provider_name`` / ``model_id`` so cost
    tracking can attribute the merged turn to the slot that produced the
    primary narrator output.
    """
    real = [u for u in usages if u]
    if not real:
        return None
    merged: dict = {
        "type": "usage",
        "input_tokens": sum(int(u.get("input_tokens", 0) or 0) for u in real),
        "output_tokens": sum(int(u.get("output_tokens", 0) or 0) for u in real),
    }
    for u in real:
        provider_name = u.get("provider_name")
        if provider_name and "provider_name" not in merged:
            merged["provider_name"] = provider_name
        model_id = u.get("model_id")
        if model_id and "model_id" not in merged:
            merged["model_id"] = model_id
        if "provider_name" in merged and "model_id" in merged:
            break
    return merged


def _emit_stage_timing(stage: str, started: float, **fields) -> None:
    """Log a structured timing event for an orchestrator stage."""
    logger.info(
        "stage.timing",
        stage=stage,
        duration_ms=round((time.perf_counter() - started) * 1000),
        **fields,
    )


async def _resolve_moderation_router(db):
    if db is None:
        return None
    try:
        from services.model_management import resolve_slot_router

        return await resolve_slot_router(db, "moderation_slot")
    except Exception:
        logger.warning("moderation_slot_resolve_failed", exc_info=True)
        return None


def should_trigger_stage_summary(state: GameState) -> bool:
    if not state.npc_intents and not state.world_conflicts:
        return False

    if not state.npc_intents:
        return False

    high_urgency_count = sum(
        1
        for intent in state.npc_intents.values()
        if isinstance(intent, dict) and float(intent.get("urgency", 0)) >= 8
    )

    if state.last_stage_summary_round == 0:
        return state.round_number >= 20 and (high_urgency_count > 0 or bool(state.world_conflicts))

    return state.round_number - state.last_stage_summary_round >= 30


def build_stage_summary_instruction(state: GameState) -> str:
    world_tensions = [
        str(conflict.get("description", ""))
        for conflict in state.world_conflicts
        if conflict.get("description")
    ]
    urgent_goals = [
        f"{npc_name}：{intent.get('current_goal', '')}"
        for npc_name, intent in state.npc_intents.items()
        if isinstance(intent, dict) and float(intent.get("urgency", 0)) >= 8
    ]

    details: list[str] = []
    if world_tensions:
        details.append("当前暗流：" + "；".join(world_tensions[:2]))
    if urgent_goals:
        details.append("高压行动：" + "；".join(urgent_goals[:3]))

    extra = "\n".join(details) if details else "回顾玩家已经搅动起来的世界张力。"
    return (
        "请在本轮叙事结尾补上一段简短的章节总结，用叙事化语言回顾当前阶段的变化，"
        "不要暴露系统机制或指标。\n"
        f"{extra}"
    )


class Orchestrator:
    def __init__(
        self,
        llm_router,
        compression_llm_router=None,
        ending_summary_llm_router=None,
        npc_llm_router=None,
        director_agent: DirectorAgent | None = None,
        npc_agent: NPCAgent | None = None,
        narrator_agent: NarratorAgent | None = None,
        memory_manager: MemoryManager | None = None,
        world_simulator: WorldSimulator | None = None,
    ):
        self.llm_router = llm_router
        self.compression_llm_router = compression_llm_router or llm_router
        self.ending_summary_llm_router = ending_summary_llm_router or llm_router
        self.npc_llm_router = npc_llm_router or llm_router
        # Director dispatch mode is decided by per-model capability lookup
        # at run() time (see engine/director_agent.py). The legacy
        # ``director_prefer_json_mode`` config flag is no longer consulted
        # — if set in env it has no effect; remove on next config sweep.
        self.director_agent = director_agent or DirectorAgent(llm_router)
        self.npc_agent = npc_agent or NPCAgent(self.npc_llm_router)
        self.narrator_agent = narrator_agent or NarratorAgent(llm_router)
        self.memory_manager = memory_manager or MemoryManager()
        self.world_simulator = world_simulator or WorldSimulator()
        self.narrative_arc_tracker = NarrativeArcTracker()

    def _resolve_ending(
        self,
        world_data: dict,
        state,
        game_mode: str,
        director_result,
        *,
        session_id: str | None,
        round_number: int,
    ) -> dict | None:
        """Resolve this turn's ending across all three triggers + log the path.

        Order: authored hard_conditions → Director's ``ending_triggered`` →
        architectural stall floor (``check_forced_ending``). The floor only
        matters in script mode and only when the session has stalled, so a
        normally-progressing or free session is unaffected.
        """
        endings = world_data.get("endings", [])
        ending: dict | None = None
        path: str | None = None

        hard_ending = check_hard_endings(endings, state, game_mode)
        if hard_ending:
            ending, path = hard_ending, "hard"
        elif director_result.ending_triggered:
            ending = merge_ai_ending_judgment(endings, director_result.ending_triggered)
            path = "ai" if ending else None

        if ending is None:
            forced = check_forced_ending(endings, state, game_mode)
            if forced:
                ending, path = forced, "forced"

        if ending is not None:
            logger.info(
                "ending.resolved",
                path=path,
                ending_type=ending.get("ending_type"),
                session_id=session_id,
                round_number=round_number,
                rounds_in_climax=getattr(state, "rounds_in_climax", 0),
                rounds_since_last_clue=getattr(state, "rounds_since_last_clue", 0),
            )
        return ending

    def _claim_compression(self, state) -> bool:
        """Decide whether to compact this turn and, if so, stamp the debounce
        counter on the turn's owned ``state``.

        MUST be called BEFORE the turn emits its state snapshot (state_ready /
        state_update): the early-stream path commits state at state_ready, so a
        stamp written afterward is lost + clobbered, and compaction re-fires
        every round (last_compressed_round stuck at 0). The detached compaction
        task must NOT own this counter — see claim_compression_round.
        """
        claimed = claim_compression_round(
            state.round_number, state.last_compressed_round, threshold=20
        )
        if claimed is None:
            return False
        state.last_compressed_round = claimed
        return True

    def _schedule_compression(self, session_id: str, rounds_played: int) -> None:
        # Compaction opens its own AsyncSession because the caller's
        # request-scoped session is closed by FastAPI before this
        # fire-and-forget task actually runs — that's the root cause of the
        # 2026-05-27 "compression never fires" bug.
        asyncio.create_task(
            self._run_compression_with_retry(
                session_id=session_id,
                rounds_played=rounds_played,
                trigger_reason="threshold",
            )
        )

    async def _run_compression_with_retry(
        self,
        session_id: str,
        rounds_played: int,
        trigger_reason: str,
        max_attempts: int = 2,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                await self._run_compression(
                    session_id=session_id,
                    rounds_played=rounds_played,
                    trigger_reason=trigger_reason,
                    attempt=attempt,
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "compressor.retry",
                    session_id=session_id,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exc_info=True,
                )

        logger.warning(
            "compressor.run",
            session_id=session_id,
            trigger_reason=trigger_reason,
            tokens_before=0,
            tokens_after=0,
            duration_ms=0,
            outcome="failed",
            attempts=max_attempts,
            error=str(last_error) if last_error else None,
        )

    async def _run_compression(
        self,
        session_id: str,
        rounds_played: int,
        trigger_reason: str = "manual",
        attempt: int = 1,
    ) -> None:
        from database import async_session

        started_at = time.perf_counter()
        tokens_before = 0
        tokens_after = 0
        outcome = "skipped"

        # Open an independent DB session — caller's request scope is gone by
        # the time this fire-and-forget task runs.
        async with async_session() as db:
            try:
                from sqlalchemy import select
                from models.game import Message

                result = await db.execute(
                    select(Message)
                    .where(
                        Message.session_id == session_id,
                        Message.is_compressed.is_(False),
                    )
                    .order_by(Message.created_at.asc())
                )
                all_msgs = result.scalars().all()
                # Keep the most recent 15 rounds (30 messages), compress the rest
                if len(all_msgs) <= 30:
                    outcome = "skipped_too_few_messages"
                    return
                old_msgs = all_msgs[:-30]
                formatted = [{"role": msg.role, "content": msg.content} for msg in old_msgs]
                if not formatted:
                    outcome = "skipped_empty"
                    return

                tokens_before = estimate_messages_token_count(formatted)
                prompt = build_compression_prompt(formatted)
                summary_parts: list[str] = []
                # Override inherited ``game`` purpose so compression spend is
                # bucketed separately in admin analytics.
                with usage_context(purpose="compression", session_id=session_id):
                    async for event in self.compression_llm_router.stream_with_tools(
                        messages=[{"role": "user", "content": prompt}],
                        tools=[],
                        system="你是一个对话压缩助手。请将对话压缩为简洁摘要。",
                        max_tokens=1024,
                    ):
                        if event.get("type") == "text_delta":
                            summary_parts.append(event.get("text", ""))

                summary = "".join(summary_parts).strip()
                if not summary:
                    outcome = "skipped_empty_summary"
                    return
                tokens_after = estimate_token_count(summary)

                from models.game import GameSession
                session = await db.get(GameSession, session_id)
                if session:
                    session.context_summary = merge_context_summary(
                        session.context_summary, summary
                    )
                for msg in old_msgs:
                    msg.is_compressed = True

                # last_compressed_round is stamped by the main loop on the
                # turn's GameState (see _maybe_compress / claim_compression_round)
                # — NOT written here: this detached session + plain-JSON column
                # would silently drop it and the main loop would clobber it.

                await db.commit()
                outcome = "success"
            except Exception:
                outcome = "failed"
                await db.rollback()
                raise
            finally:
                logger.info(
                    "compressor.run",
                    session_id=session_id,
                    trigger_reason=trigger_reason,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    outcome=outcome,
                    attempt=attempt,
                )

    async def process_action(
        self,
        action_text: str,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        game_mode: str,
        memory_context: str = "",
        authors_note: str | None = None,
        memory_entries: list[dict] | None = None,
        all_messages: list[dict] | None = None,
        session_id: str | None = None,
        round_number: int = 0,
        db=None,
        known_npcs: list[str] | None = None,
        emit_state_ready: bool = False,
    ) -> AsyncIterator[dict]:
        # Runtime architecture v2 — feature-flagged dispatch. See
        # docs/plans/runtime-architecture-overhaul-2026-05.md for the new
        # pipeline shape. Legacy path below is left untouched.
        if settings.runtime_architecture_v2_enabled:
            async for event in self._process_action_v2(
                action_text=action_text,
                game_state=game_state,
                recent_messages=recent_messages,
                context_summary=context_summary,
                world_data=world_data,
                game_mode=game_mode,
                memory_context=memory_context,
                authors_note=authors_note,
                memory_entries=memory_entries,
                all_messages=all_messages,
                session_id=session_id,
                round_number=round_number,
                db=db,
                known_npcs=known_npcs,
                emit_state_ready=emit_state_ready,
            ):
                yield event
            return

        turn_started = time.perf_counter()
        moderation_router = await _resolve_moderation_router(db)

        moderation_input_started = time.perf_counter()
        filter_result = await check_input_moderated(action_text, llm_router=moderation_router)
        _emit_stage_timing(
            "moderation_input",
            moderation_input_started,
            session_id=session_id,
            round_number=round_number,
            outcome="rejected" if not filter_result.is_safe else "passed",
        )
        if not filter_result.is_safe:
            yield {"type": "error", "code": 40001, "message": filter_result.reason}
            return

        structured_memory_context = self.memory_manager.build_memory_context(memory_entries or [])
        world_conflict_context = ""
        if game_state.world_conflicts:
            conflict_lines = [
                f"- {conflict.get('description', '')}"
                for conflict in game_state.world_conflicts
                if conflict.get("description")
            ]
            if conflict_lines:
                world_conflict_context = "## 世界张力\n" + "\n".join(conflict_lines)

        npc_schedule_context = build_npc_schedule_context(
            world_data.get("npcs", []),
            current_time=game_state.current_time,
        )
        world_pulse = build_world_pulse_directive(game_state, game_mode)

        # --- WorldSimulator tick (task 9.1) ---
        world_tick_started = time.perf_counter()
        tick_result: TickResult = self.world_simulator.tick(game_state, world_data)
        game_state = tick_result.updated_state
        _emit_stage_timing(
            "world_tick",
            world_tick_started,
            session_id=session_id,
            round_number=round_number,
            world_event_count=len(tick_result.world_events),
        )

        # Build world events context for Director
        world_events_context = ""
        if tick_result.world_events:
            event_lines = [f"- [{e.event_type}] {e.description}" for e in tick_result.world_events]
            world_events_context = "【本轮世界事件】\n" + "\n".join(event_lines)

        env_changes_context = ""
        if tick_result.environment_changes:
            env_changes_context = "【环境变化】\n" + "\n".join(tick_result.environment_changes)

        # Build narrative arc summary for Director
        arc_data = ArcData.from_dict(game_state.narrative_arc) if game_state.narrative_arc else ArcData()
        arc_summary = self.narrative_arc_tracker.build_summary(arc_data)

        effective_memory_context = "\n".join(
            part
            for part in [
                memory_context,
                structured_memory_context,
                world_conflict_context,
                npc_schedule_context,
                world_pulse,
                world_events_context,
                env_changes_context,
                arc_summary,
            ]
            if part
        )

        recall_fn = None
        if all_messages:
            def recall_fn(keyword: str, max_results: int = 3) -> list[dict]:
                return self.memory_manager.search_messages(all_messages, keyword, max_results)

        # Surface a "directing" phase to the client before the (often-slowest) Director call,
        # so the UI can show progress instead of staying silent until NPCs return.
        yield build_phase_hint("directing", current_location=game_state.current_location)

        director_started = time.perf_counter()
        try:
            director_result = await self.director_agent.run(
                game_state=game_state,
                recent_messages=recent_messages,
                context_summary=context_summary,
                world_data=world_data,
                user_input=action_text,
                game_mode=game_mode,
                memory_context=effective_memory_context,
                authors_note=authors_note,
                recall_fn=recall_fn,
                script_type=world_data.get("script_type", ""),
            )
        except (DirectorParseError, DirectorUpstreamError) as exc:
            # Phase 2.A.3 — Director couldn't produce a usable decision. Surface
            # a typed SSE error so the UI can offer "retry round". Distinguish a
            # genuine parse failure (`llm_parse`) from an upstream/provider
            # failure (`provider_unavailable`, e.g. 402 balance) — the latter
            # must NOT be mislabeled "导演无法解析". Abort cleanly without
            # mutating game_state.
            upstream = isinstance(exc, DirectorUpstreamError)
            logger.warning(
                "director.unrecoverable",
                session_id=session_id,
                round_number=round_number,
                error=str(exc),
                upstream=upstream,
            )
            yield {
                "type": "error",
                "code": "provider_unavailable" if upstream else "llm_parse",
                "message": (
                    "AI 服务暂时不可用，请稍后再试"
                    if upstream
                    else "导演无法解析本轮指令，请重试该回合"
                ),
            }
            return
        _emit_stage_timing(
            "director",
            director_started,
            session_id=session_id,
            round_number=round_number,
            involved_npcs=len(director_result.involved_npcs),
        )

        npc_lookup = {npc["name"]: npc for npc in world_data.get("npcs", [])}

        # --- Phase 1.B.5: append typed player_action to game_state.player_actions ---
        # Director categorizes the player's input into a typed action; we keep
        # the most recent PLAYER_ACTIONS_HISTORY_LIMIT entries so NPC system
        # prompts can reference cross-turn player behavior (e.g. "你刚才连问
        # 三轮我关于遗嘱"). The action is stamped with the round it was
        # observed in so renderers can show a relative round number.
        if director_result.player_action is not None:
            entry = {
                "round": round_number,
                **director_result.player_action,
            }
            actions_history = list(game_state.player_actions or [])
            actions_history.append(entry)
            if len(actions_history) > PLAYER_ACTIONS_HISTORY_LIMIT:
                actions_history = actions_history[-PLAYER_ACTIONS_HISTORY_LIMIT:]
            game_state.player_actions = actions_history

        # --- Update narrative arc after Director result (task 9.2) ---
        # Phase 2.A.1 — pass round_number + discovered_clues_count so the
        # 3-act detector can recompute the current label each turn.
        arc_data = self.narrative_arc_tracker.update(
            arc_data,
            action_text,
            director_result.involved_npcs,
            game_state.current_location,
            round_number=round_number,
            discovered_clues_count=len(game_state.discovered_clues or []),
            dramatic_intensity=director_result.dramatic_intensity,
        )
        game_state.narrative_arc = arc_data.to_dict()

        # --- NPC-scoped memories from world events (task 9.2 / 0.A.3) ---
        dual_memory_entries: list[dict] = []
        if session_id:
            dual_memory_entries.extend(
                self.memory_manager.write_info_propagation_memories(
                    session_id=session_id,
                    round_number=round_number,
                    events=tick_result.world_events,
                )
            )
            for event in tick_result.world_events:
                if event.event_type == "npc_action" and len(event.involved_npcs) >= 2:
                    npc_a, npc_b = event.involved_npcs[0], event.involved_npcs[1]
                    dual_memory_entries.extend(
                        self.memory_manager.write_dual_perspective_memories(
                            session_id=session_id,
                            round_number=round_number,
                            npc_a=npc_a,
                            npc_b=npc_b,
                            event_description=event.description,
                            perspective_a=f"{npc_a}视角：{event.description}",
                            perspective_b=f"{npc_b}视角：{event.description}",
                        )
                    )
            # 0.A.3 余项 — Director 的 inform_npc_calls 显式写入 NPC 私有记忆。
            # 拒绝指向不存在的 NPC（防止 Director 幻觉造名字污染数据）。
            _importance_to_int = {"high": 8, "medium": 5, "low": 3}
            for call in director_result.inform_npc_calls or []:
                target_npc = str(call.get("npc") or "").strip()
                info = str(call.get("info") or "").strip()
                if not target_npc or not info:
                    continue
                if target_npc not in npc_lookup:
                    logger.warning(
                        "director_inform_npc_unknown",
                        target_npc=target_npc,
                        info_preview=info[:80],
                    )
                    continue
                dual_memory_entries.append(
                    {
                        "session_id": session_id,
                        "memory_type": "director_told",
                        "content": info,
                        "round_number": round_number,
                        "importance": _importance_to_int.get(
                            str(call.get("importance") or "high").lower(), 7
                        ),
                        "related_npc": target_npc,
                    }
                )

        # Phase 2.D.3 — batch fetch all NPCs' memories in one SQL query and
        # one embedding pass, eliminating the per-NPC N+1.
        batched_memories: dict[str, list[dict]] = {}
        valid_involved_names = [
            name for name in director_result.involved_npcs if npc_lookup.get(name)
        ]
        if db and session_id and valid_involved_names:
            try:
                batched_memories = await self.memory_manager.batch_query_npc_memories(
                    db,
                    session_id,
                    valid_involved_names,
                    query_text=action_text,
                )
            except Exception:
                logger.warning("npc_memory_batch_query_failed", exc_info=True)

        npc_tasks = []
        for npc_name in director_result.involved_npcs:
            npc_info = npc_lookup.get(npc_name)
            if not npc_info:
                continue

            # --- NPC independent memory injection (task 9.2) ---
            npc_memories = self.memory_manager.filter_npc_memory_entries(
                memory_entries or [],
                npc_name,
            )
            npc_memories.extend(batched_memories.get(npc_name, []))
            npc_relation: dict = game_state.npc_relations.get(npc_name, {})
            # Long-term reflection (NPC inner-monologue summary). Falls back
            # to None silently when the table doesn't exist (older session)
            # or the query fails.
            npc_reflection_text: str | None = None
            if db and session_id:
                try:
                    from services.npc_reflection_service import get_reflection

                    reflection_row = await get_reflection(db, session_id, npc_name)
                    if reflection_row:
                        npc_reflection_text = reflection_row.summary
                except Exception:
                    logger.warning(
                        "npc_reflection_load_failed",
                        npc_name=npc_name,
                        exc_info=True,
                    )
            # Voice anchor (1.B.4): re-feed the NPC its own last few
            # utterances so tone stays consistent across turns.
            npc_voice_anchor: list[str] = []
            if db and session_id:
                try:
                    npc_voice_anchor = await self.memory_manager.get_npc_recent_utterances(
                        db, session_id, npc_name, limit=3
                    )
                except Exception:
                    logger.warning(
                        "npc_voice_anchor_load_failed",
                        npc_name=npc_name,
                        exc_info=True,
                    )

            # NPC-2 — outgoing peer relations (A→? only). Reverse trust and
            # unrelated C↔D relations are filtered at the query layer.
            npc_peer_relations: list[dict] = []
            if settings.npc_peer_relations_enabled and db and session_id:
                try:
                    npc_peer_relations = await self.memory_manager.get_npc_peer_relations(
                        db, session_id, npc_name,
                    )
                except Exception:
                    logger.warning(
                        "npc_peer_relations_load_failed",
                        npc_name=npc_name,
                        exc_info=True,
                    )

            # Scene context — what this NPC perceives about the present moment.
            time_slot = _extract_time_slot(game_state.current_time or "")
            my_location = (
                npc_info.get("schedule", {}).get(time_slot)
                or npc_info.get("initial_location")
                or ""
            )
            peer_npcs: list[dict] = []
            for other in world_data.get("npcs", []):
                other_name = other.get("name")
                if not other_name or other_name == npc_name:
                    continue
                other_loc = (
                    other.get("schedule", {}).get(time_slot)
                    or other.get("initial_location")
                    or ""
                )
                if my_location and other_loc == my_location:
                    # Public personality only — never leak peers' secret.
                    peer_personality = str(other.get("personality") or "").strip()
                    if len(peer_personality) > 60:
                        peer_personality = peer_personality[:60].rstrip() + "…"
                    peer_npcs.append({"name": other_name, "personality": peer_personality})
            npc_scene_context = {
                "current_time": game_state.current_time,
                "my_location": my_location,
                "player_location": game_state.current_location,
                "peer_npcs": peer_npcs,
            }

            # Current intent — NPC's own internal pursuit, computed by intent_system.
            npc_current_intent = game_state.npc_intents.get(npc_name)

            # v2 NPC injection fields (§7.1) — per-NPC recall, guarded so
            # failures never block the NPC turn.
            npc_relevant_lore: list[dict] = self.memory_manager.find_relevant_lore(
                npc_knowledge=list(npc_info.get("knowledge") or []),
                lore_pack=world_data.get("lore_pack"),
                top_k=3,
            )
            npc_involved_shared_events: list[dict] = self.memory_manager.find_npc_shared_events(
                npc_name=npc_name,
                shared_events=world_data.get("shared_events"),
            )
            npc_relevant_rumors: list[str] = self.memory_manager.find_npc_rumors(
                npc_name=npc_name,
                events_data=world_data.get("events_data"),
                triggered_event_ids=getattr(game_state, "triggered_event_ids", set()),
            )

            npc_tasks.append(
                {
                    "name": npc_name,
                    "kwargs": {
                        "npc_name": npc_name,
                        "npc_personality": npc_info.get("personality", ""),
                        "voice_style": npc_info.get("voice_style", ""),
                        "npc_secret": npc_info.get("secret", ""),
                        "player_identity": world_data.get("player_public"),
                        "instruction": director_result.npc_instructions.get(npc_name, ""),
                        "recent_messages": [],
                        "npc_memories": npc_memories,
                        "npc_relation": npc_relation,
                        "reflection": npc_reflection_text,
                        "voice_anchor": npc_voice_anchor,
                        "world_setting": world_data.get("base_setting", ""),
                        "knowledge": list(npc_info.get("knowledge") or []),
                        "scene_context": npc_scene_context,
                        "current_intent": npc_current_intent,
                        "peer_relations": npc_peer_relations,
                        # Phase 1.B.5 — share the typed player-action history
                        # so NPCs can reference what the player has been doing
                        # across rounds. Shared object is read-only inside
                        # build_npc_system.
                        "recent_player_actions": list(game_state.player_actions or []),
                        # v2 NPC injection fields (§7.1)
                        "relevant_lore": npc_relevant_lore,
                        "involved_shared_events": npc_involved_shared_events,
                        "relevant_rumors": npc_relevant_rumors,
                    },
                }
            )

        # NPC-1 — sequential dialogue: pick speaker order from Director (or
        # fall back to involved_npcs order) and cap to npc_max_speakers_per_turn
        # so wall-time doesn't blow up. Trimmed-out NPCs still get memory-batch
        # query / reflection trigger via director_result.involved_npcs below;
        # they just don't speak this turn.
        sequential_mode = settings.npc_dialogue_sequential_enabled and bool(npc_tasks)
        if sequential_mode:
            valid_names = {t["name"] for t in npc_tasks}
            director_order = [
                name for name in director_result.npc_speech_order if name in valid_names
            ]
            order_names = director_order or [t["name"] for t in npc_tasks]
            max_speakers = max(1, settings.npc_max_speakers_per_turn)
            if len(order_names) > max_speakers:
                order_names = order_names[:max_speakers]
            task_by_name = {t["name"]: t for t in npc_tasks}
            npc_tasks = [task_by_name[name] for name in order_names]

        # Phase 2.D.3 — cap simultaneous NPC LLM calls per turn. In sequential
        # mode the semaphore is effectively a no-op (peak in-flight = 1) but
        # we keep it for the parallel fallback path.
        npc_semaphore = asyncio.Semaphore(max(1, settings.npc_max_concurrency))

        async def _run_npc_capped(kwargs: dict):
            async with npc_semaphore:
                return await self.npc_agent.run(**kwargs)

        async def _run_all_npcs() -> list:
            """Sequential: each NPC sees prior speakers' dialogue.
            Parallel: legacy gather (every NPC sees nothing from peers).

            Phase 2.A.3 — single-NPC failure must not crash the whole turn.
            Failed NPCs get an empty-dialogue placeholder + structlog warn;
            the turn proceeds with the remaining NPCs.
            """
            if sequential_mode:
                collected: list = []
                so_far: list[dict] = []
                for task in npc_tasks:
                    kwargs = dict(task["kwargs"])
                    kwargs["peer_dialogues_so_far"] = list(so_far)
                    try:
                        res = await _run_npc_capped(kwargs)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "npc.run_failed",
                            npc_name=task["name"],
                            error=str(exc),
                            error_type=exc.__class__.__name__,
                            session_id=session_id,
                            round_number=round_number,
                        )
                        res = NPCResult(npc_name=task["name"], dialogue="", usage=None)
                    collected.append(res)
                    if res.dialogue:
                        so_far.append({"npc_name": res.npc_name, "dialogue": res.dialogue})
                return collected
            raw_results = await asyncio.gather(
                *(_run_npc_capped(t["kwargs"]) for t in npc_tasks),
                return_exceptions=True,
            )
            normalized: list = []
            for raw, task in zip(raw_results, npc_tasks):
                if isinstance(raw, Exception):
                    logger.warning(
                        "npc.run_failed",
                        npc_name=task["name"],
                        error=str(raw),
                        error_type=raw.__class__.__name__,
                        session_id=session_id,
                        round_number=round_number,
                    )
                    normalized.append(NPCResult(npc_name=task["name"], dialogue="", usage=None))
                else:
                    normalized.append(raw)
            return normalized

        npc_dialogues: dict[str, str] = {}
        prelude_text: str | None = None  # prelude removed; kept None for downstream signature compat
        prelude_usage: dict | None = None
        timing_stage = "npc_sequential" if sequential_mode else "npc_parallel"

        # Prelude removed (BUGS #27 H3 / docs/plans/narrator-simplification-2026-05.md).
        # NPC run sequentially in their parallel/sequential pool, then narrator weaves.
        if npc_tasks:
            npcs_started = time.perf_counter()
            npc_results = await _run_all_npcs()
            _emit_stage_timing(
                timing_stage,
                npcs_started,
                session_id=session_id,
                round_number=round_number,
                npc_count=len(npc_tasks),
            )
            for result in npc_results:
                if result.dialogue:
                    npc_dialogues[result.npc_name] = result.dialogue

        yield build_processing_hint(
            director_result.involved_npcs,
            current_location=game_state.current_location,
        )

        new_state = apply_state_updates(game_state, director_result.state_updates or {})
        triggered_events = check_events(world_data.get("events", []), new_state, game_mode)
        for event in triggered_events:
            new_state = apply_event_effects(new_state, event)

        case_board_history_entries: list[dict] = []
        if director_result.case_board_ops and game_mode == "script":
            try:
                new_case_board, case_board_history_entries = apply_case_board_ops(
                    new_state.to_dict(),
                    game_state.case_board or {},
                    director_result.case_board_ops,
                )
                new_state.case_board = new_case_board
            except CaseBoardError as exc:
                logger.warning("case_board_invalid_ops", error=str(exc))

        if director_result.research_note and session_id:
            from engine.research_log import append_turn_note

            append_turn_note(
                session_id,
                round_number,
                director_result.research_note,
                player_input=action_text,
                script_type=world_data.get("script_type"),
                game_mode=game_mode,
                extras={
                    "applied_case_board_ops": len(case_board_history_entries),
                    "new_clues": [
                        c.get("id") for c in (director_result.state_updates or {}).get("new_clues") or []
                    ],
                },
            )

        # Phase 2.A.4 — climax dwell counter (carried on new_state, persisted via
        # to_dict). Drives the stall floor below + next turn's resolution pressure.
        new_state.rounds_in_climax = (
            (game_state.rounds_in_climax or 0) + 1
            if arc_data.current_act == ACT_CLIMAX
            else 0
        )

        ending = self._resolve_ending(
            world_data, new_state, game_mode, director_result,
            session_id=session_id, round_number=new_state.round_number,
        )

        scene_direction = director_result.scene_direction
        if game_mode == "free" and should_trigger_stage_summary(new_state):
            new_state.last_stage_summary_round = new_state.round_number
            stage_summary_instruction = build_stage_summary_instruction(new_state)
            scene_direction = "\n\n".join(
                part
                for part in [scene_direction, f"【叙述附加要求】\n{stage_summary_instruction}"]
                if part
            )

        # Stamp the compaction counter BEFORE the state snapshot (see
        # _claim_compression); scheduling happens after, gated on db.
        compress_due = self._claim_compression(new_state)

        if emit_state_ready:
            yield {
                "type": "state_ready",
                "new_state": new_state,
                "case_board_history_entries": case_board_history_entries,
            }

        narrative_parts: list[str] = []
        usage_data = None
        narrator_started = time.perf_counter()
        first_token_logged = False
        async for event in self.narrator_agent.stream(
            scene_direction=scene_direction,
            npc_dialogues=npc_dialogues,
            recent_messages=recent_messages,
            authors_note=authors_note,
            prelude_text=prelude_text,
        ):
            if event["type"] == "text_delta":
                if not first_token_logged:
                    _emit_stage_timing(
                        "narrator_first_token",
                        narrator_started,
                        session_id=session_id,
                        round_number=round_number,
                        source="single",
                    )
                    first_token_logged = True
                narrative_parts.append(event["text"])
                yield {"type": "narrative", "text": event["text"]}
            elif event["type"] == "usage":
                usage_data = event
            else:
                yield event
        _emit_stage_timing(
            "narrator",
            narrator_started,
            session_id=session_id,
            round_number=round_number,
            char_count=sum(len(p) for p in narrative_parts),
        )

        full_narrative = "".join(narrative_parts)
        moderation_output_started = time.perf_counter()
        output_check = await check_output_moderated(full_narrative, llm_router=moderation_router)
        _emit_stage_timing(
            "moderation_output",
            moderation_output_started,
            session_id=session_id,
            round_number=round_number,
            outcome="flagged" if not output_check.is_safe else "passed",
        )
        if not output_check.is_safe:
            logger.warning(
                "output_filtered",
                reason=output_check.reason,
                categories=output_check.flagged_categories,
                source=output_check.source,
            )

        yield {
            "type": "state_update",
            "game_state": new_state.to_dict(),
            "quick_actions": director_result.quick_actions or ["继续观察", "和周围的人聊聊", "检查线索"],
            "triggered_events": [event["name"] for event in triggered_events],
        }

        if ending:
            summary_data = {}
            try:
                from engine.ending_system import generate_ending_summary
                summary_data = await generate_ending_summary(
                    llm_router=self.ending_summary_llm_router,
                    ending=ending,
                    game_state=new_state,
                    memory_context=effective_memory_context,
                    script_type=world_data.get("script_type", "mystery"),
                    play_duration_minutes=0,
                )
            except Exception:
                logger.warning("ending_summary_generation_failed", exc_info=True)

            yield {
                "type": "ending",
                "ending_type": ending["ending_type"],
                "title": ending["title"],
                "summary": summary_data,
            }

        # Trigger async compression if needed (counter already stamped above)
        if db and session_id and compress_due:
            self._schedule_compression(session_id, new_state.round_number)

        _emit_stage_timing(
            "turn_total",
            turn_started,
            session_id=session_id,
            round_number=round_number,
            mode=game_mode,
        )

        # Merge prelude usage into the reported usage so cost tracking is
        # accurate when early-stream mode runs the narrator twice per turn.
        merged_usage = _merge_usage(usage_data, prelude_usage) or director_result.usage

        # Bundle the involved NPCs (with personality) so the GameService can
        # fire-and-forget the npc_reflection job without re-querying world data.
        involved_npcs_for_reflection = [
            {
                "name": name,
                "personality": npc_lookup.get(name, {}).get("personality", "") if npc_lookup.get(name) else "",
            }
            for name in director_result.involved_npcs
            if npc_lookup.get(name)
        ]

        yield {
            "type": "done",
            "new_state": new_state,
            "usage": merged_usage,
            "memory_extracts": director_result.memory_extracts,
            "dual_memory_entries": dual_memory_entries,
            "case_board_history_entries": case_board_history_entries,
            "involved_npcs_for_reflection": involved_npcs_for_reflection,
            # Phase 1.B.4 — raw per-NPC dialogue for voice-anchor recall on
            # the next turn. None if no NPCs spoke.
            "npc_dialogues": dict(npc_dialogues) if npc_dialogues else None,
        }

    # ==================================================================
    # Runtime architecture v2 path
    # ==================================================================

    async def _process_action_v2(
        self,
        *,
        action_text: str,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        game_mode: str,
        memory_context: str,
        authors_note: str | None,
        memory_entries: list[dict] | None,
        all_messages: list[dict] | None,
        session_id: str | None,
        round_number: int,
        db,
        known_npcs: list[str] | None,
        emit_state_ready: bool,
    ) -> AsyncIterator[dict]:
        turn_started = time.perf_counter()
        moderation_router = await _resolve_moderation_router(db)

        # ---- moderation input ----
        moderation_input_started = time.perf_counter()
        filter_result = await check_input_moderated(action_text, llm_router=moderation_router)
        _emit_stage_timing(
            "moderation_input",
            moderation_input_started,
            session_id=session_id,
            round_number=round_number,
            outcome="rejected" if not filter_result.is_safe else "passed",
        )
        if not filter_result.is_safe:
            yield {"type": "error", "code": 40001, "message": filter_result.reason}
            return

        # ---- multi-step player input (§11) ----
        effective_action, new_pending, used_pending = consume_pending_segment(
            list(game_state.pending_player_segments or []),
            action_text,
        )
        # If the player didn't trigger a "continue" but we still have content,
        # segment the fresh input. effective_action is the head; rest goes
        # into pending.
        multi_step = False
        if not used_pending and effective_action:
            segments = segment_player_action(effective_action)
            if len(segments) > 1:
                multi_step = True
                effective_action = segments[0]
                new_pending = segments[1:]
        action_for_turn = effective_action or action_text
        game_state.pending_player_segments = list(new_pending)

        # ---- input strength assessment (§12) ----
        assessment = assess_input_strength(action_for_turn)
        weak_hint = assessment.to_hint()

        # ---- world tick (skip intent_advance per §4.4) ----
        world_tick_started = time.perf_counter()
        tick_result: TickResult = self.world_simulator.tick(
            game_state, world_data, skip_intent_advance=True
        )
        game_state = tick_result.updated_state
        # Structural ledger overlay (spec §4): fold committed structural facts
        # onto the seed spine BEFORE building the Director/NPC prompts, so a
        # milestone committed in this tick is visible to the Director this turn.
        # No-op (same object) when the ledger is empty → prefix-cache preserved.
        from engine.structural_ledger import apply_structural_overlay

        world_data = apply_structural_overlay(world_data, game_state.structural_facts)
        _emit_stage_timing(
            "world_tick",
            world_tick_started,
            session_id=session_id,
            round_number=round_number,
            world_event_count=len(tick_result.world_events),
        )

        world_events_context = ""
        if tick_result.world_events:
            event_lines = [f"- [{e.event_type}] {e.description}" for e in tick_result.world_events]
            world_events_context = "【本轮世界事件】\n" + "\n".join(event_lines)

        env_changes_context = ""
        if tick_result.environment_changes:
            env_changes_context = "【环境变化】\n" + "\n".join(tick_result.environment_changes)

        # narrative arc
        arc_data = ArcData.from_dict(game_state.narrative_arc) if game_state.narrative_arc else ArcData()
        arc_summary = self.narrative_arc_tracker.build_summary(arc_data)
        # Phase 2.A.4 — script-mode climax resolution pressure (soft → decision).
        # Built from the pre-turn arc label + dwell count; "" in free mode or
        # before climax, so free play is never nudged toward an ending.
        resolution_directive = build_resolution_directive(
            arc_data.current_act, game_state.rounds_in_climax or 0, game_mode
        )

        structured_memory_context = self.memory_manager.build_memory_context(memory_entries or [])
        world_conflict_context = ""
        if game_state.world_conflicts:
            conflict_lines = [
                f"- {conflict.get('description', '')}"
                for conflict in game_state.world_conflicts
                if conflict.get("description")
            ]
            if conflict_lines:
                world_conflict_context = "## 世界张力\n" + "\n".join(conflict_lines)

        npc_schedule_context = build_npc_schedule_context(
            world_data.get("npcs", []),
            current_time=game_state.current_time,
        )
        world_pulse = build_world_pulse_directive(game_state, game_mode)

        # 拆分 prompt（Director v2 prompt cache 优化，2026-05）：
        # - world_pulse（指令型，准静态）→ system role，保留指令权威 + cache 友好
        # - 其余事实块（每 turn 变）→ user role 消息，不破坏 system prefix cache
        # - weak_hint 文本不再单独塞进上下文：build_director_system_v2 已经通过
        #   player_input_weak 布尔位渲染了独立警告块，weak_hint 是冗余
        # H5 consumption: surface the player's still-unresolved structural claims
        # so the Director keeps the world visibly NOT honoring baseless assertions
        # (and can escalate to a reckoning). Per-turn user context, never the spine.
        from engine.structural_grounding import build_structural_claims_context

        structural_claims_context = build_structural_claims_context(
            game_state.structural_claims, current_round=round_number
        )
        memory_facts_context = "\n".join(
            part
            for part in [
                memory_context,
                structured_memory_context,
                world_conflict_context,
                npc_schedule_context,
                world_events_context,
                env_changes_context,
                arc_summary,
                structural_claims_context,
            ]
            if part
        )
        # 留给 ending_summary 用的全量 bundle（不走 Director 关键路径，无 cache 压力）
        effective_memory_context = "\n".join(
            part for part in [memory_facts_context, world_pulse, weak_hint] if part
        )

        recall_fn = None
        if all_messages:
            def recall_fn(keyword: str, max_results: int = 3) -> list[dict]:
                return self.memory_manager.search_messages(all_messages, keyword, max_results)

        # 思考态过程反馈 ①：提交后立即告诉玩家"已接收行动"。
        # 旧的 build_phase_hint("directing") 模板句 + IntermissionAgent 氛围短句
        # 已移除——改为蹭 director 流式真实里程碑的演进式进度反馈
        # （接收 / 推演 / 角色进场 / 落笔，见 _on_partial_director + 主循环 drain）。
        yield {
            "type": "processing",
            "kind": "progress",
            "stage": "received",
        }

        # ---- B (early NPC dispatch) setup ----
        # Director 输出 tool_use JSON 是 streaming 的，前 5 个 schema 字段（scene_brief / active_npcs /
        # per_npc_focus / scene_role / dramatic_intensity）只占总 JSON 的前 30-50%。
        # 一旦这 5 个 key 都 partial-parse 完成，NPC pre-fetch + LLM 调用就可以开跑了，
        # 不必等 Director 输出 state_updates / case_board_ops 等后续字段。
        npc_lookup = {npc["name"]: npc for npc in world_data.get("npcs", [])}
        known_npc_set = {
            str(n.get("name") or "").strip()
            for n in (world_data.get("npcs") or [])
            if isinstance(n, dict) and n.get("name")
        }
        partial_ready = asyncio.Event()
        partial_data: dict = {}
        partial_fired_at: list[float] = []  # 用 list 当可变容器记 wall time
        # L1: the narrator only needs scene_direction (+ narrative_pressure +
        # scene_role) from the director — measured to land at ~44% of the
        # director's stream, well before its bookkeeping tail (state_updates /
        # memory_extracts / case_board_ops / ...). Capture those fields the
        # moment scene_direction completes and fire ``narrator_ready`` so the
        # narrator can start without waiting for the full director result.
        # ``scene_dir_fired_at`` doubles as the timing probe.
        scene_dir_fired_at: list[float] = []
        narrator_ready = asyncio.Event()
        narrator_inputs: dict = {}

        # 思考态进度事件信号通道：on_partial 在 director task 内同步跑，把里程碑
        # （角色进场 / 落笔）推进 queue，主循环 drain 后 yield。
        progress_queue: asyncio.Queue[dict] = asyncio.Queue()
        npcs_progress_sent: list[bool] = []  # 可变容器当一次性 flag
        # done-core 提取：player_action 是 case_board_ops 之前最后一个 required
        # 字段，它在 partial 中出现即意味着 state_updates / ending_triggered 已闭合
        # （schema 顺序）。此刻抓快照（剔除 case_board_ops），done 不再等 director
        # 的 case_board 尾巴。case_board 在 Phase 4 作为 follow-up 补发。
        core_ready = asyncio.Event()
        core_tool_input: dict = {}

        def _on_partial_director(parsed: dict) -> None:
            # 进度 ③：active NPC 名单先到 → "角色进场"
            if "active_npcs" in parsed and not npcs_progress_sent:
                npcs_progress_sent.append(True)
                names = [
                    str(n).strip()
                    for n in (parsed.get("active_npcs") or [])
                    if str(n).strip() and npc_lookup.get(str(n).strip())
                ]
                if names:
                    progress_queue.put_nowait(
                        {
                            "type": "processing",
                            "kind": "progress",
                            "stage": "npcs_entering",
                            "npcs": names[:4],
                        }
                    )
            if "scene_direction" in parsed and not scene_dir_fired_at:
                scene_dir_fired_at.append(time.perf_counter())
                narrator_inputs["scene_direction"] = parsed["scene_direction"]
                narrator_inputs["narrative_pressure"] = parsed.get("narrative_pressure", "advance")
                narrator_inputs["scene_role"] = dict(parsed.get("scene_role") or {})
                narrator_ready.set()
                # 进度 ④：scene_direction 就绪 → narrator 起笔 → "落笔成文"
                progress_queue.put_nowait(
                    {"type": "processing", "kind": "progress", "stage": "writing"}
                )
            # done-core 快照：player_action 出现即抓（不含 case_board_ops）。
            if "player_action" in parsed and not core_ready.is_set():
                core_tool_input.clear()
                core_tool_input.update(
                    {k: v for k, v in parsed.items() if k != "case_board_ops"}
                )
                core_ready.set()
            if partial_ready.is_set():
                return
            needed = ("active_npcs", "per_npc_focus", "scene_role",
                      "dramatic_intensity", "scene_brief")
            if not all(k in parsed for k in needed):
                return
            partial_data["active_npcs"] = list(parsed["active_npcs"])
            partial_data["per_npc_focus"] = dict(parsed["per_npc_focus"])
            partial_data["scene_role"] = dict(parsed["scene_role"])
            partial_data["dramatic_intensity"] = parsed["dramatic_intensity"]
            partial_data["scene_brief"] = parsed["scene_brief"]
            partial_fired_at.append(time.perf_counter())
            partial_ready.set()

        async def _npc_block_when_ready() -> tuple[list, list[dict]]:
            """等到 partial 信号或 director 兜底信号触发，跑 batch_query + catchup + 预取 + NPC parallel。

            返回 (npc_actions, catchup_memory_entries) 让 orchestrator 主流程接管。
            """
            await partial_ready.wait()
            active_set = list(partial_data["active_npcs"])
            valid_active_names = [name for name in active_set if npc_lookup.get(name)]
            scene_brief_p = partial_data["scene_brief"]
            per_npc_focus_p = partial_data["per_npc_focus"]
            scene_role_p = partial_data["scene_role"]
            dramatic_intensity_p = partial_data["dramatic_intensity"]

            # batch query NPC memories
            batched_memories: dict[str, list[dict]] = {}
            if db and session_id and valid_active_names:
                try:
                    batched_memories = await self.memory_manager.batch_query_npc_memories(
                        db, session_id, valid_active_names, query_text=action_for_turn,
                    )
                except Exception:
                    logger.warning("npc_memory_batch_query_failed", exc_info=True)

            # newly_active catchup
            catchup_threshold = 3
            newly_active: list[str] = []
            for name in valid_active_names:
                last_active = (game_state.last_active_round or {}).get(name)
                if last_active is None:
                    continue
                if (round_number - int(last_active)) > catchup_threshold or (
                    game_state.offstage_event_log.get(name)
                ):
                    newly_active.append(name)

            catchup_memory_entries_local: list[dict] = []
            if newly_active:
                catchup_started = time.perf_counter()

                async def _catchup_one(npc_name: str):
                    npc_info_inner = npc_lookup.get(npc_name) or {}
                    last_active = int(
                        (game_state.last_active_round or {}).get(npc_name, round_number - 1)
                    )
                    last_intent = (game_state.npc_intents or {}).get(npc_name)
                    offstage_log = list(game_state.offstage_event_log.get(npc_name) or [])
                    return await run_catchup(
                        llm_router=self.npc_llm_router,
                        npc_name=npc_name,
                        npc_personality=str(npc_info_inner.get("personality", "")),
                        npc_secret=npc_info_inner.get("secret"),
                        last_active_round=last_active,
                        current_round=round_number,
                        last_intent=last_intent,
                        offstage_log=offstage_log,
                    )

                catchup_results = await asyncio.gather(
                    *(_catchup_one(name) for name in newly_active),
                    return_exceptions=True,
                )
                for raw in catchup_results:
                    if isinstance(raw, Exception) or raw is None:
                        continue
                    entries = apply_catchup_to_state(game_state, raw)
                    if session_id:
                        for e in entries:
                            e["session_id"] = session_id
                            catchup_memory_entries_local.append(e)
                _emit_stage_timing(
                    "npc_catchup",
                    catchup_started,
                    session_id=session_id,
                    round_number=round_number,
                    count=len(newly_active),
                )

            # 每个 active NPC 预取上下文（DB queries），然后并行跑 NPC LLM
            time_slot = _extract_time_slot(game_state.current_time or "")

            # Batch-load the three per-NPC DB lookups in one round trip each
            # (reflections / voice anchors / peer relations) instead of 3×N
            # serial queries inside the loop below. db is a single shared
            # AsyncSession so these can't be gathered — batching is the win.
            # On failure each NPC just falls back to empty (same as before).
            reflections_by_npc: dict = {}
            voice_anchors_by_npc: dict[str, list[str]] = {}
            peer_rel_by_npc: dict[str, list[dict]] = {}
            if db and session_id and active_set:
                try:
                    from services.npc_reflection_service import batch_get_reflections
                    reflections_by_npc = await batch_get_reflections(db, session_id, active_set)
                except Exception:
                    logger.warning("npc_reflection_batch_load_failed", exc_info=True)
                try:
                    voice_anchors_by_npc = (
                        await self.memory_manager.batch_get_npc_recent_utterances(
                            db, session_id, active_set, limit=3
                        )
                    )
                except Exception:
                    logger.warning("npc_voice_anchor_batch_load_failed", exc_info=True)
                if settings.npc_peer_relations_enabled:
                    try:
                        peer_rel_by_npc = (
                            await self.memory_manager.batch_get_npc_peer_relations(
                                db, session_id, active_set
                            )
                        )
                    except Exception:
                        logger.warning("npc_peer_relations_batch_load_failed", exc_info=True)

            npc_kwargs_by_name: dict[str, dict] = {}
            for name in active_set:
                npc_info = npc_lookup.get(name) or {}
                npc_memories = self.memory_manager.filter_npc_memory_entries(
                    memory_entries or [], name
                )
                npc_memories.extend(batched_memories.get(name, []))
                npc_relation = game_state.npc_relations.get(name, {})

                reflection_text: str | None = None
                _reflection_row = reflections_by_npc.get(name)
                if _reflection_row is not None:
                    reflection_text = _reflection_row.summary

                voice_anchor: list[str] = voice_anchors_by_npc.get(name, [])

                peer_rel: list[dict] = peer_rel_by_npc.get(name, [])

                my_location = (
                    npc_info.get("schedule", {}).get(time_slot)
                    or npc_info.get("initial_location")
                    or ""
                )
                peer_npcs: list[dict] = []
                for other in world_data.get("npcs", []):
                    other_name = other.get("name")
                    if not other_name or other_name == name:
                        continue
                    other_loc = (
                        other.get("schedule", {}).get(time_slot)
                        or other.get("initial_location")
                        or ""
                    )
                    if my_location and other_loc == my_location:
                        peer_personality = str(other.get("personality") or "").strip()
                        if len(peer_personality) > 60:
                            peer_personality = peer_personality[:60].rstrip() + "…"
                        peer_npcs.append({"name": other_name, "personality": peer_personality})
                scene_context = {
                    "current_time": game_state.current_time,
                    "my_location": my_location,
                    "player_location": game_state.current_location,
                    "peer_npcs": peer_npcs,
                }
                current_intent = game_state.npc_intents.get(name)
                relevant_lore = self.memory_manager.find_relevant_lore(
                    npc_knowledge=list(npc_info.get("knowledge") or []),
                    lore_pack=world_data.get("lore_pack"),
                    top_k=3,
                )
                involved_shared_events = self.memory_manager.find_npc_shared_events(
                    npc_name=name,
                    shared_events=world_data.get("shared_events"),
                )
                relevant_rumors = self.memory_manager.find_npc_rumors(
                    npc_name=name,
                    events_data=world_data.get("events_data"),
                    triggered_event_ids=getattr(game_state, "triggered_event_ids", set()),
                )

                npc_kwargs_by_name[name] = {
                    "npc_info": npc_info,
                    "npc_memories": npc_memories,
                    "npc_relation": npc_relation,
                    "reflection_text": reflection_text,
                    "voice_anchor": voice_anchor,
                    "peer_rel": peer_rel,
                    "scene_context": scene_context,
                    "current_intent": current_intent,
                    "relevant_lore": relevant_lore,
                    "involved_shared_events": involved_shared_events,
                    "relevant_rumors": relevant_rumors,
                }

            async def _run_npc_v2_inner(name: str):
                ctx = npc_kwargs_by_name.get(name) or {}
                npc_info_inner = ctx.get("npc_info") or {}
                tool_ctx = ToolContext(
                    npc_name=name,
                    game_state=game_state,
                    world_data=world_data,
                    session_id=session_id,
                    db=None,
                    memory_manager=self.memory_manager,
                )
                try:
                    action = await self.npc_agent.run_v2(
                        npc_name=name,
                        npc_personality=str(npc_info_inner.get("personality", "")),
                        voice_style=str(npc_info_inner.get("voice_style", "")),
                        npc_secret=npc_info_inner.get("secret"),
                        player_identity=world_data.get("player_public"),
                        scene_brief=scene_brief_p,
                        per_npc_focus=per_npc_focus_p.get(name, "在场"),
                        scene_role=scene_role_p.get(name, "secondary"),
                        dramatic_intensity=dramatic_intensity_p,
                        recent_messages=[],
                        tool_context=tool_ctx,
                        npc_memories=ctx.get("npc_memories"),
                        npc_relation=ctx.get("npc_relation"),
                        reflection=ctx.get("reflection_text"),
                        voice_anchor=ctx.get("voice_anchor"),
                        world_setting=world_data.get("base_setting", ""),
                        knowledge=list(npc_info_inner.get("knowledge") or []),
                        scene_context=ctx.get("scene_context"),
                        current_intent=ctx.get("current_intent"),
                        peer_relations=ctx.get("peer_rel"),
                        recent_player_actions=list(game_state.player_actions or []),
                        relevant_lore=ctx.get("relevant_lore"),
                        involved_shared_events=ctx.get("involved_shared_events"),
                        relevant_rumors=ctx.get("relevant_rumors"),
                        peer_dialogues_last_turn=None,
                        active_npcs=active_set,
                        known_npcs=known_npc_set,
                        max_tool_calls=settings.npc_action_max_tools_per_call,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "npc_agent_v2.run_failed",
                        npc=name,
                        error=str(exc),
                        session_id=session_id,
                        round_number=round_number,
                    )
                    from engine.npc_action import validate_action
                    action = validate_action(name, None, scene_role=scene_role_p.get(name))
                return action

            npc_semaphore = asyncio.Semaphore(max(1, settings.npc_max_concurrency))

            async def _run_npc_capped(name: str):
                async with npc_semaphore:
                    return await _run_npc_v2_inner(name)

            if not active_set:
                return [], catchup_memory_entries_local

            npcs_started = time.perf_counter()
            raw_actions = await asyncio.gather(
                *(_run_npc_capped(name) for name in active_set),
                return_exceptions=True,
            )
            _emit_stage_timing(
                "npc_v2_parallel",
                npcs_started,
                session_id=session_id,
                round_number=round_number,
                npc_count=len(active_set),
            )

            npc_actions_local: list = []
            from engine.npc_action import validate_action
            for raw, name in zip(raw_actions, active_set):
                if isinstance(raw, Exception) or raw is None:
                    npc_actions_local.append(
                        validate_action(name, None, scene_role=scene_role_p.get(name))
                    )
                else:
                    npc_actions_local.append(raw)
            return npc_actions_local, catchup_memory_entries_local

        # Phase stamp (token_usage attribution): the NPC block's LLM calls
        # (catchup + per-NPC) bucket under phase="npc". asyncio tasks copy the
        # contextvar at creation, so the tag rides along even though the block
        # runs later (after partial_ready fires) in its own context copy.
        with usage_context(phase="npc"):
            npc_block_task = asyncio.create_task(_npc_block_when_ready())

        director_started = time.perf_counter()
        with usage_context(phase="director"):
            director_task = asyncio.create_task(
                self.director_agent.run_v2(
                    game_state=game_state,
                    recent_messages=recent_messages,
                    context_summary=context_summary,
                    world_data=world_data,
                    user_input=action_for_turn,
                    game_mode=game_mode,
                    memory_context=memory_facts_context,
                    world_pulse_directive=world_pulse,
                    authors_note=authors_note,
                    recall_fn=recall_fn,
                    script_type=world_data.get("script_type", ""),
                    on_partial=_on_partial_director,
                    player_input_weak=assessment.is_weak,
                    multi_step_input=multi_step or bool(game_state.pending_player_segments),
                )
            )

        # Record the director's true completion time (it may finish during/after
        # the narrator now, so we can't measure its duration at the emit site).
        director_done_at: list[float] = []
        director_task.add_done_callback(lambda _t: director_done_at.append(time.perf_counter()))

        # 思考态过程反馈 ②：director 已起跑 → "推演『{玩家这次输入}』"。引用玩家真实
        # 动作（截断），不暴露 scene_brief 剧情，撑住头 ~10s 的"在动、针对你这次"。
        _input_summary = (action_for_turn or "").strip()
        if len(_input_summary) > 40:
            _input_summary = _input_summary[:40].rstrip() + "…"
        yield {
            "type": "processing",
            "kind": "progress",
            "stage": "reasoning",
            "input_summary": _input_summary,
        }

        director_result = None
        # L1: wait until the narrator can start (scene_direction ready, fired via
        # narrator_ready) OR the director fully finishes — whichever comes first.
        # We no longer block the player-facing narrative on the director's
        # bookkeeping tail. narrator_ready is set from the partial callback.
        # 同时 drain progress_queue —— on_partial 推来的思考态里程碑（角色进场/落笔）
        # 即时 yield 给前端。
        narrator_ready_waiter = asyncio.create_task(narrator_ready.wait())
        progress_waiter: asyncio.Task = asyncio.create_task(progress_queue.get())
        try:
            while True:
                pending_tasks = {
                    t
                    for t in (director_task, narrator_ready_waiter, progress_waiter)
                    if t and not t.done()
                }
                if not pending_tasks:
                    break
                done, _ = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
                if progress_waiter in done:
                    try:
                        yield progress_waiter.result()
                    except Exception:  # noqa: BLE001
                        pass
                    progress_waiter = asyncio.create_task(progress_queue.get())
                if director_task in done:
                    # raises DirectorParseError if the director failed entirely
                    director_result = director_task.result()
                    break
                if narrator_ready_waiter in done:
                    # scene_direction is ready — weave the narrative now without
                    # waiting for the director's tail. director_result is fetched
                    # after the narrator (Phase 3); the task runs in background.
                    break
        except (DirectorParseError, DirectorUpstreamError) as exc:
            # Director failed before producing a usable scene_direction → nothing
            # shown to the player yet, so surface a clean retry error. Upstream/
            # provider failures (402 balance, exhausted fallback) get a distinct
            # code so they aren't mislabeled as a parse failure.
            if not npc_block_task.done():
                npc_block_task.cancel()
            if not narrator_ready_waiter.done():
                narrator_ready_waiter.cancel()
            if not progress_waiter.done():
                progress_waiter.cancel()
            upstream = isinstance(exc, DirectorUpstreamError)
            logger.warning(
                "director_v2.unrecoverable",
                session_id=session_id,
                round_number=round_number,
                error=str(exc),
                upstream=upstream,
            )
            yield {
                "type": "error",
                "code": "provider_unavailable" if upstream else "llm_parse",
                "message": (
                    "AI 服务暂时不可用，请稍后再试"
                    if upstream
                    else "导演无法解析本轮指令，请重试该回合"
                ),
            }
            return
        finally:
            if not narrator_ready_waiter.done():
                narrator_ready_waiter.cancel()
            if not progress_waiter.done():
                progress_waiter.cancel()

        # Flush any milestone that landed exactly as we broke out — "writing" is
        # pushed in the same on_partial call that fires narrator_ready, so it may
        # still be queued when narrator_ready_waiter wins the race.
        while not progress_queue.empty():
            try:
                yield progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        # ============================================================
        # Phase 2 (L1) — NPC actions + narrator weave = the player-facing
        # critical path. Runs as soon as scene_direction is ready, WITHOUT
        # waiting for the director's bookkeeping tail (state_updates / clues /
        # case_board / memory_extracts). The tail finishes in the background and
        # is applied in Phase 3 below.
        # ============================================================

        # Fallback: director streamed without firing the partial scene_direction
        # signal (e.g. a provider that doesn't emit incremental JSON). Populate
        # narrator inputs (+ NPC partial data) from the full result instead.
        if not narrator_ready.is_set():
            if director_result is None:
                director_result = await director_task
            narrator_inputs["scene_direction"] = director_result.scene_direction
            narrator_inputs["narrative_pressure"] = director_result.narrative_pressure
            narrator_inputs["scene_role"] = dict(director_result.scene_role)
        if not partial_ready.is_set() and director_result is not None:
            partial_data["active_npcs"] = list(director_result.active_npcs)
            partial_data["per_npc_focus"] = dict(director_result.per_npc_focus)
            partial_data["scene_role"] = dict(director_result.scene_role)
            partial_data["dramatic_intensity"] = director_result.dramatic_intensity
            partial_data["scene_brief"] = director_result.scene_brief
            partial_ready.set()

        prelude_text: str | None = None  # prelude removed (BUGS #27 H3)
        prelude_usage: dict | None = None

        # Await the NPC block (started when the 5-field partial fired; usually
        # already done since NPCs run on the fast model and overlapped the
        # director's tail).
        npc_block_started_wait = time.perf_counter()
        try:
            npc_actions, catchup_memory_entries = await npc_block_task
        except Exception:  # noqa: BLE001
            logger.warning(
                "npc_block_task_failed",
                exc_info=True,
                session_id=session_id,
                round_number=round_number,
            )
            npc_actions = []
            catchup_memory_entries = []
        _emit_stage_timing(
            "npc_block_wait",
            npc_block_started_wait,
            session_id=session_id,
            round_number=round_number,
            note="time spent waiting on background NPC task before narrator (L1)",
        )

        # Sort actions for the narrator: visible first, then internal, then omitted.
        visible_actions = [a for a in npc_actions if a.is_visible()]
        internal_actions = [a for a in npc_actions if not a.is_visible() and not a.omitted]
        omitted_actions = [a for a in npc_actions if a.omitted]
        sorted_actions = (
            sorted(visible_actions, key=lambda a: a.priority, reverse=True)
            + sorted(internal_actions, key=lambda a: a.priority, reverse=True)
            + omitted_actions
        )

        # Narrator weave — streams now, off the director's bookkeeping tail.
        narrative_parts: list[str] = []
        usage_data = None
        narrator_started = time.perf_counter()
        with usage_context(phase="narrator"):
            async for event in self.narrator_agent.stream_v2(
                scene_direction=narrator_inputs.get("scene_direction", ""),
                npc_actions=sorted_actions,
                scene_role_map=narrator_inputs.get("scene_role") or {},
                recent_messages=filter_recent_messages_for_narrator(recent_messages),
                authors_note=authors_note,
                prelude_text=prelude_text,
                narrative_pressure=narrator_inputs.get("narrative_pressure", "advance"),
            ):
                if event["type"] == "text_delta":
                    narrative_parts.append(event["text"])
                    yield {"type": "narrative", "text": event["text"]}
                elif event["type"] == "usage":
                    usage_data = event
                else:
                    yield event
        _emit_stage_timing(
            "narrator_v2",
            narrator_started,
            session_id=session_id,
            round_number=round_number,
            char_count=sum(len(p) for p in narrative_parts),
        )
        full_narrative = "".join(narrative_parts)

        # ============================================================
        # Phase 3 — resolve a CORE director result and run world bookkeeping off
        # the player's critical path. "Core" = everything the director produced
        # EXCEPT case_board_ops (its longest tail). We commit state + emit `done`
        # (unlocking the player) without waiting for case_board; case_board is
        # applied as a Phase-4 follow-up once the full director_task finishes.
        #   • director already fully resolved → use it directly (no deferral)
        #   • core snapshot ready (player_action partial-parsed) → build from it
        #   • neither → fall back to awaiting the full director_task (§8)
        # ============================================================
        case_board_deferred = False
        if director_result is None and core_ready.is_set():
            known_event_ids_core = {
                str(ev.get("id") or "").strip()
                for ev in (world_data.get("events_data") or [])
                if isinstance(ev, dict) and ev.get("id")
            }
            director_result = self.director_agent._build_result_v2(
                dict(core_tool_input),
                None,
                known_npcs=known_npc_set,
                known_event_ids=known_event_ids_core,
                fired_event_ids=set(game_state.triggered_event_ids or set()),
            )
            # case_board_ops was stripped from the snapshot → empty here, so the
            # case_board block below skips naturally. Defer it to Phase 4 (script
            # mode only; free mode produces no case_board).
            case_board_deferred = game_mode == "script"
        elif director_result is None:
            # Fallback (§8): no early core signal — await the full director result
            # before emitting done. Degrades the done-gap back to the old timing
            # but stays correct.
            try:
                director_result = await director_task
            except (DirectorParseError, DirectorUpstreamError) as exc:
                # Rare: scene_direction partial-parsed (narrative already shown)
                # but the final director call failed (parse OR upstream). Degrade
                # gracefully — close the turn with no state changes rather than
                # error after showing text.
                logger.warning(
                    "director_v2.unrecoverable_post_narrative",
                    session_id=session_id,
                    round_number=round_number,
                    error=str(exc),
                    upstream=isinstance(exc, DirectorUpstreamError),
                )
                director_result = DirectorResult(
                    scene_direction=narrator_inputs.get("scene_direction", ""),
                    active_npcs=list(partial_data.get("active_npcs") or []),
                )

        # two-pass: 即使 director 完全 resolved（慢路径），也把 case_board 推迟到
        # Phase-4 独立生成 —— 主 schema 已不含 ops（Task 6），director_result.
        # case_board_ops 恒空，上方 inline apply 自然跳过。
        if settings.director_case_board_two_pass and game_mode == "script":
            case_board_deferred = True

        # Structural evolution (spec 2026-06-03 redesign). Free mode only: if the
        # Grounded structural evolution (spec 2026-06-03 grounded redesign).
        # The Director parsed the player's structural assertion into a claim; we
        # record it in the claim ledger (drives drama, never the spine) and
        # PROMOTE it to a world fact only if its premise is grounded in STRUCTURED
        # state (§3.4: the entity whose authority/consent the change requires is
        # present and acting via its own agent) — never the player's words, never
        # bystander compliance (INV-1). Ungrounded claims stay in-play / exposed.
        if (
            game_mode == "free"
            and director_result.structural_in_play
            and director_result.structural_claim
            and settings.structural_grounded_enabled
        ):
            from engine.structural_grounding import (
                check_entity_assent,
                is_grounded,
                record_or_refresh_claim,
            )
            from engine.structural_ledger import commit_structural_fact

            _claim = director_result.structural_claim
            _entry = record_or_refresh_claim(game_state, _claim)
            _turn_actions = [
                {"npc_name": a.npc_name, "dialogue": a.dialogue, "physical": a.physical}
                for a in sorted_actions
            ]
            _verdict = is_grounded(_claim, game_state.structural_facts, _turn_actions)
            _grounded = _verdict["grounded"]
            if _verdict.get("needs_assent_check"):
                # Required entity IS present — narrow LLM read of ONLY its own
                # action decides assent (INV-1: never player input / narration).
                _ea = _verdict.get("entity_action") or {}
                _action_text = "；".join(t for t in (_ea.get("dialogue"), _ea.get("physical")) if t)
                _grounded = await check_entity_assent(
                    self.npc_llm_router,
                    entity_name=str((_claim.get("premise") or {}).get("required_entity") or ""),
                    entity_action_text=_action_text,
                    claim_text=str(_claim.get("claim_text") or ""),
                )
            _committed = False
            if _grounded:
                _committed = commit_structural_fact(game_state, {
                    "fact_key": _claim.get("claim_key"),
                    "fact_text": _claim.get("claim_text"),
                    "kind": _claim.get("kind"),
                    "target_ref": _claim.get("target_ref"),
                    "provenance": "grounded",
                })
                _entry["status"] = "grounded"
            elif _verdict.get("needs_assent_check"):
                # The invoked authority was present and did NOT back it → exposed
                # (collision with a verifier). Next turn's brief surfaces the
                # reckoning; the claim never reaches the spine.
                _entry["status"] = "exposed"
            logger.info(
                "structural.grounding",
                session_id=session_id,
                round_number=round_number,
                claim_key=_entry.get("claim_key"),
                grounded=_grounded,
                basis=_verdict.get("basis"),
                reason=_verdict.get("reason"),
                status=_entry.get("status"),
                committed=_committed,
            )

        director_elapsed_ms = round(
            ((director_done_at[0] if director_done_at else time.perf_counter()) - director_started)
            * 1000
        )
        partial_elapsed_ms: int | None = None
        if partial_fired_at:
            partial_elapsed_ms = round((partial_fired_at[0] - director_started) * 1000)
        scene_direction_ms: int | None = None
        if scene_dir_fired_at:
            scene_direction_ms = round((scene_dir_fired_at[0] - director_started) * 1000)
        _emit_stage_timing(
            "director_v2",
            director_started,
            session_id=session_id,
            round_number=round_number,
            active_npcs=len(director_result.active_npcs),
            intensity=director_result.dramatic_intensity,
            partial_signal_ms=partial_elapsed_ms,  # 早绑 NPC 的提前量
            # L1 probe: scene_direction landing vs full director. f = this /
            # director's duration_ms. Small f ⇒ early narrator kickoff worth it.
            scene_direction_ms=scene_direction_ms,
            # core_path: done committed from the partial snapshot, case_board
            # deferred to Phase 4. When True, duration_ms here is time-to-core
            # (not director-total); the true tail is logged as director_v2_tail.
            core_path=case_board_deferred,
        )

        # Weak-input clamp safety net — even if director ignored the hint,
        # cap intensity / active_npcs at the orchestrator layer (§12.3).
        # Note: if partial_ready fired early, NPCs already started with un-clamped
        # values. Clamp 仍然作用于 director_result（narrator/state 看到的版本）。
        if assessment.is_weak:
            if director_result.dramatic_intensity in {"high", "climax"}:
                director_result.dramatic_intensity = "medium"
            if len(director_result.active_npcs) > 1:
                kept = director_result.active_npcs[:1]
                director_result.active_npcs = kept
                director_result.per_npc_focus = {
                    k: v for k, v in director_result.per_npc_focus.items() if k in set(kept)
                }
                director_result.scene_role = {
                    k: v for k, v in director_result.scene_role.items() if k in set(kept)
                }
            director_result.involved_npcs = list(director_result.active_npcs)

        # Fallback: 若 partial 信号没在 streaming 中触发（如 JSON mode 没有 input_json_delta
        # 事件，或字段顺序不利），现在用完整 director_result 兜底点燃 NPC block。
        if not partial_ready.is_set():
            partial_data["active_npcs"] = list(director_result.active_npcs)
            partial_data["per_npc_focus"] = dict(director_result.per_npc_focus)
            partial_data["scene_role"] = dict(director_result.scene_role)
            partial_data["dramatic_intensity"] = director_result.dramatic_intensity
            partial_data["scene_brief"] = director_result.scene_brief
            partial_ready.set()
            logger.info(
                "director.partial_fallback",
                session_id=session_id,
                round_number=round_number,
                director_elapsed_ms=director_elapsed_ms,
            )

        # npc_lookup 已在 director_task 之前构造好

        # Record typed player_action.
        if director_result.player_action is not None:
            entry = {
                "round": round_number,
                **director_result.player_action,
            }
            actions_history = list(game_state.player_actions or [])
            actions_history.append(entry)
            if len(actions_history) > PLAYER_ACTIONS_HISTORY_LIMIT:
                actions_history = actions_history[-PLAYER_ACTIONS_HISTORY_LIMIT:]
            game_state.player_actions = actions_history

        # narrative arc update
        arc_data = self.narrative_arc_tracker.update(
            arc_data,
            action_for_turn,
            director_result.active_npcs,
            game_state.current_location,
            round_number=round_number,
            discovered_clues_count=len(game_state.discovered_clues or []),
            dramatic_intensity=director_result.dramatic_intensity,
        )
        game_state.narrative_arc = arc_data.to_dict()

        # info_propagation + dual perspective memory entries (same as v1).
        dual_memory_entries: list[dict] = []
        if session_id:
            dual_memory_entries.extend(
                self.memory_manager.write_info_propagation_memories(
                    session_id=session_id,
                    round_number=round_number,
                    events=tick_result.world_events,
                )
            )
            for event in tick_result.world_events:
                if event.event_type == "npc_action" and len(event.involved_npcs) >= 2:
                    npc_a, npc_b = event.involved_npcs[0], event.involved_npcs[1]
                    dual_memory_entries.extend(
                        self.memory_manager.write_dual_perspective_memories(
                            session_id=session_id,
                            round_number=round_number,
                            npc_a=npc_a,
                            npc_b=npc_b,
                            event_description=event.description,
                            perspective_a=f"{npc_a}视角：{event.description}",
                            perspective_b=f"{npc_b}视角：{event.description}",
                        )
                    )

        # NPC actions + narrator already ran in Phase 2 above. Phase 3 only needs
        # active_set (for last_active_round / offstage) and folds the catchup
        # memories (from the Phase-2 NPC block) into the dual-memory write batch.
        active_set = list(director_result.active_npcs)
        dual_memory_entries.extend(catchup_memory_entries)

        # ---- Apply intent_update / mood_shift from each NPCAction ----
        for action in npc_actions:
            if action.intent_update:
                intent = game_state.npc_intents.get(action.npc_name)
                if isinstance(intent, dict):
                    progress = action.intent_update.progress
                    if progress == "advance":
                        stages = intent.get("plan_stages") or []
                        max_stage = max(0, len(stages) - 1)
                        intent["plan_stage"] = min(
                            max_stage,
                            int(intent.get("plan_stage") or 0) + action.intent_update.stage_index_delta,
                        )
                    elif progress == "stuck":
                        if action.intent_update.blocked_by:
                            intent["blocked_by"] = action.intent_update.blocked_by
                    elif progress == "pivot" and action.intent_update.new_goal:
                        intent["current_goal"] = action.intent_update.new_goal
                        intent["plan_stage"] = 0
                        intent["blocked_by"] = None
                    elif progress == "complete":
                        intent["plan_stage"] = max(0, len(intent.get("plan_stages") or []) - 1)
                    game_state.npc_intents[action.npc_name] = intent
            if action.mood_shift:
                relation = game_state.npc_relations.setdefault(
                    action.npc_name,
                    {"trust": 3, "mood": "正常", "last_interaction": ""},
                )
                relation["mood"] = action.mood_shift.to_mood
            # Persist hidden_note as a private memory entry so the NPC can
            # see their own internal note on subsequent turns.
            if action.hidden_note and session_id:
                dual_memory_entries.append(
                    {
                        "session_id": session_id,
                        "memory_type": "self_note",
                        "content": action.hidden_note,
                        "round_number": round_number,
                        "importance": 6,
                        "related_npc": action.npc_name,
                    }
                )

        # ---- State updates + events + case_board ----
        new_state = apply_state_updates(game_state, director_result.state_updates or {})

        # Update last_active_round for all NPCs that participated this turn.
        for name in active_set:
            new_state.last_active_round[name] = new_state.round_number

        # Deterministic events (v1 legacy events list).
        triggered_events = check_events(world_data.get("events", []), new_state, game_mode)
        for event in triggered_events:
            new_state = apply_event_effects(new_state, event)

        # Director-driven event_fire_intent (script mode, events_data).
        fired_intent_events: list[dict] = []
        if director_result.event_fire_intent and game_mode == "script":
            from engine.condition_dsl import ConditionDSLParseError
            from engine.condition_dsl import evaluate as dsl_evaluate
            from engine.condition_dsl import parse as dsl_parse

            events_data = world_data.get("events_data") or []
            events_by_id = {
                str(ev.get("id") or ""): ev for ev in events_data if isinstance(ev, dict)
            }
            for event_id in director_result.event_fire_intent:
                event = events_by_id.get(event_id)
                if not event:
                    continue
                if event_id in new_state.triggered_event_ids:
                    continue
                dsl_source = ""
                trigger = event.get("trigger") or {}
                if isinstance(trigger, dict):
                    dsl_source = str(trigger.get("condition_dsl") or "")
                if not dsl_source.strip():
                    # No condition → director intent alone is allowed to fire.
                    condition_ok = True
                else:
                    try:
                        condition_ok = dsl_evaluate(dsl_parse(dsl_source), new_state)
                    except (ConditionDSLParseError, Exception):
                        condition_ok = False
                if not condition_ok:
                    logger.info(
                        "director_v2.event_fire_rejected",
                        event_id=event_id,
                        reason="condition_unmet",
                    )
                    continue
                # Apply effects (same as world_simulator._process_events_data
                # but synchronous and tied to director intent).
                effects = event.get("effects") or {}
                for k, v in (effects.get("world_state_changes") or {}).items():
                    new_state.world_state[k] = v
                for clue_text in effects.get("spawn_clues") or []:
                    append_discovered_clue(
                        new_state.discovered_clues,
                        clue_text,
                        found_at=new_state.current_time,
                        source="director_intent_event_spawn_clues",
                    )
                for npc_name_eff, new_mood in (effects.get("npc_mood_changes") or {}).items():
                    rel = new_state.npc_relations.setdefault(
                        npc_name_eff,
                        {"trust": 3, "mood": "正常", "last_interaction": ""},
                    )
                    rel["mood"] = new_mood
                new_state.triggered_event_ids.add(event_id)
                fired_intent_events.append(event)

        case_board_history_entries: list[dict] = []
        if director_result.case_board_ops and game_mode == "script":
            try:
                new_case_board, case_board_history_entries = apply_case_board_ops(
                    new_state.to_dict(),
                    game_state.case_board or {},
                    director_result.case_board_ops,
                )
                new_state.case_board = new_case_board
            except CaseBoardError as exc:
                logger.warning("case_board_invalid_ops", error=str(exc))

        if director_result.research_note and session_id:
            from engine.research_log import append_turn_note

            append_turn_note(
                session_id,
                round_number,
                director_result.research_note,
                player_input=action_text,
                script_type=world_data.get("script_type"),
                game_mode=game_mode,
                extras={
                    "applied_case_board_ops": len(case_board_history_entries),
                    "new_clues": [
                        # Director 偶尔会返回 list[str] 而非 list[dict]，两种都接住
                        (c.get("id") if isinstance(c, dict) else c)
                        for c in (director_result.state_updates or {}).get("new_clues") or []
                    ],
                    "v2": True,
                },
            )

        # Phase 2.A.4 — climax dwell counter (carried on new_state, persisted via
        # to_dict). Drives the stall floor below + next turn's resolution pressure.
        new_state.rounds_in_climax = (
            (game_state.rounds_in_climax or 0) + 1
            if arc_data.current_act == ACT_CLIMAX
            else 0
        )

        # Ending check — authored hard → Director AI → architectural stall floor.
        ending = self._resolve_ending(
            world_data, new_state, game_mode, director_result,
            session_id=session_id, round_number=new_state.round_number,
        )

        # ---- offstage scheduler — record triggers from this turn ----
        all_fired = list(triggered_events) + fired_intent_events
        offstage_triggers = collect_triggers(
            offstage_npcs=director_result.offstage_active,
            npc_actions=npc_actions,
            player_action=director_result.player_action,
            fired_events=all_fired,
            round_number=round_number,
        )
        append_log_entries(new_state, offstage_triggers)

        # Stamp the compaction counter BEFORE the state snapshot so the
        # early-stream commit (state_ready) persists it; scheduling happens
        # after, gated on db.
        compress_due = self._claim_compression(new_state)

        if emit_state_ready:
            yield {
                "type": "state_ready",
                "new_state": new_state,
                "case_board_history_entries": case_board_history_entries,
            }

        # Narrator already wove + streamed in Phase 2 above; full_narrative,
        # visible_actions, sorted_actions and usage_data are set there.
        moderation_output_started = time.perf_counter()
        output_check = await check_output_moderated(full_narrative, llm_router=moderation_router)
        _emit_stage_timing(
            "moderation_output",
            moderation_output_started,
            session_id=session_id,
            round_number=round_number,
            outcome="flagged" if not output_check.is_safe else "passed",
        )
        if not output_check.is_safe:
            logger.warning(
                "output_filtered",
                reason=output_check.reason,
                categories=output_check.flagged_categories,
                source=output_check.source,
            )

        # BUGS #22: SSE used to read only legacy + intent-fired events,
        # missing world_simulator auto-fires (Path B). Read directly from
        # state.triggered_event_ids which all three paths converge into.
        # Display names: legacy events expose .name; v2 events_data only have
        # .id but no .name, so we also keep the bare id as a fallback.
        events_by_id_for_display = {
            str(ev.get("id") or ""): ev
            for ev in (world_data.get("events_data") or [])
            if isinstance(ev, dict) and ev.get("id")
        }
        legacy_by_name = {str(ev.get("name") or ""): ev for ev in (triggered_events or [])}
        display_names: list[str] = []
        for eid in list(new_state.triggered_event_ids or []):
            v2_ev = events_by_id_for_display.get(eid)
            if v2_ev:
                # events_data has no name field by schema; fall back to summary[:20] or id
                summary = str(v2_ev.get("summary") or "")[:30]
                display_names.append(summary or eid)
            else:
                display_names.append(eid)
        for legacy_name in legacy_by_name:
            if legacy_name and legacy_name not in display_names:
                display_names.append(legacy_name)

        yield {
            "type": "state_update",
            "game_state": new_state.to_dict(),
            "quick_actions": director_result.quick_actions or ["继续观察", "和周围的人聊聊", "检查线索"],
            "triggered_events": display_names,
        }

        if ending:
            summary_data = {}
            try:
                from engine.ending_system import generate_ending_summary
                summary_data = await generate_ending_summary(
                    llm_router=self.ending_summary_llm_router,
                    ending=ending,
                    game_state=new_state,
                    memory_context=effective_memory_context,
                    script_type=world_data.get("script_type", "mystery"),
                    play_duration_minutes=0,
                )
            except Exception:
                logger.warning("ending_summary_generation_failed", exc_info=True)
            yield {
                "type": "ending",
                "ending_type": ending["ending_type"],
                "title": ending["title"],
                "summary": summary_data,
            }

        if db and session_id and compress_due:
            self._schedule_compression(session_id, new_state.round_number)

        _emit_stage_timing(
            "turn_total",
            turn_started,
            session_id=session_id,
            round_number=round_number,
            mode=game_mode,
            v2=True,
        )

        # ---- Schedule offstage periodic ticks in background (fire-and-forget) ----
        tick_candidates = [
            name
            for name in director_result.offstage_active
            if should_run_periodic_tick(name, new_state, tick_rounds=settings.npc_offstage_tick_rounds)
        ]
        if tick_candidates and db and session_id:
            asyncio.create_task(
                self._run_offstage_ticks(
                    npc_names=tick_candidates,
                    world_data=world_data,
                    session_id=session_id,
                    state_snapshot=new_state.to_dict(),
                )
            )

        # Build dialogues dict from visible NPC actions for voice anchor.
        npc_dialogues_for_voice: dict[str, str] = {}
        for action in visible_actions:
            text = action.dialogue or action.physical
            if text:
                npc_dialogues_for_voice[action.npc_name] = text

        merged_usage = _merge_usage(usage_data, prelude_usage) or director_result.usage
        involved_npcs_for_reflection = [
            {
                "name": name,
                "personality": npc_lookup.get(name, {}).get("personality", ""),
            }
            for name in director_result.active_npcs
            if npc_lookup.get(name)
        ]

        done_event: dict = {
            "type": "done",
            "new_state": new_state,
            "usage": merged_usage,
            "memory_extracts": director_result.memory_extracts,
            "dual_memory_entries": dual_memory_entries,
            "case_board_history_entries": case_board_history_entries,
            "involved_npcs_for_reflection": involved_npcs_for_reflection,
            "npc_dialogues": dict(npc_dialogues_for_voice) if npc_dialogues_for_voice else None,
        }
        if not case_board_deferred:
            # Director fully resolved here (case_board already applied above), so
            # the off-critical-path flash memory-extraction bundle has the full
            # case_board reasoning. When deferred, this rides the Phase-4 event.
            done_event["mem_extract_input"] = {
                "player_action": (director_result.player_action or {}).get("summary", ""),
                "scene_brief": director_result.scene_brief,
                "per_npc_focus": director_result.per_npc_focus,
                "new_clues": (director_result.state_updates or {}).get("new_clues") or [],
                "case_board_ops": director_result.case_board_ops,
                "active_npcs": list(director_result.active_npcs),
            }
        yield done_event

        # ============================================================
        # Phase 4 (follow-up) — the director's case_board tail. Runs AFTER `done`
        # (the player is already unlocked). director_task finishes its
        # case_board_ops in the background; we apply them and emit a
        # `case_board_update` so the case board refreshes a beat after the prose.
        # The memory-extraction bundle (which wants the full case_board reasoning)
        # rides along here. gap 消失：done 在正文流完即触发，case_board 晚一拍。
        # ============================================================
        if case_board_deferred:
            if settings.director_case_board_two_pass and game_mode == "script":
                # two-pass: case_board_ops 由独立轻量调用生成（不再 await 同一个
                # director_task）。截断只影响案件板（非致命 tail），不连累叙事/结局。
                ops = await self.director_agent.generate_case_board_ops(
                    scene_brief=director_result.scene_brief,
                    new_clues=(director_result.state_updates or {}).get("new_clues") or [],
                    current_board=game_state.case_board or {},
                    script_type=world_data.get("script_type", ""),
                    discovered_clue_ids=[
                        c.get("id")
                        for c in (getattr(new_state, "discovered_clues", None) or [])
                        if isinstance(c, dict) and c.get("id")
                    ],
                )
                cb_history = []
                if ops:
                    try:
                        new_case_board, cb_history = apply_case_board_ops(
                            new_state.to_dict(),
                            game_state.case_board or {},
                            ops,
                        )
                        new_state.case_board = new_case_board
                    except CaseBoardError as exc:
                        logger.warning("case_board_invalid_ops", error=str(exc))
                _emit_stage_timing(
                    "case_board_two_pass",
                    director_started,
                    session_id=session_id,
                    round_number=round_number,
                    op_count=len(ops),
                )
                yield {
                    "type": "case_board_update",
                    "new_state": new_state,
                    "game_state": new_state.to_dict(),
                    "case_board_history_entries": cb_history,
                    "mem_extract_input": {
                        "player_action": (director_result.player_action or {}).get("summary", ""),
                        "scene_brief": director_result.scene_brief,
                        "per_npc_focus": director_result.per_npc_focus,
                        "new_clues": (director_result.state_updates or {}).get("new_clues") or [],
                        "case_board_ops": ops,
                        "active_npcs": list(director_result.active_npcs),
                    },
                }
            else:
                try:
                    full_result = await director_task
                except DirectorParseError:
                    full_result = None
                except Exception:  # noqa: BLE001
                    logger.warning("director_v2.tail_await_failed", exc_info=True)
                    full_result = None

                if full_result is not None:
                    if director_done_at:
                        _emit_stage_timing(
                            "director_v2_tail",
                            director_started,
                            session_id=session_id,
                            round_number=round_number,
                            note="true director completion (case_board tail) after early done",
                        )
                    cb_history: list[dict] = []
                    if full_result.case_board_ops:
                        try:
                            new_case_board, cb_history = apply_case_board_ops(
                                new_state.to_dict(),
                                game_state.case_board or {},
                                full_result.case_board_ops,
                            )
                            new_state.case_board = new_case_board
                        except CaseBoardError as exc:
                            logger.warning("case_board_invalid_ops", error=str(exc))
                    yield {
                        "type": "case_board_update",
                        "new_state": new_state,
                        "game_state": new_state.to_dict(),
                        "case_board_history_entries": cb_history,
                        "mem_extract_input": {
                            "player_action": (full_result.player_action or {}).get("summary", ""),
                            "scene_brief": full_result.scene_brief,
                            "per_npc_focus": full_result.per_npc_focus,
                            "new_clues": (full_result.state_updates or {}).get("new_clues") or [],
                            "case_board_ops": full_result.case_board_ops,
                            "active_npcs": list(full_result.active_npcs),
                        },
                    }

    async def _extract_memories_llm(
        self, bundle: dict, known_npcs: list[str]
    ) -> tuple[list[dict], dict | None]:
        """Post-turn memory extraction on the flash NPC router.

        Reads the Director's *already-produced output* (``bundle``: scene_brief /
        case_board reasoning / clues / player action) — not the full 22k game
        context — so it's a lean, cheap call that runs off the critical path,
        replacing the Director's in-call ``memory_extracts``. Returns
        (extracts, usage_event).
        """
        import json as _json

        system = (
            "你从一段游戏回合的材料里抽取值得长期记住的事实，只输出 JSON 对象："
            '{"memory_extracts":[{"type":...,"content":...,"importance":...}]}。'
            "type 取值 player_claim/npc_attitude/discovery/causal_chain/environment_change；"
            "importance 取值 high/medium/low。只抽真正重要的 3-5 条："
            "玩家的声称或谎言、NPC 态度转变、关键发现、推理链（线索如何关联）、环境剧变。"
            "content 一句话，具体客观。"
        )
        user = "本回合材料（来自导演输出）：\n" + _json.dumps(bundle, ensure_ascii=False)
        text_parts: list[str] = []
        usage: dict | None = None
        try:
            async for event in self.npc_llm_router.stream_json(
                messages=[{"role": "user", "content": user}], system=system, max_tokens=1024,
            ):
                if event.get("type") == "text_delta":
                    text_parts.append(event.get("text", ""))
                elif event.get("type") == "usage":
                    usage = event
        except Exception as exc:  # noqa: BLE001
            logger.warning("async_mem_extract_failed", error=str(exc))
            return [], None
        raw = "".join(text_parts).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw[:-3] if raw.rstrip().endswith("```") else raw
        try:
            start, end = raw.find("{"), raw.rfind("}")
            parsed = _json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
            extracts = parsed.get("memory_extracts", []) if isinstance(parsed, dict) else []
        except Exception:  # noqa: BLE001
            extracts = []
        return extracts, usage

    async def _run_offstage_ticks(
        self,
        *,
        npc_names: list[str],
        world_data: dict,
        session_id: str,
        state_snapshot: dict,
    ) -> None:
        """Fire-and-forget periodic offstage tick.

        Runs after the main turn completes. Uses a fresh DB session because
        the caller's session is gone by the time this lands. Failures are
        silently logged — the offstage log is best-effort.
        """
        try:
            from database import async_session
        except Exception:  # noqa: BLE001
            return
        npc_lookup = {n.get("name"): n for n in world_data.get("npcs") or []}
        state = GameState.from_dict(state_snapshot)
        round_number = state.round_number

        async def _tick(name: str) -> None:
            npc_info = npc_lookup.get(name) or {}
            last_active = int((state.last_active_round or {}).get(name, round_number - 1))
            try:
                result = await run_catchup(
                    llm_router=self.npc_llm_router,
                    npc_name=name,
                    npc_personality=str(npc_info.get("personality", "")),
                    npc_secret=npc_info.get("secret"),
                    last_active_round=last_active,
                    current_round=round_number,
                    last_intent=(state.npc_intents or {}).get(name),
                    offstage_log=list(state.offstage_event_log.get(name) or []),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("offstage_tick.failed", npc=name, error=str(exc))
                return
            if not result.ok:
                return
            # Persist intent / mood / clear log in a fresh DB transaction.
            try:
                async with async_session() as db:
                    from models.game import GameSession

                    sess = await db.get(GameSession, session_id)
                    if not sess or not isinstance(sess.game_state, dict):
                        return
                    live_state = GameState.from_dict(sess.game_state)
                    apply_catchup_to_state(live_state, result)
                    sess.game_state = live_state.to_dict()
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("offstage_tick.persist_failed", npc=name, error=str(exc))

        await asyncio.gather(*(_tick(n) for n in npc_names), return_exceptions=True)
