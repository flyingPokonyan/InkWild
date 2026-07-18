"""Durable, versioned world-quality jobs."""
from __future__ import annotations

import structlog
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.draft import WorldDraft
from models.generation_task import GenerationTask
from models.ip_knowledge_pack import IPKnowledgePack
from models.world_quality_score import WorldQualityScore
from services.generation_rubric import (
    compute_blocking_flags,
    compute_hard_blocking_flags,
    compute_hard_metrics,
)
from services.world_critic_service import score_world_soft
from utils import utcnow

logger = structlog.get_logger(__name__)


class WorldQualityScorer:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], llm_router) -> None:
        self.session_factory = session_factory
        self.llm = llm_router

    async def enqueue(self, task_id: str) -> str | None:
        """Create the pending row transactionally after the draft revision lands."""
        async with self.session_factory() as session:
            task = await session.get(GenerationTask, task_id)
            if not task or task.draft_type != "world_draft" or task.status != "succeeded":
                return None
            draft = await session.get(WorldDraft, task.draft_id)
            if not draft or not draft.payload or not draft.payload_hash:
                return None
            existing = (
                await session.execute(
                    select(WorldQualityScore)
                    .where(
                        WorldQualityScore.task_id == task_id,
                        WorldQualityScore.payload_revision == draft.payload_revision,
                        WorldQualityScore.payload_hash == draft.payload_hash,
                    )
                    .order_by(WorldQualityScore.created_at.desc())
                )
            ).scalars().first()
            if existing and existing.status in {
                "pending", "running", "passed", "needs_review", "waived"
            }:
                return None
            row = WorldQualityScore(
                task_id=task_id,
                draft_id=str(task.draft_id),
                kind="world",
                status="pending",
                payload_revision=int(draft.payload_revision or 0),
                payload_hash=draft.payload_hash,
                shippable=False,
            )
            draft.quality_status = "pending"
            session.add(row)
            await session.commit()
            return str(row.id)

    async def score_task(self, task_id: str, *, run_soft: bool = True) -> None:
        """Compatibility entrypoint: durable enqueue followed by job execution."""
        job_id = await self.enqueue(task_id)
        if job_id:
            await self.run_job(job_id, run_soft=run_soft)

    async def run_job(self, job_id: str, *, run_soft: bool = True) -> None:
        try:
            async with self.session_factory() as session:
                row = (
                    await session.execute(
                        select(WorldQualityScore)
                        .where(WorldQualityScore.id == job_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if row is None or row.status != "pending":
                    return
                row.status = "running"
                row.attempt = int(row.attempt or 0) + 1
                row.started_at = utcnow()
                row.error_message = None
                draft = await session.get(WorldDraft, row.draft_id)
                task = await session.get(GenerationTask, row.task_id)
                if not draft or not task or not draft.payload:
                    raise RuntimeError("quality job draft/task payload missing")
                if draft.payload_revision != row.payload_revision or draft.payload_hash != row.payload_hash:
                    row.status = "stale"
                    row.finished_at = utcnow()
                    await session.commit()
                    return
                draft.quality_status = "running"
                payload = dict(draft.payload)
                world_spec = dict(task.world_spec or {})
                pack = (
                    await session.execute(
                        select(IPKnowledgePack)
                        .where(IPKnowledgePack.draft_id == task.draft_id)
                        .order_by(IPKnowledgePack.created_at.desc())
                    )
                ).scalars().first()
                pack_json = (pack.pack_json if pack else {}) or {}
                must_have = [
                    str(c.get("name"))
                    for c in (pack_json.get("characters") or [])
                    if isinstance(c, dict)
                    and c.get("must_have")
                    and c.get("name")
                    and c.get("in_continuity", True)
                ]
                await session.commit()

            hard = compute_hard_metrics(payload, must_have)
            soft = (
                await score_world_soft(
                    payload,
                    pack_json,
                    self.llm,
                    world_spec=world_spec,
                )
                if run_soft and self.llm
                else None
            )
            blocking_flags, shippable = compute_blocking_flags(soft)
            if run_soft and self.llm is not None and soft is None:
                blocking_flags = list(blocking_flags) + ["quality_judge_unavailable"]
                shippable = False
            hard_blocking_flags = compute_hard_blocking_flags(hard, payload, world_spec)
            blocking_flags = hard_blocking_flags + list(blocking_flags)
            shippable = shippable and not hard_blocking_flags
            strict_ip = world_spec.get("fidelity_mode") == "strict" and bool(world_spec.get("ip_name"))
            if strict_ip and pack is None:
                blocking_flags = list(blocking_flags) + ["strict_ip_pack_missing"]
                shippable = False
            elif pack is not None and not must_have:
                blocking_flags = list(blocking_flags) + ["ip_pack_no_must_have"]
                shippable = False

            async with self.session_factory() as session:
                row = await session.get(WorldQualityScore, job_id)
                draft = await session.get(WorldDraft, row.draft_id) if row else None
                if row is None:
                    return
                row.character_count = hard["character_count"]
                row.playable_count = hard["playable_count"]
                row.must_have_total = hard["must_have_total"]
                row.must_have_covered = hard["must_have_covered"]
                row.events_count = hard["events_count"]
                row.shared_events_count = hard["shared_events_count"]
                row.structure_score = hard["structure_score"]
                row.soft_ip_consistency = (soft or {}).get("ip_consistency")
                row.soft_collision = (soft or {}).get("collision")
                row.soft_tension = (soft or {}).get("tension")
                row.soft_summary = (soft or {}).get("summary")
                row.backfill_count = hard["backfill_count"]
                row.prune_count = hard["prune_count"]
                row.soft_warning_count = hard["soft_warning_count"]
                row.overall_score = hard["overall_score"]
                row.blocking_flags = blocking_flags or None
                row.shippable = shippable
                row.status = "passed" if shippable else "needs_review"
                row.detail = {
                    "hard": hard,
                    "soft": soft,
                    "blocking_flags": blocking_flags,
                    "hard_blocking_flags": hard_blocking_flags,
                    "shippable": shippable,
                    "must_have_names": must_have,
                    "judge_count": (soft or {}).get("judge_count"),
                }
                row.scored_at = utcnow()
                row.finished_at = utcnow()
                if draft and draft.payload_revision == row.payload_revision and draft.payload_hash == row.payload_hash:
                    draft.quality_status = row.status
                await session.commit()
            logger.info("quality_score_done", task_id=row.task_id, status=row.status, shippable=shippable)
        except Exception as exc:  # noqa: BLE001
            logger.exception("quality_score_failed", job_id=job_id)
            async with self.session_factory() as session:
                row = await session.get(WorldQualityScore, job_id)
                if row:
                    row.status = "failed"
                    row.error_message = str(exc)[:2000]
                    row.finished_at = utcnow()
                    draft = await session.get(WorldDraft, row.draft_id)
                    if draft and draft.payload_revision == row.payload_revision and draft.payload_hash == row.payload_hash:
                        draft.quality_status = "failed"
                    await session.commit()

    async def run_pending(self, *, limit: int = 10) -> int:
        async with self.session_factory() as session:
            await session.execute(
                update(WorldQualityScore)
                .where(
                    WorldQualityScore.status == "running",
                    WorldQualityScore.started_at < utcnow() - timedelta(minutes=30),
                )
                .values(status="pending", error_message="recovered stale running quality job")
            )
            ids = (
                await session.execute(
                    select(WorldQualityScore.id)
                    .where(
                        WorldQualityScore.status == "pending",
                        WorldQualityScore.attempt < 3,
                    )
                    .order_by(WorldQualityScore.created_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            await session.commit()
        for job_id in ids:
            await self.run_job(str(job_id), run_soft=self.llm is not None)
        return len(ids)
