import asyncio
from typing import AsyncIterator

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from engine.cost_guardrail import (
    CostGuardrailStatus,
    classify_session_cost,
)
from engine.orchestrator import Orchestrator
from engine.intent_system import init_npc_intents
from engine.stance_inference import infer_initial_stances
from engine.state_manager import GameState, StaleVersionError, save_session_state
from llm.usage_context import usage_context
from middleware.error_handler import AppError
from models.case_board_history import CaseBoardHistory
from models.game import GameSession, Message, TokenUsage
from models.memory import MemoryEntry
from models.npc_relation import NPCRelation
from models.script import Script
from models.world import Ending, Event, World, WorldCharacter
from schemas.game import GameSessionDetailResponse, SessionMessageDTO
from utils import utcnow

logger = structlog.get_logger()


class _AttachedNPC:
    """Runtime stand-in for a script-owned 反哺 character (no world_characters
    row). The engine handles NPCs entirely by name (game_state.npc_relations /
    npc_locations, stance inference, NPCRelation rows all key on name), so a
    plain duck-typed object carrying the attributes the runtime reads is enough.
    Only the *player* character must be a real WorldCharacter; attached
    characters are NPC-only.
    """

    __slots__ = (
        "id", "name", "personality", "voice_style", "secret", "knowledge",
        "schedule", "initial_location", "description", "narrative_weight",
        "initial_peer_relations", "playable", "mode", "gender", "abilities",
        "starting_inventory",
    )

    def __init__(self, data: dict):
        self.id = None  # no DB row — never used as an NPC (name-keyed runtime)
        self.name = str(data.get("name", ""))
        self.personality = data.get("personality", "") or ""
        self.voice_style = data.get("voice_style") or None
        self.secret = data.get("secret") or None
        self.knowledge = data.get("knowledge") or []
        self.schedule = data.get("schedule") or {}
        self.initial_location = data.get("initial_location", "") or ""
        self.description = data.get("description") or None
        self.narrative_weight = int(data.get("narrative_weight") or 0)
        # Character schema peer relations use {target, trust, kind}; the relation
        # seeder reads {target, trust, label, history_summary}. Map kind→label.
        self.initial_peer_relations = [
            {
                "target": r.get("target"),
                "trust": r.get("trust", 0),
                "label": r.get("label") or r.get("kind"),
                "history_summary": r.get("history_summary"),
            }
            for r in (data.get("initial_peer_relations") or [])
            if isinstance(r, dict) and r.get("target")
        ]
        self.playable = False
        self.mode = data.get("mode", "both")
        self.gender = data.get("gender", "")
        self.abilities = data.get("abilities") or []
        self.starting_inventory = data.get("starting_inventory") or []


def _attached_npcs_from_script(
    script: Script | None, *, taken_names: set[str]
) -> list[_AttachedNPC]:
    """Build runtime NPCs from ``Script.local_characters`` (反哺), skipping any
    whose name collides with a real world character or the player."""
    if script is None:
        return []
    out: list[_AttachedNPC] = []
    seen = set(taken_names)
    for raw in (getattr(script, "local_characters", None) or []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(_AttachedNPC(raw))
    return out


async def load_recent_messages(
    db: AsyncSession, session_id: str, limit: int | None = None
) -> list[dict]:
    """The Director's non-compacted message window, oldest-first.

    ``limit`` is a safety ceiling (``settings.recent_message_hard_cap``), not a
    sliding window: kept above the compaction keep-size so it normally returns
    the full non-compacted history — a stable, append-only prefix that stays
    prefix-cacheable turn to turn.
    """
    if limit is None:
        limit = settings.recent_message_hard_cap
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.is_compressed.is_(False))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(result.scalars().all())
    ]


async def _reflect_one_npc(
    *,
    session_id: str,
    npc_name: str,
    npc_personality: str,
    llm_router,
) -> None:
    """Run NPC reflection in an isolated DB session so the request lifecycle
    is not blocked by the LLM call. Imported lazily to avoid a top-level
    cycle with services.npc_reflection_service.
    """
    from services.npc_reflection_service import maybe_reflect

    try:
        async with async_session() as fresh_db:
            await maybe_reflect(
                fresh_db,
                session_id=session_id,
                npc_name=npc_name,
                npc_personality=npc_personality,
                llm_router=llm_router,
            )
    except Exception:  # noqa: BLE001
        logger.warning(
            "npc_reflection.background_task_failed",
            session_id=session_id,
            npc_name=npc_name,
            exc_info=True,
        )


# Strong refs so fire-and-forget memory-extraction tasks aren't GC'd mid-flight.
_pending_memory_tasks: set[asyncio.Task] = set()


async def _extract_and_write_memories(
    *,
    orchestrator,
    session_id: str,
    round_number: int,
    known_npcs: list[str],
    bundle: dict,
) -> None:
    """Fire-and-forget post-turn long-term memory extraction.

    Replaces the Director's in-call ``memory_extracts`` (removed to save ~16%
    of its decode tokens). Runs the lean flash extractor off the critical path
    and writes to ``memory_entries`` in an isolated session. Falls back to
    deriving discovery memories from this turn's new_clues so hard facts are
    never lost if the extraction call fails or returns nothing.
    """
    try:
        extracts, _usage = await orchestrator._extract_memories_llm(bundle, known_npcs)
        if not extracts:
            extracts = [
                {"type": "discovery", "content": str(clue).strip(), "importance": "high"}
                for clue in (bundle.get("new_clues") or [])
                if str(clue).strip()
            ]
        if not extracts:
            return
        async with async_session() as fresh_db:
            entries = orchestrator.memory_manager.parse_memory_extracts(
                {"memory_extracts": extracts},
                session_id=session_id,
                round_number=round_number,
                known_npcs=known_npcs,
            )
            await orchestrator.memory_manager.attach_embeddings(entries)
            for entry in entries:
                fresh_db.add(MemoryEntry(**entry))
            await fresh_db.commit()
    except Exception:  # noqa: BLE001
        logger.warning(
            "async_memory_extract.background_task_failed",
            session_id=session_id,
            round_number=round_number,
            exc_info=True,
        )


