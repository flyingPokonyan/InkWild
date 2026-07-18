from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import hashlib
import inspect
import json
from typing import Any
import uuid

import structlog
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from llm.usage_context import pop_usage_context, push_usage_context, usage_accumulator
from models.draft import ScriptDraft, WorldDraft
from models.generation_task import GenerationTask, GenerationTaskEvent
from models.script import Script
from models.world import World, WorldCharacter
from utils import utcnow

logger = structlog.get_logger()

TERMINAL_TASK_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_GENERATION_TASK_STATUSES = ("pending", "running")
MAX_ACTIVE_TASKS_PER_USER = 10  # env/admin default; runtime reads settings below.
# Backward-compat alias kept temporarily to avoid breaking any direct imports
MAX_ACTIVE_GENERATION_TASKS_PER_ADMIN = MAX_ACTIVE_TASKS_PER_USER
GENERATION_TASK_LIMIT_RETRY_AFTER_SECONDS = 30
# BUGS #17 — liveness reaper. Tasks whose updated_at is older than this
# threshold while still in an active status are presumed dead (worker
# crashed / SIGKILL) and get marked failed so the per-user quota releases.
# Honest world generation runs under ~10 min; script generation under ~3
# min. 30 min covers slow IP-loaded runs with comfortable margin.
STALE_TASK_AFTER_SECONDS = 1800

# outline 短于此长度即视为「支撑不足」，触发 grok 联网自动选题。
_OUTLINE_AUTO_RECOMMEND_THRESHOLD = 12

PHASE_A = "phase_a"
PHASE_B = "phase_b"
REFINE = "refine"  # AI 精修：对已生成草稿的 payload 做定向内容重写


class GenerationTaskLimitExceeded(Exception):
    def __init__(self, *, active_count: int, limit: int):
        super().__init__("generation task limit exceeded")
        self.active_count = active_count
        self.limit = limit
        self.retry_after_seconds = GENERATION_TASK_LIMIT_RETRY_AFTER_SECONDS


def _active_task_limit_per_user() -> int:
    from config import settings

    return max(1, int(getattr(settings, "generation_task_active_limit_per_user", MAX_ACTIVE_TASKS_PER_USER)))


def _can_wrap_v2(base_agent: Any) -> bool:
    """V2 wrap 的前提：feature flag 开 + base_agent 暴露真实 v1 agent 的三件套
    (llm / image_gen / research_broker)。测试里的 fake agent 缺这些 → 走 v1 path。"""
    from config import settings
    if not settings.world_creator_v2_enabled or base_agent is None:
        return False
    return all(hasattr(base_agent, attr) for attr in ("llm", "image_gen", "research_broker"))


async def _resolve_factory_result(result: Any) -> Any:
    """Normalize factory return so asyncio.wait_for can always await it.

    Factories may be sync (lambda returning a built object) or async (returning
    a coroutine). wait_for requires an awaitable, so wrap non-awaitable results.
    """
    if inspect.isawaitable(result):
        return await result
    return result


def _script_reference_summary_from_model(script: Script) -> dict:
    event_names: list[str] = []
    for event in script.events_data or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name", "")).strip()
        if name:
            event_names.append(name)

    ending_types: list[str] = []
    for ending in script.endings_data or []:
        if not isinstance(ending, dict):
            continue
        ending_type = str(ending.get("ending_type", "")).strip()
        if ending_type and ending_type not in ending_types:
            ending_types.append(ending_type)

    return {
        "name": script.name,
        "description": script.description,
        "script_setting": script.script_setting,
        "event_names": event_names,
        "ending_types": ending_types,
    }