TEST_EXIT_COMMANDS = {"/结束测试"}

# 玩家"主动退场"哨兵。前端检测到退场意图、玩家确认后，由前端以此保留串调用
# action 接口触发；不是用户可见/可手打的文案，detection 走 frontend/lib/exit-intent.ts。
WITHDRAW_COMMANDS = {"__inkwild_withdraw__"}


class GameService:
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    async def start_game(
        self,
        db: AsyncSession,
        user_id: str,
        world_id: str,
        character_id: str,
        mode: str,
        script_id: str | None = None,
        authors_note: str | None = None,
        force_abandon_session_id: str | None = None,
        is_admin: bool = False,
        start_stage_id: str | None = None,
    ) -> AsyncIterator[dict]:
        # 用户在 start 页选择「放弃旧的开新」时，先原子地把旧 session 标为 abandoned，
        # 再走正常的 start 流程；两步在同一事务串行，避免半态。
        if force_abandon_session_id:
            await self._abandon_session(db, user_id, force_abandon_session_id)

        world = await db.get(World, world_id)
        if not world:
            raise AppError(40001, "世界不存在")
        # 访问闸：published 对所有人开放；private（及其它非公开态）仅 owner / admin 可玩。
        # 顺手堵上原先"任意 world_id 都能开局（含 withdrawn）"的隐患。
        if (
            world.status != "published"
            and str(world.created_by_user_id) != str(user_id)
            and not is_admin
        ):
            raise AppError(40001, "世界不存在")

        character = await db.get(WorldCharacter, character_id)
        # 角色必须存在且属于本世界——堵住 API 直传任意/跨世界 character_id。
        if not character or str(character.world_id) != str(world.id):
            raise AppError(40002, "角色不存在")

        resolved_script_id = None
        if mode == "script":
            if script_id:
                script = await db.get(Script, script_id)
                # 公开剧本对所有人；私有剧本仅 owner / admin 可玩。
                script_accessible = bool(script) and script.world_id == world.id and (
                    script.is_published
                    or str(script.created_by_user_id) == str(user_id)
                    or is_admin
                )
                if not script_accessible:
                    raise AppError(40008, "剧本不存在或未发布")
                # 剧本可玩名单非空时，角色必须在名单内；空名单 = 放行世界全部可玩角色。
                roster = [str(cid) for cid in (script.playable_character_ids or [])]
                if roster and str(character.id) not in roster:
                    raise AppError(40009, "该角色不在此剧本中")
                resolved_script_id = script.id
            elif not world.script_setting:
                raise AppError(40008, "当前世界没有可用剧本")

        # 自由模式「人生进度」起点：仅自由模式 + 世界配了 free_start_stages + 选的是主角
        # + stage_id 命中，四者俱全才生效；否则 None，走老的固定 initial_location 开局。
        # （spec docs/plans/2026-06-24-free-start-stages.md）
        start_stage: dict | None = None
        if mode == "free" and start_stage_id and isinstance(world.free_start_stages, dict):
            fss = world.free_start_stages
            if str(fss.get("protagonist_character_id") or "") == str(character.id):
                start_stage = next(
                    (
                        s
                        for s in (fss.get("stages") or [])
                        if isinstance(s, dict) and str(s.get("id") or "") == str(start_stage_id)
                    ),
                    None,
                )
            if start_stage is None:
                logger.info(
                    "start_stage_unresolved",
                    world_id=str(world.id),
                    character_id=str(character.id),
                    start_stage_id=start_stage_id,
                )
        start_location = (
            str(start_stage.get("start_location") or "").strip() if start_stage else ""
        ) or character.initial_location

        npcs = await self._load_session_npcs(
            db,
            world_id=world.id,
            exclude_character_id=character.id,
            player_name=character.name,
            script_id=resolved_script_id,
        )
        # Seed each NPC's OPENING attitude toward the player from the player's
        # public identity × the NPC's profile (one cheap LLM call). Generated
        # worlds carry no authored player↔NPC relations, so without this every
        # NPC opens at a flat trust=3 and warms up generically. Falls back to
        # that flat default on any failure or when NPC_INITIAL_STANCE_ENABLED=false.
        stances: dict[str, dict] = {}
        if settings.npc_initial_stance_enabled:
            # Surface the stance inference as the opening's first milestone so the
            # ~5s call isn't dead air on the loading screen (frontend renders it
            # as "体察各人对你的态度" via the processing/casting stage).
            yield {"type": "processing", "kind": "progress", "stage": "casting"}
            stances = await infer_initial_stances(
                self.orchestrator.npc_llm_router,
                {"name": character.name, "description": (character.description or "").strip()},
                [
                    {
                        "name": npc.name,
                        "personality": npc.personality,
                        "description": npc.description or "",
                        "narrative_weight": npc.narrative_weight or 0,
                    }
                    for npc in npcs
                ],
            )

        # 起点预设里「认识的人」直接覆盖 stance 推断：命中的 NPC 用预设的中高 trust +
        # standing 备注，未命中的照旧走推断（或默认 trust=3）。无论 stance 开关都生效。
        if start_stage:
            for rel in start_stage.get("known_relations") or []:
                if not isinstance(rel, dict):
                    continue
                npc_name = str(rel.get("npc") or "").strip()
                if npc_name:
                    stances[npc_name] = {
                        "trust": 6,
                        "mood": "正常",
                        "note": str(rel.get("standing") or "").strip(),
                    }

        def _seed_player_relation(npc_name: str) -> dict:
            s = stances.get(npc_name)
            if not s:
                return {"trust": 3, "mood": "正常", "last_interaction": ""}
            return {"trust": s["trust"], "mood": s["mood"], "note": s.get("note", ""), "last_interaction": ""}

        initial_state = GameState(
            current_time="第1天·上午",
            current_location=start_location,
            player_inventory=character.starting_inventory or [],
            discovered_clues=[],
            npc_relations={npc.name: _seed_player_relation(npc.name) for npc in npcs},
            triggered_events=[],
            visited_locations=[start_location],
            time_index=0,
        )
        if mode == "free":
            world_tensions: list[str] = []
            if world.free_setting:
                world_tensions = [line.strip() for line in world.free_setting.split("\n") if line.strip()]
            npc_dicts = [
                {"name": npc.name, "secret": npc.secret, "knowledge": npc.knowledge or []}
                for npc in npcs
            ]
            intent_state = init_npc_intents(npc_dicts, world_tensions)
            initial_state.npc_intents = intent_state["npc_intents"]
            initial_state.info_items = intent_state["info_items"]
            initial_state.world_conflicts = intent_state["world_conflicts"]

        # Initialize NPC locations from schedule
        for npc in npcs:
            if npc.initial_location:
                initial_state.npc_locations[npc.name] = npc.initial_location

        # 强制单局：开新局前，把同键下所有进行中的旧局结束掉。键与 start 页查重一致
        # （剧本模式 = 世界+剧本，自由模式 = 世界+角色）。堵住"评测/直叩 API/多 tab
        # 无限堆 playing"；与顶部 force_abandon_session_id（只结束单个）互补——这里
        # 把同键的全部清掉，保证一个键始终至多一个进行中局。
        await self._retire_active_sessions_for_key(
            db, user_id, world.id, mode, resolved_script_id, character.id
        )

        session = GameSession(
            user_id=user_id,
            world_id=world.id,
            character_id=character.id,
            script_id=resolved_script_id,
            authors_note=authors_note,
            mode=mode,
            status="playing",
            game_state=initial_state.to_dict(),
            rounds_played=0,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        # NPC-2 — seed persistent NPC↔NPC relations from
        # WorldCharacter.initial_peer_relations. Directed: A→B and B→A live in
        # separate rows; B→A defaults to A→B's values unless B explicitly
        # declared its own view.
        if settings.npc_peer_relations_enabled:
            self._seed_npc_relations(db, session_id=str(session.id), npcs=npcs)
            await db.commit()

        yield {"type": "session_created", "session_id": str(session.id)}
        # 提前把已落库的初始 game_state 发给前端：setup 页据此 markReady 提前跳转，
        # 落到 play 页时 gameState 已在手、舞台直接渲染，开场旁白随后在 play 页流式呈现，
        # 而不是等开场旁白整段跑完才发 state_update（那样玩家会盯着 setup loading 等很久）。
        yield {"type": "state_update", "game_state": initial_state.to_dict()}

        world_data = await self._load_world_data(db, world, npcs, script_id=resolved_script_id, player_character=character)
        opening_framing = (
            str(start_stage.get("opening_framing") or "").strip() if start_stage else ""
        )
        if opening_framing:
            # 起点预设替换默认的「刚刚抵达 X」——后者假设全新到场，与「你已是元婴」类
            # 进阶起点自相矛盾。开场定调直接喂处境，让旁白据此起笔。
            opening_prompt = (
                f"游戏开始。玩家扮演{character.name}（{character.description}）。"
                f"此刻的处境：{opening_framing}"
                f"故事从{start_location}展开。"
                "请据此描写开场场景，营造氛围，介绍周围环境和可见的NPC；"
                "把此刻在场的人都纳入本回合的在场名单，并给玩家三个具体、可立即上手的开场行动方向。"
            )
        else:
            opening_prompt = (
                f"游戏开始。玩家扮演{character.name}（{character.description}），"
                f"刚刚抵达{start_location}。"
                "请描写开场场景，营造氛围，介绍周围环境和可见的NPC；"
                "把此刻在场的人都纳入本回合的在场名单，并给玩家三个具体、可立即上手的开场行动方向。"
            )

        with usage_context(
            purpose="game", session_id=str(session.id), user_id=user_id
        ):
            async for event in self._consume_turn(
                db=db,
                session=session,
                action_text=opening_prompt,
                turn_stream=self.orchestrator.process_action(
                    action_text=opening_prompt,
                    game_state=initial_state,
                    recent_messages=[],
                    context_summary=None,
                    world_data=world_data,
                    game_mode=mode,
                    memory_context=session.context_summary or "",
                    authors_note=authors_note,
                    memory_entries=[],
                    all_messages=[],
                    session_id=str(session.id),
                    round_number=1,
                    db=db,
                    known_npcs=[npc.name for npc in npcs],
                    emit_state_ready=True,
                ),
                record_turn_state=False,
                save_messages=True,
                rounds_mode="set_one",
                save_user_message=False,
            ):
                yield event

    async def process_action(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        action_text: str,
        is_retry: bool = False,
    ) -> AsyncIterator[dict]:
        session = await self._get_owned_session(db, session_id, user_id)
        if session.status != "playing":
            raise AppError(40004, "游戏未在进行中")

        # 主动退场：放在 cost gate 之前 —— 费用封顶的 session 也必须能体面收场。
        # 绕过 orchestrator，只用 ending_summary 槽生成一段"落幕白"，不推进世界。
        if self._is_withdraw_command(action_text):
            async for event in self._consume_turn(
                db=db,
                session=session,
                action_text=action_text,
                turn_stream=self._withdraw_turn_stream(session),
                record_turn_state=False,
                save_messages=False,
                rounds_mode="none",
            ):
                yield event
            return

        session_cost_cents = await self._get_session_cost_cents(db, session)
        cost_status = classify_session_cost(
            session_cost_cents,
            soft_warn_cost_cents=settings.game_session_soft_warn_cost_cents,
            hard_cap_cost_cents=settings.game_session_hard_cap_cost_cents,
        )
        if cost_status.status == CostGuardrailStatus.CAPPED:
            yield {
                "type": "cap_reached",
                "suggest": "ending",
                "message": "本次故事已达到费用上限，建议进入结局。",
                "total_cost_cents": cost_status.total_cost_cents,
                "cap_cost_cents": cost_status.hard_cap_cost_cents,
            }
            yield {"type": "done"}
            return
        if cost_status.status == CostGuardrailStatus.WARN:
            yield {
                "type": "cost_warning",
                "suggest": "ending",
                "message": "本次故事接近费用上限，建议尽快收束剧情。",
                "total_cost_cents": cost_status.total_cost_cents,
                "cap_cost_cents": cost_status.hard_cap_cost_cents,
            }

        if self._is_test_exit_command(action_text):
            async for event in self._consume_turn(
                db=db,
                session=session,
                action_text=action_text,
                turn_stream=self._test_exit_turn_stream(session),
                record_turn_state=False,
                save_messages=True,
                rounds_mode="none",
            ):
                yield event
            return

        if not is_retry:
            session.state_snapshot = session.game_state
            session.last_action_text = action_text
            session.retry_count = 0
            await db.commit()

        game_state = GameState.from_dict(session.game_state)
        recent_messages = await load_recent_messages(db, session.id)
        memory_result = await db.execute(
            select(MemoryEntry)
            .where(MemoryEntry.session_id == session.id)
            .order_by(MemoryEntry.importance.desc(), MemoryEntry.created_at.desc())
            .limit(15)
        )
        memory_entries = [
            {
                "memory_type": memory.memory_type,
                "content": memory.content,
                "round_number": memory.round_number,
            }
            for memory in memory_result.scalars().all()
        ]
        all_messages_result = await db.execute(
            select(Message)
            .where(Message.session_id == session.id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        all_messages = [
            {"role": message.role, "content": message.content, "round": index // 2 + 1}
            for index, message in enumerate(all_messages_result.scalars().all())
        ]

        world = await db.get(World, session.world_id)
        character = await db.get(WorldCharacter, session.character_id)
        npcs = await self._load_session_npcs(
            db,
            world_id=world.id,
            exclude_character_id=session.character_id,
            player_name=character.name,
            script_id=session.script_id,
        )
        world_data = await self._load_world_data(db, world, npcs, script_id=session.script_id, player_character=character)

        # AOP token recording: every LLM event yielded by the orchestrator
        # is attributed to this session via the ambient ``UsageContext``.
        with usage_context(
            purpose="game", session_id=str(session.id), user_id=user_id
        ):
            async for event in self._consume_turn(
                db=db,
                session=session,
                action_text=action_text,
                turn_stream=self.orchestrator.process_action(
                    action_text=action_text,
                    game_state=game_state,
                    recent_messages=recent_messages,
                    context_summary=session.context_summary,
                    world_data=world_data,
                    game_mode=session.mode,
                    memory_context=session.context_summary or "",
                    authors_note=session.authors_note,
                    memory_entries=memory_entries,
                    all_messages=all_messages,
                    session_id=str(session.id),
                    round_number=(session.rounds_played or 0) + 1,
                    db=db,
                    known_npcs=[npc.name for npc in npcs],
                    emit_state_ready=True,
                ),
                record_turn_state=False,
                save_messages=True,
                rounds_mode="increment",
            ):
                yield event

    async def retry_action(self, db: AsyncSession, user_id: str, session_id: str) -> AsyncIterator[dict]:
        session = await self._get_owned_session(db, session_id, user_id)
        if session.status != "playing":
            raise AppError(40004, "游戏未在进行中")
        if not session.state_snapshot or not session.last_action_text:
            raise AppError(40006, "没有可重试的操作")
        if session.retry_count >= 3:
            raise AppError(40007, "已达最大重试次数")

        result = await db.execute(
            select(Message)
            .where(Message.session_id == session.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(2)
        )
        for message in result.scalars().all():
            await db.delete(message)

        snapshot_round_number = int((session.state_snapshot or {}).get("round_number") or 0)
        await db.execute(
            delete(CaseBoardHistory)
            .where(
                CaseBoardHistory.session_id == session.id,
                CaseBoardHistory.round_number > snapshot_round_number,
            )
            .execution_options(synchronize_session=False)
        )

        try:
            await save_session_state(
                db,
                session.id,
                session.state_snapshot,
                expected_version=int(session.version or 0),
                extra_values={"retry_count": (session.retry_count or 0) + 1},
            )
        except StaleVersionError as exc:
            await db.rollback()
            raise AppError(40901, "游戏状态已被更新，请刷新后重试", status_code=409) from exc
        await db.commit()
        await db.refresh(session)

        async for event in self.process_action(db, user_id, session_id, session.last_action_text, is_retry=True):
            yield event

    async def pause_game(self, db: AsyncSession, user_id: str, session_id: str):
        session = await self._get_owned_session(db, session_id, user_id)
        session.status = "paused"
        await db.commit()

    async def abandon_game(self, db: AsyncSession, user_id: str, session_id: str):
        """玩家在 PauseOverlay 主动「放弃这局」时调用。"""
        await self._abandon_session(db, user_id, session_id)
        await db.commit()

    async def _abandon_session(self, db: AsyncSession, user_id: str, session_id: str) -> None:
        """把 session 置为 ended + ending_type=abandoned。
        - 已 ended 的直接幂等返回，不重复改 ended_at
        - 不属于当前用户的抛 40003（和 _get_owned_session 一致）
        - 调用方负责 commit（start_game 内联调用时跟主流程一起 commit）
        """
        session = await self._get_owned_session(db, session_id, user_id)
        if session.status == "ended":
            return
        session.status = "ended"
        session.ending_type = "abandoned"
        session.ended_at = utcnow()

    async def _retire_active_sessions_for_key(
        self,
        db: AsyncSession,
        user_id: str,
        world_id,
        mode: str,
        script_id,
        character_id,
    ) -> None:
        """强制单局：把同键下所有进行中(playing/paused)的旧局置为 ended+abandoned。
        - 键与 start 页查重一致：剧本模式 (user, world, script)，自由模式
          (user, world, character)。
        - 剧本模式但无离散 script_id（world.script_setting 内联剧本）时无法判键，
          跳过不误伤。
        - 调用方负责 commit（start_game 内联调用时跟主流程一起 commit）。
        """
        conditions = [
            GameSession.user_id == user_id,
            GameSession.world_id == world_id,
            GameSession.status.in_(("playing", "paused")),
        ]
        if mode == "script":
            if script_id is None:
                return
            conditions.append(GameSession.script_id == script_id)
        else:
            conditions.append(GameSession.mode == "free")
            conditions.append(GameSession.character_id == character_id)

        rows = (await db.execute(select(GameSession).where(*conditions))).scalars().all()
        now = utcnow()
        for old in rows:
            old.status = "ended"
            old.ending_type = "abandoned"
            old.ended_at = now

    async def get_session_detail(self, db: AsyncSession, session_id: str, user_id: str) -> dict:
        session = await self._get_owned_session(db, session_id, user_id)

        world = await db.get(World, session.world_id)
        character = await db.get(WorldCharacter, session.character_id)

        script_type = "mystery"
        if session.script_id:
            script = await db.get(Script, session.script_id)
            if script:
                script_type = getattr(script, 'script_type', None) or "mystery"

        messages = (
            (
                await db.execute(
                    select(Message)
                    .where(Message.session_id == session.id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            )
            .scalars()
            .all()
        )

        return GameSessionDetailResponse(
            session_id=str(session.id),
            status=session.status,
            world_name=world.name if world else "",
            character_name=character.name if character else "",
            character_description=character.description if character else "",
            character_abilities=character.abilities if character and character.abilities else [],
            game_state=session.game_state,
            messages=[
                SessionMessageDTO(
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at.isoformat(),
                )
                for message in messages
            ],
            mode=session.mode,
            script_type=script_type,
        ).model_dump()

    async def resume_game(self, db: AsyncSession, user_id: str, session_id: str) -> AsyncIterator[dict]:
        session = await self._get_owned_session(db, session_id, user_id)
        if session.status != "paused":
            raise AppError(40005, "游戏未暂停")

        session.status = "playing"
        session.last_played_at = utcnow()
        await db.commit()

        game_state = GameState.from_dict(session.game_state)
        world = await db.get(World, session.world_id)
        character = await db.get(WorldCharacter, session.character_id)
        npcs = await self._load_session_npcs(
            db,
            world_id=world.id,
            exclude_character_id=session.character_id,
            player_name=character.name,
            script_id=session.script_id,
        )
        world_data = await self._load_world_data(db, world, npcs, script_id=session.script_id, player_character=character)
        recap_prompt = (
            "玩家刚从中断中回来。用一段简短的叙述帮玩家回忆之前发生了什么，"
            "包括关键事件和当前处境。然后以'你现在想做什么？'结尾。"
        )

        with usage_context(
            purpose="game", session_id=str(session.id), user_id=user_id
        ):
            async for event in self._consume_turn(
                db=db,
                session=session,
                action_text=recap_prompt,
                turn_stream=self.orchestrator.process_action(
                    action_text=recap_prompt,
                    game_state=game_state,
                    recent_messages=[],
                    context_summary=session.context_summary,
                    world_data=world_data,
                    game_mode=session.mode,
                    memory_context=session.context_summary or "",
                    authors_note=session.authors_note,
                    memory_entries=[],
                    all_messages=[],
                    session_id=str(session.id),
                    round_number=session.rounds_played or 0,
                    db=db,
                    known_npcs=[npc.name for npc in npcs],
                    emit_state_ready=True,
                ),
                record_turn_state=False,
                save_messages=False,
                rounds_mode="none",
            ):
                if event["type"] in ("narrative", "state_update", "ending"):
                    yield event
                elif event["type"] == "done":
                    yield {"type": "done"}

    async def get_game_state(self, db: AsyncSession, user_id: str, session_id: str) -> dict:
        session = await self._get_owned_session(db, session_id, user_id)
        return session.game_state

    async def _get_owned_session(self, db: AsyncSession, session_id: str, user_id: str) -> GameSession:
        session = await db.get(GameSession, session_id)
        if not session or session.user_id != user_id:
            raise AppError(40003, "游戏会话不存在", status_code=404)
        return session

    async def _consume_turn(
        self,
        db: AsyncSession,
        session: GameSession,
        action_text: str,
        turn_stream: AsyncIterator[dict],
        record_turn_state: bool,
        save_messages: bool,
        rounds_mode: str,
        save_user_message: bool = True,
    ) -> AsyncIterator[dict]:
        narrative_parts: list[str] = []
        expected_version = int(session.version or 0)
        state_committed = False
        case_board_history_committed = False
        committed_round_number = session.rounds_played or 0

        async for event in turn_stream:
            if event["type"] == "narrative":
                narrative_parts.append(event["text"])
                yield event
            elif event["type"] == "state_ready":
                committed_round_number = await self._commit_turn_state(
                    db=db,
                    session=session,
                    new_state=event["new_state"],
                    rounds_mode=rounds_mode,
                    expected_version=expected_version,
                    case_board_history_entries=event.get("case_board_history_entries") or [],
                )
                expected_version = int(session.version or expected_version + 1)
                state_committed = True
                case_board_history_committed = bool(event.get("case_board_history_entries"))
            elif event["type"] == "state_update":
                yield event
            elif event["type"] == "ending":
                session.status = "ended"
                session.ending_type = event["ending_type"]
                session.ended_at = utcnow()
                await db.commit()
                yield event
            elif event["type"] == "done":
                new_state = event["new_state"]
                if not state_committed:
                    committed_round_number = await self._commit_turn_state(
                        db=db,
                        session=session,
                        new_state=new_state,
                        rounds_mode=rounds_mode,
                        expected_version=expected_version,
                        case_board_history_entries=event.get("case_board_history_entries") or [],
                    )
                    case_board_history_committed = bool(event.get("case_board_history_entries"))
                elif event.get("case_board_history_entries") and not case_board_history_committed:
                    self._add_case_board_history_entries(
                        db,
                        session_id=str(session.id),
                        round_number=committed_round_number,
                        entries=event["case_board_history_entries"],
                    )
                    case_board_history_committed = True
                if memory_extracts := event.get("memory_extracts"):
                    parsed_entries = self.orchestrator.memory_manager.parse_memory_extracts(
                        {"memory_extracts": memory_extracts},
                        session_id=str(session.id),
                        round_number=committed_round_number,
                        known_npcs=self._get_npc_names(session),
                    )
                    # Phase 1.B.2 — attach embeddings (best-effort; embedding=None on failure).
                    await self.orchestrator.memory_manager.attach_embeddings(parsed_entries)
                    for entry in parsed_entries:
                        db.add(MemoryEntry(**entry))
                # Write dual-perspective NPC interaction memories
                if dual_entries := event.get("dual_memory_entries"):
                    await self.orchestrator.memory_manager.attach_embeddings(dual_entries)
                    for entry in dual_entries:
                        db.add(MemoryEntry(**entry))
                if save_messages:
                    if save_user_message:
                        db.add(Message(session_id=session.id, role="user", content=action_text))
                    db.add(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="".join(narrative_parts),
                            state_snapshot=session.game_state,
                            npc_dialogues=event.get("npc_dialogues"),
                        )
                    )
                await db.commit()
                # Phase 1 NPC reflection: fire-and-forget per involved NPC.
                # Uses an isolated DB session so the SSE response and session
                # lock are released immediately; reflection failures are
                # silent and never block the player turn.
                if (
                    settings.npc_reflection_enabled
                    and getattr(self.orchestrator, "compression_llm_router", None) is not None
                ):
                    for npc in event.get("involved_npcs_for_reflection") or []:
                        npc_name = npc.get("name")
                        if not npc_name:
                            continue
                        asyncio.create_task(
                            _reflect_one_npc(
                                session_id=str(session.id),
                                npc_name=npc_name,
                                npc_personality=npc.get("personality", ""),
                                llm_router=self.orchestrator.compression_llm_router,
                            )
                        )
                # Async long-term memory extraction: fire-and-forget, off the
                # critical path (Director no longer emits memory_extracts inline).
                if mem_bundle := event.get("mem_extract_input"):
                    mem_task = asyncio.create_task(
                        _extract_and_write_memories(
                            orchestrator=self.orchestrator,
                            session_id=str(session.id),
                            round_number=committed_round_number,
                            known_npcs=self._get_npc_names(session),
                            bundle=mem_bundle,
                        )
                    )
                    _pending_memory_tasks.add(mem_task)
                    mem_task.add_done_callback(_pending_memory_tasks.discard)
                yield event
            elif event["type"] == "case_board_update":
                # Phase-4 follow-up: the director's case_board tail finished
                # after `done` already committed this turn's core state + unlocked
                # the player. Persist only the case_board delta (+ history rows),
                # fire the async memory extraction (it wants the full case_board
                # reasoning), then forward so the board refreshes a beat later.
                if (
                    event.get("case_board_history_entries")
                    and not case_board_history_committed
                    and event.get("new_state") is not None
                ):
                    await self._commit_case_board_followup(
                        db,
                        session=session,
                        case_board=event["new_state"].case_board,
                        round_number=committed_round_number,
                        entries=event["case_board_history_entries"],
                    )
                    case_board_history_committed = True
                if mem_bundle := event.get("mem_extract_input"):
                    mem_task = asyncio.create_task(
                        _extract_and_write_memories(
                            orchestrator=self.orchestrator,
                            session_id=str(session.id),
                            round_number=committed_round_number,
                            known_npcs=self._get_npc_names(session),
                            bundle=mem_bundle,
                        )
                    )
                    _pending_memory_tasks.add(mem_task)
                    mem_task.add_done_callback(_pending_memory_tasks.discard)
                yield event
            else:
                yield event

    async def _commit_turn_state(
        self,
        *,
        db: AsyncSession,
        session: GameSession,
        new_state: GameState,
        rounds_mode: str,
        expected_version: int,
        case_board_history_entries: list[dict] | None = None,
    ) -> int:
        next_round_number = session.rounds_played or 0
        if rounds_mode == "set_one":
            next_round_number = 1
        elif rounds_mode == "increment":
            next_round_number = (session.rounds_played or 0) + 1

        state_dict = new_state.to_dict()
        saved_at = utcnow()
        try:
            await save_session_state(
                db,
                session.id,
                state_dict,
                expected_version=expected_version,
                extra_values={
                    "rounds_played": next_round_number,
                    "last_played_at": saved_at,
                },
            )
        except StaleVersionError as exc:
            await db.rollback()
            raise AppError(40901, "游戏状态已被更新，请刷新后重试", status_code=409) from exc

        if case_board_history_entries:
            self._add_case_board_history_entries(
                db,
                session_id=str(session.id),
                round_number=next_round_number,
                entries=case_board_history_entries,
            )

        await db.commit()
        await db.refresh(session)
        return next_round_number

    async def _commit_case_board_followup(
        self,
        db: AsyncSession,
        *,
        session: GameSession,
        case_board: dict,
        round_number: int,
        entries: list[dict],
    ) -> None:
        """Persist the Phase-4 case_board delta after `done` already committed
        this turn's core state.

        Re-reads the freshly persisted state and updates ONLY ``case_board`` —
        fire-and-forget writers (offstage ticks / reflections) may have touched
        other fields after the `done` commit, so we must not clobber them by
        re-saving a stale full snapshot. ``rounds_played`` is left untouched: the
        round was already counted at `done`.
        """
        await db.refresh(session)
        state_dict = dict(session.game_state or {})
        state_dict["case_board"] = case_board
        try:
            await save_session_state(
                db,
                session.id,
                state_dict,
                expected_version=int(session.version or 0),
                extra_values={"last_played_at": utcnow()},
            )
        except StaleVersionError as exc:
            await db.rollback()
            raise AppError(40901, "游戏状态已被更新，请刷新后重试", status_code=409) from exc

        if entries:
            self._add_case_board_history_entries(
                db,
                session_id=str(session.id),
                round_number=round_number,
                entries=entries,
            )

        await db.commit()
        await db.refresh(session)

    def _seed_npc_relations(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        npcs: list[WorldCharacter],
    ) -> None:
        """Materialize NPCRelation rows from each NPC's initial_peer_relations.

        Trust is hard-clamped to [-10, 10] (LLM hallucinated values get
        bounded). Targets pointing outside the NPC roster (player character,
        unknown name) are silently dropped — relations are NPC↔NPC only;
        player relations live in ``game_state.npc_relations``.
        """
        npc_name_set = {npc.name for npc in npcs}
        # (npc_a, npc_b) -> dict; explicit declarations win over symmetric backfill.
        rels: dict[tuple[str, str], dict] = {}
        for npc in npcs:
            for raw in (npc.initial_peer_relations or []):
                if not isinstance(raw, dict):
                    continue
                target = str(raw.get("target") or "").strip()
                if not target or target == npc.name or target not in npc_name_set:
                    continue
                try:
                    trust = int(raw.get("trust", 0))
                except (TypeError, ValueError):
                    trust = 0
                trust = max(-10, min(10, trust))
                label = (str(raw.get("label") or "").strip() or None)
                history = (str(raw.get("history_summary") or "").strip() or None)
                rels[(npc.name, target)] = {
                    "trust": trust,
                    "label": label,
                    "history_summary": history,
                }
        # Symmetric backfill — only when the peer never declared its own view.
        for (a, b), data in list(rels.items()):
            if (b, a) not in rels:
                rels[(b, a)] = dict(data)
        for (a, b), data in rels.items():
            db.add(
                NPCRelation(
                    session_id=session_id,
                    npc_a=a,
                    npc_b=b,
                    trust=data["trust"],
                    relationship_label=data["label"],
                    history_summary=data["history_summary"],
                )
            )

    def _add_case_board_history_entries(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        round_number: int,
        entries: list[dict],
    ) -> None:
        for entry in entries:
            db.add(
                CaseBoardHistory(
                    session_id=session_id,
                    round_number=round_number,
                    op_type=str(entry.get("op_type") or ""),
                    path=entry.get("path") or [],
                    payload=entry.get("payload") or {},
                    before=entry.get("before"),
                    after=entry.get("after"),
                    reason=entry.get("reason"),
                )
            )

    def _is_test_exit_command(self, action_text: str) -> bool:
        return action_text.strip() in TEST_EXIT_COMMANDS

    def _is_withdraw_command(self, action_text: str) -> bool:
        return action_text.strip() in WITHDRAW_COMMANDS

    async def _withdraw_turn_stream(self, session: GameSession) -> AsyncIterator[dict]:
        """玩家主动退场的"落幕白"：生成一段基于当前局面的体面收场，诚实地框成
        "在此处搁笔"（ending_type=withdrawn，不伪装成挣来的好结局）。复用 ending_summary
        槽；LLM 失败时退回静态兜底文案，绝不卡住退场。"""
        current_state = GameState.from_dict(session.game_state)
        ending = {"ending_type": "withdrawn", "title": "搁笔"}

        summary_data: dict = {}
        try:
            from engine.ending_system import generate_ending_summary

            summary_data = await generate_ending_summary(
                llm_router=self.orchestrator.ending_summary_llm_router,
                ending=ending,
                game_state=current_state,
                memory_context=session.context_summary or "",
                script_type="story",
                play_duration_minutes=0,
            )
        except Exception:
            logger.warning("withdraw_summary_failed", exc_info=True)

        if not (summary_data.get("ending_narrative") or "").strip():
            summary_data = {
                "ending_narrative": "你合上了这一页，故事在此处搁笔。未尽的篇章，留待来日再续。",
                "path_review": summary_data.get("path_review", []),
                "evidence_review": summary_data.get("evidence_review"),
            }

        yield {"type": "narrative", "text": summary_data["ending_narrative"]}
        yield {
            "type": "state_update",
            "game_state": current_state.to_dict(),
            "quick_actions": [],
            "triggered_events": [],
        }
        yield {
            "type": "ending",
            "ending_type": "withdrawn",
            "title": "搁笔",
            "summary": summary_data,
        }
        yield {"type": "done", "new_state": current_state, "usage": None}

    def _get_npc_names(self, session: GameSession) -> list[str]:
        """Extract NPC names from game_state npc_relations keys."""
        state = session.game_state or {}
        return list(state.get("npc_relations", {}).keys())

    async def _get_session_cost_cents(self, db: AsyncSession, session: GameSession) -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(TokenUsage.cost_cents), 0)).where(
                TokenUsage.session_id == session.id
            )
        )
        return int(result.scalar_one() or 0)

    async def _test_exit_turn_stream(self, session: GameSession) -> AsyncIterator[dict]:
        current_state = GameState.from_dict(session.game_state)
        yield {"type": "narrative", "text": "你说出了测试暗号，故事在这里暂时落幕。"}
        yield {
            "type": "state_update",
            "game_state": current_state.to_dict(),
            "quick_actions": [],
            "triggered_events": [],
        }
        yield {
            "type": "ending",
            "ending_type": "test_exit",
            "title": "测试结束",
        }
        yield {
            "type": "done",
            "new_state": current_state,
            "usage": None,
        }

    async def _load_session_npcs(
        self,
        db: AsyncSession,
        *,
        world_id: str,
        exclude_character_id,
        player_name: str,
        script_id: str | None,
    ) -> list:
        """Session NPC roster = world characters (minus the player) ∪ the
        script's 反哺 characters (``Script.local_characters``). The world is
        never mutated by a script; attached characters live only here at
        runtime, unioned by name."""
        npcs = list((await db.execute(
            select(WorldCharacter).where(
                WorldCharacter.world_id == world_id,
                WorldCharacter.id != exclude_character_id,
            )
        )).scalars().all())
        if script_id:
            script = await db.get(Script, script_id)
            taken = {n.name for n in npcs} | {player_name}
            npcs.extend(_attached_npcs_from_script(script, taken_names=taken))
        return npcs

    async def _load_world_data(self, db: AsyncSession, world: World, npcs: list[WorldCharacter], script_id: str | None = None, player_character: WorldCharacter | None = None) -> dict:
        script_type = "mystery"
        # legacy_events: old-shape rows for engine.event_system.check_events
        #   (trigger_type/trigger_condition); read in free mode only.
        # events_data_v2: new-shape rows for director / world_simulator /
        #   orchestrator intent firing (trigger.condition_dsl).
        legacy_events: list[dict] = []
        events_data_v2: list[dict] = []
        if script_id:
            script = await db.get(Script, script_id)
            if not script or script.world_id != world.id or not script.is_published:
                raise AppError(40008, "当前世界没有可用剧本")
            script_setting = script.script_setting or ""
            events_data_v2 = script.events_data or []
            endings_data = script.endings_data or []
            script_type = getattr(script, 'script_type', None) or "mystery"
        else:
            script_setting = world.script_setting or ""
            events = (await db.execute(select(Event).where(Event.world_id == world.id))).scalars().all()
            endings = (await db.execute(select(Ending).where(Ending.world_id == world.id))).scalars().all()
            legacy_events = [
                {
                    "id": str(event.id),
                    "name": event.name,
                    "trigger_type": event.trigger_type,
                    "trigger_condition": event.trigger_condition,
                    "effects": event.effects,
                    "mode": event.mode,
                }
                for event in events
            ]
            events_data_v2 = list(world.events_data or [])
            endings_data = [
                {
                    "id": str(ending.id),
                    "ending_type": ending.ending_type,
                    "title": ending.title,
                    "description": ending.description,
                    "priority": ending.priority,
                    "hard_conditions": ending.hard_conditions,
                    "soft_conditions": ending.soft_conditions,
                }
                for ending in endings
            ]

        npc_descriptions = "\n".join(
            f"- {npc.name}：{npc.personality}" + (f"（秘密：{npc.secret}）" if npc.secret else "") for npc in npcs
        )
        ending_conditions = "\n".join(
            f"- {ending['ending_type']}（{ending['title']}）：{ending.get('soft_conditions') or '硬性条件，后端判定'}"
            for ending in endings_data
        )

        # Player's PUBLIC identity, fed to NPCs so they recognise who they're
        # facing. Only name + public description — never personality/secret
        # (the engine doesn't puppet the player). None for callers that don't
        # pass the player character (e.g. display-only paths).
        player_public = None
        if player_character is not None:
            player_public = {
                "name": player_character.name,
                "description": (player_character.description or "").strip(),
            }

        return {
            "base_setting": world.base_setting,
            "player_public": player_public,
            "script_setting": script_setting,
            "npc_descriptions": npc_descriptions,
            "ending_conditions": ending_conditions,
            "script_type": script_type,
            "npcs": [
                {
                    "name": npc.name,
                    "personality": npc.personality,
                    "voice_style": npc.voice_style or "",
                    "secret": npc.secret or "",
                    # NPC's pre-game background knowledge (what this character
                    # already knows before the player's session begins). Fed
                    # into the NPC system prompt so it doesn't act ignorant of
                    # facts its character would obviously know.
                    "knowledge": list(npc.knowledge or []),
                    "initial_location": npc.initial_location,
                    "schedule": npc.schedule or {},
                }
                for npc in npcs
            ],
            "events": legacy_events,
            "events_data": events_data_v2,
            "endings": endings_data,
        }