class GenerationTaskService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        world_creator_factory: Callable[[], Any],
        normalize_world_payload: Callable[[dict], dict],
        normalize_script_payload: Callable[[dict], dict],
    ):
        self.session_factory = session_factory
        self.world_creator_factory = world_creator_factory
        self.normalize_world_payload = normalize_world_payload
        self.normalize_script_payload = normalize_script_payload
        self._running_tasks: set[asyncio.Task] = set()

    async def start_world_generation(
        self,
        *,
        description: str,
        genre: str = "",
        era: str = "",
        user_id: str,
        phase: str | None = None,
    ) -> tuple[str, str]:
        async with self.session_factory() as session:
            await self._acquire_generation_task_limit_lock(session, user_id)
            await self._enforce_generation_task_limit(session, user_id)
            draft = WorldDraft(payload=self.normalize_world_payload({}), created_by_user_id=user_id)
            session.add(draft)
            await session.flush()
            request_payload: dict[str, Any] = {
                "description": description,
                "genre": genre,
                "era": era,
                "user_id": user_id,
            }
            if phase:
                request_payload["phase"] = phase
            generation_run_id = str(uuid.uuid4())
            task = GenerationTask(
                generation_run_id=generation_run_id,
                kind="world",
                draft_type="world_draft",
                draft_id=draft.id,
                request_payload=request_payload,
                created_by_user_id=user_id,
                started_at=utcnow(),
                current_phase="boot",
                current_code="task_created",
                current_message="生成任务已创建，正在准备创作会话…",
                last_event_seq=1,
            )
            session.add(task)
            await session.flush()
            task.root_task_id = task.id
            session.add(
                GenerationTaskEvent(
                    task_id=task.id,
                    seq=1,
                    event_name="progress",
                    payload={
                        "phase": "boot",
                        "code": "task_created",
                        "message": "生成任务已创建，正在准备创作会话…",
                    },
                )
            )
            await session.commit()
            return str(draft.id), str(task.id)

    async def start_world_phase_b_task(
        self,
        *,
        draft_id: str,
        description: str,
        genre: str = "",
        era: str = "",
        user_id: str,
        ip_recognition: dict | None = None,
        fidelity_mode: str = "none",
    ) -> str:
        """Create a phase_b world generation task on an EXISTING draft.

        Used by the continue-generation endpoint after Stage 0 (phase_a) has
        succeeded and the admin has picked a fidelity_mode in the UI.
        """
        async with self.session_factory() as session:
            await self._acquire_generation_task_limit_lock(session, user_id)
            await self._enforce_generation_task_limit(session, user_id)
            parent_task = (
                await session.execute(
                    select(GenerationTask)
                    .where(
                        GenerationTask.draft_type == "world_draft",
                        GenerationTask.draft_id == draft_id,
                    )
                    .order_by(GenerationTask.created_at.desc())
                )
            ).scalars().first()
            generation_run_id = str(
                parent_task.generation_run_id if parent_task and parent_task.generation_run_id else uuid.uuid4()
            )
            root_task_id = str(
                parent_task.root_task_id if parent_task and parent_task.root_task_id else parent_task.id
            ) if parent_task else None
            task = GenerationTask(
                generation_run_id=generation_run_id,
                root_task_id=root_task_id,
                parent_task_id=str(parent_task.id) if parent_task else None,
                kind="world",
                draft_type="world_draft",
                draft_id=draft_id,
                request_payload={
                    "description": description,
                    "genre": genre,
                    "era": era,
                    "user_id": user_id,
                    "phase": PHASE_B,
                    "ip_recognition": ip_recognition,
                    "fidelity_mode": fidelity_mode,
                },
                created_by_user_id=user_id,
                started_at=utcnow(),
                current_phase="boot",
                current_code="task_created",
                current_message="生成任务已创建，正在准备创作会话…",
                last_event_seq=1,
            )
            session.add(task)
            await session.flush()
            if task.root_task_id is None:
                task.root_task_id = task.id
            session.add(
                GenerationTaskEvent(
                    task_id=task.id,
                    seq=1,
                    event_name="progress",
                    payload={
                        "phase": "boot",
                        "code": "task_created",
                        "message": "生成任务已创建，正在准备创作会话…",
                    },
                )
            )
            await session.commit()
            return str(task.id)

    async def start_world_refine_task(
        self,
        *,
        draft_id: str,
        targets: list[str],
        user_id: str,
    ) -> str:
        """Create a `refine` task on an EXISTING world draft.

        Ownership is enforced by the API layer. Inherits generation_run_id /
        root_task_id from the draft's latest task so all runs stay linked.
        """
        async with self.session_factory() as session:
            await self._acquire_generation_task_limit_lock(session, user_id)
            await self._enforce_generation_task_limit(session, user_id)
            parent_task = (
                await session.execute(
                    select(GenerationTask)
                    .where(
                        GenerationTask.draft_type == "world_draft",
                        GenerationTask.draft_id == draft_id,
                    )
                    .order_by(GenerationTask.created_at.desc())
                )
            ).scalars().first()
            generation_run_id = str(
                parent_task.generation_run_id if parent_task and parent_task.generation_run_id else uuid.uuid4()
            )
            root_task_id = (
                str(parent_task.root_task_id or parent_task.id) if parent_task else None
            )
            task = GenerationTask(
                generation_run_id=generation_run_id,
                root_task_id=root_task_id,
                parent_task_id=str(parent_task.id) if parent_task else None,
                kind="world",
                draft_type="world_draft",
                draft_id=draft_id,
                request_payload={
                    "phase": REFINE,
                    "targets": list(targets or []),
                    "user_id": user_id,
                },
                created_by_user_id=user_id,
                started_at=utcnow(),
                current_phase="boot",
                current_code="task_created",
                current_message="精修任务已创建…",
                last_event_seq=1,
            )
            session.add(task)
            await session.flush()
            if task.root_task_id is None:
                task.root_task_id = task.id
            session.add(
                GenerationTaskEvent(
                    task_id=task.id,
                    seq=1,
                    event_name="progress",
                    payload={"phase": "boot", "code": "task_created", "message": "精修任务已创建…"},
                )
            )
            await session.commit()
            return str(task.id)

    async def start_script_generation(
        self,
        *,
        world_id: str,
        outline: str = "",
        user_id: str,
    ) -> tuple[str, str]:
        async with self.session_factory() as session:
            await self._acquire_generation_task_limit_lock(session, user_id)
            await self._enforce_generation_task_limit(session, user_id)
            draft = ScriptDraft(world_id=world_id, payload=self.normalize_script_payload({}), created_by_user_id=user_id)
            session.add(draft)
            await session.flush()
            task = GenerationTask(
                kind="script",
                draft_type="script_draft",
                draft_id=draft.id,
                request_payload={
                    "world_id": world_id,
                    "outline": outline,
                    "user_id": user_id,
                },
                created_by_user_id=user_id,
                started_at=utcnow(),
                current_phase="boot",
                current_code="task_created",
                current_message="生成任务已创建，正在准备创作会话…",
                last_event_seq=1,
            )
            session.add(task)
            await session.flush()
            session.add(
                GenerationTaskEvent(
                    task_id=task.id,
                    seq=1,
                    event_name="progress",
                    payload={
                        "phase": "boot",
                        "code": "task_created",
                        "message": "生成任务已创建，正在准备创作会话…",
                    },
                )
            )
            await session.commit()
            return str(draft.id), str(task.id)

    async def _acquire_generation_task_limit_lock(self, session: AsyncSession, user_id: str) -> None:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"generation-task-limit:{user_id}"},
        )

    async def _enforce_generation_task_limit(self, session: AsyncSession, user_id: str) -> None:
        # BUGS #17 — reap stale tasks before counting so a crashed worker
        # doesn't permanently consume a slot.
        await self._reap_stale_tasks(session, user_id=user_id)
        active_count = (
            await session.execute(
                select(func.count())
                .select_from(GenerationTask)
                .where(
                    GenerationTask.status.in_(ACTIVE_GENERATION_TASK_STATUSES),
                    GenerationTask.created_by_user_id == user_id,
                )
            )
        ).scalar_one()
        limit = _active_task_limit_per_user()
        if active_count >= limit:
            raise GenerationTaskLimitExceeded(active_count=active_count, limit=limit)

    async def _reap_stale_tasks(self, session: AsyncSession, *, user_id: str) -> int:
        """Mark zombie tasks as failed. Returns count of reaped tasks.

        Scoped to a single user (called from per-user quota path) — keeps the
        write small and cheap. A future cron can call the same with user_id=None
        for global cleanup.
        """
        from datetime import timedelta

        cutoff = utcnow() - timedelta(seconds=STALE_TASK_AFTER_SECONDS)
        stale = (
            await session.execute(
                select(GenerationTask).where(
                    GenerationTask.status.in_(ACTIVE_GENERATION_TASK_STATUSES),
                    GenerationTask.created_by_user_id == user_id,
                    GenerationTask.updated_at < cutoff,
                )
            )
        ).scalars().all()
        if not stale:
            return 0
        now = utcnow()
        for task in stale:
            task.status = "failed"
            task.error_message = (
                task.error_message
                or f"reaped: no heartbeat for ≥ {STALE_TASK_AFTER_SECONDS // 60} min (worker presumed dead)"
            )
            task.finished_at = now
            logger.warning(
                "generation_task.reaped_stale",
                task_id=str(task.id),
                user_id=user_id,
                kind=task.kind,
                stale_seconds=(now - task.updated_at).total_seconds(),
            )
        await session.flush()
        return len(stale)

    def launch_world_generation(self, task_id: str) -> None:
        self._launch(self._run_world_generation(task_id))

    def launch_script_generation(self, task_id: str) -> None:
        self._launch(self._run_script_generation(task_id))

    def launch_world_refine(self, task_id: str) -> None:
        self._launch(self._run_world_refine(task_id))

    async def request_world_quality(self, task_id: str) -> str | None:
        """Durably enqueue quality for the draft's current payload revision."""
        from services.world_quality_scorer import WorldQualityScorer

        job_id = await WorldQualityScorer(self.session_factory, None).enqueue(task_id)
        if job_id is None:
            return None
        base_agent = await asyncio.wait_for(
            _resolve_factory_result(self.world_creator_factory()), timeout=30.0
        )
        self._launch(self._score_world_quality(job_id, getattr(base_agent, "llm", None)))
        return job_id

    async def get_task(self, task_id: str) -> GenerationTask | None:
        async with self.session_factory() as session:
            return await session.get(GenerationTask, task_id)

    async def get_latest_task_for_draft(self, *, draft_type: str, draft_id: str) -> GenerationTask | None:
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(GenerationTask)
                    .where(GenerationTask.draft_type == draft_type, GenerationTask.draft_id == draft_id)
                    .order_by(GenerationTask.created_at.desc())
                )
            ).scalars().first()

    async def list_events(self, task_id: str, *, after_seq: int = 0) -> list[GenerationTaskEvent]:
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(GenerationTaskEvent)
                    .where(GenerationTaskEvent.task_id == task_id, GenerationTaskEvent.seq > after_seq)
                    .order_by(GenerationTaskEvent.seq.asc())
                )
            ).scalars().all()

    async def stream_task_events(
        self,
        task_id: str,
        *,
        after_seq: int = 0,
        poll_interval: float = 0.25,
    ) -> AsyncIterator[dict]:
        last_seq = after_seq
        while True:
            async with self.session_factory() as session:
                task = await session.get(GenerationTask, task_id)
                if not task:
                    yield {"event": "error", "payload": {"message": "生成任务不存在"}, "seq": last_seq}
                    yield {"event": "done", "payload": {}, "seq": last_seq}
                    return

                rows = (
                    await session.execute(
                        select(GenerationTaskEvent)
                        .where(GenerationTaskEvent.task_id == task_id, GenerationTaskEvent.seq > last_seq)
                        .order_by(GenerationTaskEvent.seq.asc())
                    )
                ).scalars().all()
                terminal = task.status in TERMINAL_TASK_STATUSES
                last_event_seq = task.last_event_seq

            for row in rows:
                last_seq = row.seq
                yield {"event": row.event_name, "payload": row.payload, "seq": row.seq}

            if terminal and last_seq >= last_event_seq:
                return

            await asyncio.sleep(poll_interval)

    def _launch(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._running_tasks.add(task)

        def _cleanup(done: asyncio.Task) -> None:
            self._running_tasks.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                logger.exception("generation_background_task_failed")

        task.add_done_callback(_cleanup)

    async def _score_world_quality(self, job_id: str, llm_router: Any) -> None:
        """Execute a job whose pending row was already committed durably."""
        from services.world_quality_scorer import WorldQualityScorer

        scorer = WorldQualityScorer(self.session_factory, llm_router)
        await scorer.run_job(job_id, run_soft=llm_router is not None)

    async def _enqueue_world_quality(self, task_id: str, llm_router: Any) -> str | None:
        from services.world_quality_scorer import WorldQualityScorer

        scorer = WorldQualityScorer(self.session_factory, llm_router)
        job_id = await scorer.enqueue(task_id)
        if job_id:
            self._launch(self._score_world_quality(job_id, llm_router))
        return job_id

    async def _carry_forward_quality(self, draft_id: str, task_id: str) -> None:
        """精修后不重新打分，把精修前最近一次质量判定原样复制到当前（新）版本。

        质量门只认"精确匹配当前 payload_revision/hash 且 status∈{passed,waived}"的分。
        精修 bump 了版本，若不处理旧分不再匹配 → 卡 stale 发不出去。judge 有 run-to-run
        方差，真去重打分会把生成时已 passed 的稿子抖成 needs_review。故沿用生成结论：
        找当前版本以外最近的一条分，复制成当前版本的一条 carried 分，并同步 draft.quality_status。
        找不到历史分（理论上不该发生）则保持 stale，走正常人工复核。
        """
        from models.world_quality_score import WorldQualityScore

        async with self.session_factory() as session:
            draft = await session.get(WorldDraft, draft_id)
            if draft is None or not draft.payload_hash:
                return
            prev = (
                await session.execute(
                    select(WorldQualityScore)
                    .where(WorldQualityScore.draft_id == draft_id)
                    .where(
                        or_(
                            WorldQualityScore.payload_revision != draft.payload_revision,
                            func.coalesce(WorldQualityScore.payload_hash, "") != draft.payload_hash,
                        )
                    )
                    .order_by(WorldQualityScore.scored_at.desc())
                )
            ).scalars().first()
            if prev is None:
                return
            carried = WorldQualityScore(
                task_id=task_id,
                draft_id=draft_id,
                kind=prev.kind,
                status=prev.status,
                payload_revision=draft.payload_revision,
                payload_hash=draft.payload_hash,
                character_count=prev.character_count,
                playable_count=prev.playable_count,
                must_have_total=prev.must_have_total,
                must_have_covered=prev.must_have_covered,
                events_count=prev.events_count,
                shared_events_count=prev.shared_events_count,
                structure_score=prev.structure_score,
                soft_ip_consistency=prev.soft_ip_consistency,
                soft_collision=prev.soft_collision,
                soft_tension=prev.soft_tension,
                soft_summary=prev.soft_summary,
                backfill_count=prev.backfill_count,
                prune_count=prev.prune_count,
                soft_warning_count=prev.soft_warning_count,
                overall_score=prev.overall_score,
                blocking_flags=prev.blocking_flags,
                shippable=prev.shippable,
                detail={"carried_from_revision": prev.payload_revision, "reason": "refine_no_rescore"},
                finished_at=utcnow(),
            )
            session.add(carried)
            draft.quality_status = prev.status
            await session.commit()

    async def _run_world_generation(self, task_id: str) -> None:
        """AOP wrapper: attribute every nested LLM/image call to this task.

        The actual generation lives in ``_run_world_generation_impl`` —
        this thin shim only manages the ``UsageContext`` lifecycle so
        cost recording works without re-indenting the entire body.
        """
        user_id = await self._load_task_user_id(task_id)
        allowed, hold_id = await self._credit_reserve(user_id, "world", task_id)
        if not allowed:
            await self._record_event(
                task_id,
                {"type": "error", "message": "积分不足", "phase": "general", "code": "credits_insufficient"},
            )
            await self._record_event(task_id, {"type": "done"})
            return
        token = push_usage_context(
            purpose="world_gen",
            task_id=str(task_id),
            user_id=user_id,
        )
        with usage_accumulator() as acc:
            try:
                await self._run_world_generation_impl(task_id)
            finally:
                pop_usage_context(token)
                await self._credit_settle(user_id, hold_id, acc, task_id)

    async def _run_world_generation_impl(self, task_id: str) -> None:
        from services.world_creator_agent_v2 import WorldCreatorAgentV2

        logger.info("world_generation_started", task_id=task_id)
        request = await self._get_request_payload(task_id)
        if not request:
            await self._record_event(task_id, {"type": "error", "message": "生成任务不存在", "phase": "general", "code": "task_missing"})
            await self._record_event(task_id, {"type": "done"})
            return

        await self._record_event(
            task_id,
            {"type": "progress", "phase": "boot", "code": "session_started", "message": "已收到生成请求，正在建立创作会话…"},
        )
        await self._mark_task_running(task_id)
        logger.info("world_generation_boot_marked_running", task_id=task_id)

        # Outer try: any exception from factory / v2 wrap / phase_b prep / create_world
        # must surface to the frontend via error+done events. Without this wrapper,
        # failures (e.g. slot-bound provider with missing API-key env var) bubble up to
        # _launch._cleanup which only logs — the task then stays "running" forever and
        # the SSE stream never terminates, leaving the UI stuck at "session_started".
        factory_ready = False
        try:
            # Factory does pure DB lookups + provider constructors — should be sub-second.
            # If it hangs (e.g. DB connection pool exhausted, asyncpg deadlock), the
            # 30s timeout converts the hang into a surfaced error event instead of
            # leaving the task in "running" forever.
            logger.info("world_generation_factory_started", task_id=task_id)
            base_agent = await asyncio.wait_for(
                _resolve_factory_result(self.world_creator_factory()),
                timeout=30.0,
            )
            factory_ready = True
            logger.info(
                "world_generation_factory_ready",
                task_id=task_id,
                agent_type=type(base_agent).__name__,
            )

            phase = (request.get("phase") or "").strip() or None

            # Phase A: run Stage 0 (IP recognition) ONLY. Mark task succeeded and
            # let the front-end show the recognition card. Continuation is via the
            # `/world-drafts/{id}/continue-generation` endpoint, which creates a
            # separate phase_b task.
            if phase == PHASE_A:
                # PHASE_A is "Stage 0 only" — its product is the IP recognition
                # result stored in intermediate_state, not anything that goes
                # into draft.payload. We still emit a `result` event with an
                # empty payload so the frontend's stream consumer flips
                # `didComplete=true` and navigates to the draft detail page,
                # which then renders the IPRecognitionCard from
                # intermediate_state. Without this, PHASE_A only sent
                # progress + done, the page never navigated, and the user was
                # left staring at "已收到生成请求…" forever.
                async def _emit_ip_recognition_fallback(reason: str) -> None:
                    """Synthesize an original/0.0 IPRecognition and emit ip_recognition
                    completed + result + done so the frontend can render the card and continue."""
                    fallback_rec_dict: dict = {
                        "kind": "original",
                        "confidence": 0.0,
                        "ip_name": None,
                        "ip_type": None,
                        "one_liner": None,
                        "source_hints": [],
                    }
                    await self.record_intermediate(task_id, phase="ip_recognition", snapshot=fallback_rec_dict)
                    await self._record_event(
                        task_id,
                        {
                            "type": "progress",
                            "phase": "ip_recognition",
                            "code": "completed",
                            "message": reason,
                            "meta": fallback_rec_dict,
                        },
                    )
                    await self._record_event(task_id, {"type": "result"})
                    await self._record_event(task_id, {"type": "done"})

                try:
                    from services.ip_recognizer import build_recognizer_llm, recognize_ip

                    description = request.get("description", "")
                    llm_router = getattr(base_agent, "llm", None)
                    tavily = getattr(base_agent, "tavily", None)
                    # 识别步走 ip_recognition 槽（admin 可管，默认 grok-chat-fast 联网）；
                    # 未绑/grok 未配置时回退到生成主模型。
                    async with self.session_factory() as _rec_db:
                        recognizer_llm = await build_recognizer_llm(_rec_db, fallback=llm_router)

                    # No LLM router means we can't call the recognizer — degrade
                    # gracefully instead of crashing with AttributeError.
                    if recognizer_llm is None:
                        logger.warning("phase_a_no_llm_router", task_id=str(task_id))
                        await _emit_ip_recognition_fallback("未配置 LLM，按原创处理")
                        return

                    await self._record_event(
                        task_id,
                        {
                            "type": "progress",
                            "phase": "ip_recognition",
                            "code": "started",
                            "message": "正在识别是否指向某个已知 IP…",
                        },
                    )
                    rec = await recognize_ip(description, llm_router=recognizer_llm, tavily=tavily)
                    rec_dict = rec.model_dump()
                    await self.record_intermediate(task_id, phase="ip_recognition", snapshot=rec_dict)
                    await self._record_event(
                        task_id,
                        {
                            "type": "progress",
                            "phase": "ip_recognition",
                            "code": "completed",
                            "message": "IP 识别完成",
                            "meta": rec_dict,
                        },
                    )
                    await self._record_event(task_id, {"type": "result"})
                    await self._record_event(task_id, {"type": "done"})
                except Exception as exc:  # noqa: BLE001
                    # Recognizer failure is non-fatal: emit a fallback original/0.0
                    # so the frontend can still reach /continue-generation. We only
                    # call this for failures inside recognize_ip itself — earlier
                    # failures (factory, etc.) are caught by the outer try below.
                    logger.warning("phase_a_recognize_failed", error=str(exc), task_id=str(task_id))
                    await _emit_ip_recognition_fallback("IP 识别失败，按原创处理")
                return

            if _can_wrap_v2(base_agent):
                agent = WorldCreatorAgentV2(
                    llm=base_agent.llm,
                    image_gen=base_agent.image_gen,
                    broker=base_agent.research_broker,
                    task_service=self,
                    task_id=task_id,
                    session_factory=self.session_factory,
                )
            else:
                agent = base_agent

            await self._record_event(
                task_id,
                {"type": "progress", "phase": "boot", "code": "agent_ready", "message": "生成引擎已接入，马上开始拆解任务…"},
            )

            # Phase B: feed pre-existing IP recognition + chosen fidelity_mode
            # through to the agent so downstream stages (T7/T8) can use them.
            extra_kwargs: dict[str, Any] = {}
            if phase == PHASE_B:
                pre_rec_dict = request.get("ip_recognition")
                pre_recognition = None
                if isinstance(pre_rec_dict, dict):
                    try:
                        from services.ip_recognizer import IPRecognition

                        pre_recognition = IPRecognition(**pre_rec_dict)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "phase_b_ip_recognition_parse_failed",
                            task_id=task_id,
                            error=str(exc),
                        )
                        pre_recognition = None
                fidelity_mode = request.get("fidelity_mode") or "none"
                # Resolve draft_id so the IP research stage (T7) can persist its
                # pack with the right ip_knowledge_packs.draft_id FK.
                phase_b_task = await self.get_task(task_id)
                draft_id = str(phase_b_task.draft_id) if phase_b_task else None
                extra_kwargs = {
                    "skip_ip_recognition": True,
                    "pre_recognition": pre_recognition,
                    "fidelity_mode": fidelity_mode,
                    "draft_id": draft_id,
                }

            async for event in agent.create_world(
                request.get("description", ""),
                request.get("genre", ""),
                request.get("era", ""),
                **extra_kwargs,
            ):
                await self._record_event(task_id, event)

            # 异步质量打分（plan 2026-06-24）：done 已记录、draft 已落库后 fire-and-forget。
            # 不阻塞生成、失败不影响 draft。PHASE_A 只做 IP 识别、无 payload，跳过。
            if phase != PHASE_A:
                await self._enqueue_world_quality(task_id, getattr(agent, "llm", None))
        except asyncio.TimeoutError:
            logger.exception("world_generation_task_timed_out", task_id=task_id)
            code = "generation_call_timeout" if factory_ready else "factory_timeout"
            message = (
                "模型单次生成超过 10 分钟，已停止本次任务，请重试"
                if factory_ready
                else "创作会话建立超时（30s 内未完成 LLM/Provider 初始化），请检查模型槽位绑定与 API key 是否配置正确"
            )
            await self._record_event(
                task_id,
                {"type": "error", "message": message, "phase": "general", "code": code},
            )
            await self._record_event(task_id, {"type": "done"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("world_generation_task_failed", task_id=task_id)
            message = str(exc) or f"{type(exc).__name__}: 生成任务异常退出"
            await self._record_event(
                task_id,
                {"type": "error", "message": message, "phase": "general", "code": "generation_failed"},
            )
            await self._record_event(task_id, {"type": "done"})

    async def _run_world_refine(self, task_id: str) -> None:
        """AOP wrapper for the refine executor — attributes nested LLM cost to this task."""
        user_id = await self._load_task_user_id(task_id)
        # purpose 必须是 usage_context 白名单里的值；精修归入 world_gen 计成本。
        token = push_usage_context(purpose="world_gen", task_id=str(task_id), user_id=user_id)
        with usage_accumulator():
            try:
                await self._run_world_refine_impl(task_id)
            finally:
                pop_usage_context(token)

    async def _run_world_refine_impl(self, task_id: str) -> None:
        from services.world_gen_refiner import recheck_and_refresh, refine_world_payload

        request = await self._get_request_payload(task_id)
        task = await self.get_task(task_id)
        if not request or task is None:
            await self._record_event(task_id, {"type": "error", "message": "精修任务不存在", "phase": "refine", "code": "task_missing"})
            await self._record_event(task_id, {"type": "done"})
            return
        draft_id = str(task.draft_id)
        targets = list(request.get("targets") or [])

        await self._mark_task_running(task_id)
        await self._record_event(
            task_id,
            {"type": "progress", "phase": "refine", "code": "started", "message": "开始精修…"},
        )
        try:
            async with self.session_factory() as session:
                draft = await session.get(WorldDraft, draft_id)
                if draft is None:
                    raise ValueError("draft not found")
                payload = dict(draft.payload or {})

            # 撤销快照：精修前的 payload 存进本任务 intermediate_state
            await self.record_intermediate(task_id, phase="pre_refine_snapshot", snapshot={"payload": payload})

            base_agent = await asyncio.wait_for(
                _resolve_factory_result(self.world_creator_factory()), timeout=30.0
            )
            llm = getattr(base_agent, "llm", None)

            async def _progress(code: str, message: str) -> None:
                await self._record_event(
                    task_id, {"type": "progress", "phase": "refine", "code": code, "message": message}
                )

            # recheck=False：精修主体（事件+小传）跑完先出结果，复检退后台。
            result = await refine_world_payload(
                payload, targets=targets, llm_router=llm, progress=_progress, recheck=False
            )

            if result.changed:
                async with self.session_factory() as session:
                    draft = await session.get(WorldDraft, draft_id)
                    if draft is not None:
                        self._write_versioned_world_payload(draft, result.payload)
                        await session.commit()

            # 先出结果（不含复检）：用户 ~3 分钟就能看到改动，不必干等复检那 1~2 分钟。
            # 不发 result 事件（避免触发世界落库的 _apply_result_payload）——前端收 completed 即可。
            await self._record_event(
                task_id,
                {
                    "type": "progress",
                    "phase": "refine",
                    "code": "completed",
                    "message": "精修完成" if result.changed else "精修未产生改动",
                    "meta": result.as_dict(),
                },
            )

            # 复检退后台：仍在本任务流内跑（编辑保持锁定），但用户已先看到改动。
            # 复检刷新 quality_warnings 后再写回一次 + 重新打分，最后发 recheck_done。
            if result.changed:
                rechecked = await recheck_and_refresh(
                    result.payload, changed=True, llm_router=llm, progress=_progress
                )
                async with self.session_factory() as session:
                    draft = await session.get(WorldDraft, draft_id)
                    if draft is not None:
                        self._write_versioned_world_payload(draft, result.payload)
                        await session.commit()
                # 精修不重新打分：把生成时那次质量判定原样带到新版本，让质量门沿用生成结论
                # （passed 保持 passed）。judge 有 run-to-run 方差，重打分会把已 passed 的稿子
                # 抖成 needs_review；精修是按需的锦上添花、且有自己的复检，不该反过来卡发布。
                await self._carry_forward_quality(draft_id, task_id)
                await self._record_event(
                    task_id,
                    {
                        "type": "progress",
                        "phase": "refine",
                        "code": "recheck_done",
                        "message": "复检完成",
                        "meta": {"rechecked": [f.as_dict() for f in rechecked]},
                    },
                )

            await self._record_event(task_id, {"type": "done"})
        except asyncio.TimeoutError:
            logger.exception("world_refine_timed_out", task_id=task_id)
            await self._record_event(task_id, {"type": "error", "message": "精修超时，请重试", "phase": "refine", "code": "refine_timeout"})
            await self._record_event(task_id, {"type": "done"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("world_refine_failed", task_id=task_id)
            await self._record_event(
                task_id,
                {"type": "error", "message": str(exc) or "精修异常退出", "phase": "refine", "code": "refine_failed"},
            )
            await self._record_event(task_id, {"type": "done"})

    def _write_versioned_world_payload(self, draft: WorldDraft, payload: dict) -> None:
        """写回 draft.payload 并 bump revision/hash，标记质量为 stale（需重新打分才能发布）。"""
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        draft.payload = payload
        flag_modified(draft, "payload")
        if draft.payload_hash != payload_hash:
            draft.payload_revision = int(draft.payload_revision or 0) + 1
            draft.payload_hash = payload_hash
            draft.quality_status = "stale"

    async def _run_script_generation(self, task_id: str) -> None:
        """AOP wrapper — see ``_run_world_generation`` for the rationale."""
        user_id = await self._load_task_user_id(task_id)
        allowed, hold_id = await self._credit_reserve(user_id, "script", task_id)
        if not allowed:
            await self._record_event(
                task_id,
                {"type": "error", "message": "积分不足", "phase": "general", "code": "credits_insufficient"},
            )
            await self._record_event(task_id, {"type": "done"})
            return
        token = push_usage_context(
            purpose="script_gen",
            task_id=str(task_id),
            user_id=user_id,
        )
        with usage_accumulator() as acc:
            try:
                await self._run_script_generation_impl(task_id)
            finally:
                pop_usage_context(token)
                await self._credit_settle(user_id, hold_id, acc, task_id)

    async def _run_script_generation_impl(self, task_id: str) -> None:
        from services.world_creator_agent_v2 import WorldCreatorAgentV2

        request = await self._get_request_payload(task_id)
        if not request:
            await self._record_event(task_id, {"type": "error", "message": "生成任务不存在", "phase": "general", "code": "task_missing"})
            await self._record_event(task_id, {"type": "done"})
            return

        await self._record_event(
            task_id,
            {"type": "progress", "phase": "boot", "code": "session_started", "message": "已收到生成请求，正在建立创作会话…"},
        )
        await self._mark_task_running(task_id)
        try:
            await self._record_event(
                task_id,
                {"type": "progress", "phase": "boot", "code": "loading_world_context", "message": "先把这个世界的设定和角色资料读进来…"},
            )
            async with self.session_factory() as session:
                world_data = await self._build_script_world_data(session, str(request.get("world_id", "")))
            await self._record_event(
                task_id,
                {
                    "type": "progress",
                    "phase": "boot",
                    "code": "world_context_ready",
                    "message": "世界资料已就绪",
                    "meta": {
                        "world_name": world_data.get("name", ""),
                        "character_count": len(world_data.get("world_characters", [])),
                        "script_count": len(world_data.get("existing_scripts", [])),
                    },
                },
            )
            base_agent = self.world_creator_factory()
            if inspect.isawaitable(base_agent):
                base_agent = await base_agent

            if _can_wrap_v2(base_agent):
                agent = WorldCreatorAgentV2(
                    llm=base_agent.llm,
                    image_gen=base_agent.image_gen,
                    broker=base_agent.research_broker,
                    task_service=self,
                    task_id=task_id,
                    session_factory=self.session_factory,
                )
            else:
                agent = base_agent

            await self._record_event(
                task_id,
                {"type": "progress", "phase": "boot", "code": "agent_ready", "message": "生成引擎已接入，马上开始拆解任务…"},
            )

            outline = str(request.get("outline", "") or "")
            # outline 为空 / 支撑不足时，借 grok 联网选题挑「下一个最合适的剧本」，
            # 自动取 Top1 当 outline 喂给下游 DeepSeek 创作（永不阻断：失败则退回空 outline）。
            if len(outline.strip()) < _OUTLINE_AUTO_RECOMMEND_THRESHOLD:
                await self._record_event(
                    task_id,
                    {"type": "progress", "phase": "boot", "code": "recommending_premise",
                     "message": "没填大纲，先让 grok 联网挑一个最合适的下一个剧本切入点…"},
                )
                try:
                    from services.script_premise_recommender import recommend_script_premises
                    premises = await recommend_script_premises(
                        world_data=world_data,
                        broker=getattr(base_agent, "research_broker", None),
                        llm_router=getattr(base_agent, "llm", None),
                        count=1,
                    )
                    if premises and premises[0].to_outline():
                        outline = premises[0].to_outline()
                        await self._record_event(
                            task_id,
                            {"type": "progress", "phase": "boot", "code": "premise_selected",
                             "message": f"已选定切入点：{premises[0].title or premises[0].theme}",
                             "meta": {"title": premises[0].title, "theme": premises[0].theme}},
                        )
                except Exception:  # noqa: BLE001
                    logger.warning("script_premise_auto_recommend_failed", task_id=task_id, exc_info=True)

            async for event in agent.create_script(world_data, outline):
                await self._record_event(task_id, event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("script_generation_task_failed", task_id=task_id)
            await self._record_event(
                task_id,
                {"type": "error", "message": str(exc), "phase": "general", "code": "generation_failed"},
            )
            await self._record_event(task_id, {"type": "done"})

    async def _get_request_payload(self, task_id: str) -> dict | None:
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, task_id)
            if not task:
                return None
            return task.request_payload or {}

    async def _load_task_user_id(self, task_id: str) -> str | None:
        """Read ``created_by_user_id`` for the task — used to stamp the
        ambient ``UsageContext`` so cost can be attributed per-user."""
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, task_id)
            if not task:
                return None
            return str(task.created_by_user_id) if task.created_by_user_id else None

    async def _credit_reserve(
        self, user_id: str | None, action: str, task_id: str
    ) -> tuple[bool, str | None]:
        """L3 reserve for a generation task. Returns ``(allowed, hold_id)``.

        Insufficient balance blocks the task. A credit-subsystem error follows
        ``gate_fail_mode`` (default open) — it must not block creation.
        """
        if not user_id:
            return True, None
        from services import credit_service

        try:
            async with self.session_factory() as cdb:
                hold_id = await credit_service.reserve(
                    cdb, user_id, action=action, ref_type="task", ref_id=str(task_id)
                )
                return True, hold_id
        except credit_service.InsufficientCredits:
            return False, None
        except Exception:  # noqa: BLE001
            logger.warning("credit.gen_gate_failed", exc_info=True)
            try:
                async with self.session_factory() as cdb:
                    config = await credit_service.get_config(cdb)
                    return (config.gate_fail_mode != "safe"), None
            except Exception:  # noqa: BLE001 — fully broken => fail open
                return True, None

    async def _credit_settle(
        self, user_id: str | None, hold_id: str | None, accumulator, task_id: str
    ) -> None:
        """Settle a generation task's reservation. delivered = task succeeded
        (produced an artifact); a fully-failed task is free (design §5.2)."""
        if not user_id or not hold_id:
            return
        from services import credit_service

        try:
            async with self.session_factory() as cdb:
                task = await cdb.get(GenerationTask, task_id)
                delivered = bool(task and task.status == "succeeded")
                await credit_service.settle_hold(cdb, hold_id, accumulator, delivered=delivered)
        except Exception:  # noqa: BLE001 — fail open
            logger.warning("credit.gen_settle_failed", exc_info=True)

    async def _mark_task_running(self, task_id: str) -> None:
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, task_id)
            if not task:
                return
            if task.status == "pending":
                task.status = "running"
                task.started_at = task.started_at or utcnow()
                await session.commit()

    async def _record_event(self, task_id: str, event: dict) -> None:
        """Append an event row + bump task.last_event_seq atomically.

        The INSERT into generation_task_events and the UPDATE on
        generation_tasks (last_event_seq + status fields) MUST be in the same
        transaction. On any failure we explicitly roll back and re-raise so
        the caller observes the original error and the task row keeps its old
        seq (no event row, no seq bump).
        """
        event_name = str(event.get("type", "")).strip() or "progress"
        payload = {key: value for key, value in event.items() if key != "type"}

        async with self.session_factory() as session:
            task = await session.get(GenerationTask, task_id)
            if not task:
                return

            try:
                next_seq = int(task.last_event_seq or 0) + 1
                session.add(
                    GenerationTaskEvent(
                        task_id=task.id,
                        seq=next_seq,
                        event_name=event_name,
                        payload=payload,
                    )
                )
                task.last_event_seq = next_seq
                task.updated_at = utcnow()

                if event_name in {"progress", "warning"}:
                    task.current_phase = str(payload.get("phase", "") or "")
                    task.current_code = str(payload.get("code", "") or "")
                    task.current_message = str(payload.get("message", "") or "")
                elif event_name == "error":
                    task.status = "failed"
                    task.error_message = str(payload.get("message", "") or "生成失败")
                    task.finished_at = utcnow()
                elif event_name == "result":
                    await self._apply_result_payload(session, task, payload)
                elif event_name == "done" and task.status not in {"failed", "cancelled"}:
                    task.status = "succeeded"
                    task.finished_at = task.finished_at or utcnow()

                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "generation_task_record_event_failed",
                    task_id=task_id,
                    event_name=event_name,
                )
                raise

    async def record_intermediate(self, task_id: str, phase: str, snapshot: dict) -> None:
        """Snapshot phase 产物到 intermediate_state JSON 字段（merge，不覆盖其他 phase）。

        单事务 + with_for_update 防止并发竞态。失败 raise，调用方决定要不要 retry。
        """
        async with self.session_factory() as session:
            try:
                stmt = (
                    select(GenerationTask)
                    .where(GenerationTask.id == task_id)
                    .with_for_update()
                )
                task = (await session.execute(stmt)).scalar_one()
                current = dict(task.intermediate_state or {})
                current[phase] = snapshot
                task.intermediate_state = current
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _apply_result_payload(self, session: AsyncSession, task: GenerationTask, payload: dict) -> None:
        # We've seen the JSON column silently keep its old value across sessions
        # even after rebinding `draft.payload = new_dict` (only 14 of 21 expected
        # top-level keys land in DB). `flag_modified` + explicit flush forces the
        # UPDATE; the key-count log gives us evidence whether the issue recurs.
        if task.draft_type == "world_draft":
            draft = await session.get(WorldDraft, task.draft_id)
            if draft:
                before_keys = len(draft.payload or {})
                normalized = self.normalize_world_payload(payload)
                canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                next_revision = int(draft.payload_revision or 0) + 1
                draft.payload = normalized
                draft.payload_revision = next_revision
                draft.payload_hash = payload_hash
                draft.quality_status = "pending"
                task.payload_revision = next_revision
                task.payload_hash = payload_hash
                flag_modified(draft, "payload")
                await session.flush()
                logger.info(
                    "apply_result_payload.world_draft",
                    task_id=str(task.id),
                    draft_id=str(draft.id),
                    payload_keys_in=len(payload),
                    payload_keys_normalized=len(normalized),
                    payload_keys_before=before_keys,
                    has_character_images=bool(normalized.get("character_images")),
                )
        elif task.draft_type == "script_draft":
            draft = await session.get(ScriptDraft, task.draft_id)
            if draft:
                before_keys = len(draft.payload or {})
                normalized = self.normalize_script_payload(payload)
                draft.payload = normalized
                flag_modified(draft, "payload")
                await session.flush()
                logger.info(
                    "apply_result_payload.script_draft",
                    task_id=str(task.id),
                    draft_id=str(draft.id),
                    payload_keys_in=len(payload),
                    payload_keys_normalized=len(normalized),
                    payload_keys_before=before_keys,
                )

    async def build_script_world_data(self, session: AsyncSession, world_id: str) -> dict:
        """Public wrapper so the premise-suggestion endpoint can reuse the exact
        same world payload (shared_events + existing_scripts + chars) the worker
        feeds into script generation."""
        return await self._build_script_world_data(session, world_id)

    async def _build_script_world_data(self, session: AsyncSession, world_id: str) -> dict:
        world = await session.get(World, world_id)
        if not world:
            raise RuntimeError("世界不存在")

        world_chars = (
            await session.execute(select(WorldCharacter).where(WorldCharacter.world_id == world.id))
        ).scalars().all()
        existing_scripts = (
            await session.execute(
                select(Script)
                .where(Script.world_id == world.id, Script.is_published.is_(True))
                .order_by(Script.created_at.desc())
            )
        ).scalars().all()

        # Inherit the parent world's IP knowledge pack. World gen backfills
        # ip_knowledge_packs.world_id at publish time; for legacy worlds without
        # that backfill this returns None and downstream falls back to ip_canon.
        from models.ip_knowledge_pack import IPKnowledgePack as _IPK
        ip_pack_row = (
            await session.execute(
                select(_IPK).where(_IPK.world_id == world.id).limit(1)
            )
        ).scalar_one_or_none()
        ip_knowledge_pack = ip_pack_row.pack_json if ip_pack_row else None

        return {
            "id": str(world.id),
            "name": world.name,
            "description": world.description,
            "genre": world.genre,
            "era": world.era,
            "base_setting": world.base_setting,
            "locations": world.locations_data or [],
            "ip_knowledge_pack": ip_knowledge_pack,
            "world_characters": [
                {
                    "id": str(wc.id),
                    "name": wc.name,
                    "personality": wc.personality,
                    "secret": wc.secret,
                    "knowledge": wc.knowledge or [],
                    "schedule": wc.schedule or {},
                    "initial_location": wc.initial_location,
                    "playable": wc.playable,
                    # v2 compat: map playable flag to is_image_target so
                    # WorldCreatorAgentV2.create_script can select playable chars
                    # without a dedicated column.
                    "is_image_target": wc.playable,
                    "role_tag": "",
                }
                for wc in world_chars
            ],
            "existing_scripts": [_script_reference_summary_from_model(script) for script in existing_scripts],
            # v2 fields — may be None for older worlds; create_script handles None gracefully
            "lore_pack": world.lore_pack,
            "visual_style": (world.lore_pack or {}).get("visual_style") if isinstance(world.lore_pack, dict) else None,
            "shared_events": world.shared_events,
            "research_pack": None,  # v1 worlds don't store research_pack; script v2 re-runs research
        }
