"""生成完成后的异步质量打分器。

plan: docs/plans/2026-06-24-generation-agentic-loop.md
done 之后 fire-and-forget 调用 score_task —— 不阻塞生成,失败也不影响 draft。
硬指标(Python,0 成本) + 软分(LLM,默认跑) + 安全网触发量,一并落 world_quality_scores。
打分锁定 done 那一刻的 draft.payload 快照,不追后续人工编辑(决策②)。
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.draft import WorldDraft
from models.generation_task import GenerationTask
from models.ip_knowledge_pack import IPKnowledgePack
from models.world_quality_score import WorldQualityScore
from services.generation_rubric import compute_hard_metrics
from services.world_critic_service import score_world_soft

logger = structlog.get_logger(__name__)


class WorldQualityScorer:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], llm_router) -> None:
        self.session_factory = session_factory
        self.llm = llm_router

    async def score_task(self, task_id: str, *, run_soft: bool = True) -> None:
        """对一个已完成的世界生成 task 打分并落库。整体 try/except,绝不向上抛。"""
        try:
            async with self.session_factory() as session:
                task = await session.get(GenerationTask, task_id)
                if not task or task.draft_type != "world_draft":
                    return
                draft = await session.get(WorldDraft, task.draft_id)
                if not draft or not draft.payload:
                    logger.info("quality_score_skipped_no_payload", task_id=task_id)
                    return
                payload = dict(draft.payload)

                pack = (
                    await session.execute(
                        select(IPKnowledgePack).where(IPKnowledgePack.draft_id == task.draft_id)
                    )
                ).scalars().first()
                pack_json = (pack.pack_json if pack else {}) or {}
                must_have = [
                    str(c.get("name"))
                    for c in (pack_json.get("characters") or [])
                    if isinstance(c, dict) and c.get("must_have") and c.get("name")
                ]

            # ---- 硬指标(Python,0 成本)----
            hard = compute_hard_metrics(payload, must_have)

            # ---- 软分(LLM,默认跑;失败返回 None,不阻断)----
            soft = await score_world_soft(payload, pack_json, self.llm) if run_soft else None

            async with self.session_factory() as session:
                row = WorldQualityScore(
                    task_id=task_id,
                    draft_id=str(task.draft_id),
                    kind="world",
                    character_count=hard["character_count"],
                    playable_count=hard["playable_count"],
                    must_have_total=hard["must_have_total"],
                    must_have_covered=hard["must_have_covered"],
                    events_count=hard["events_count"],
                    shared_events_count=hard["shared_events_count"],
                    structure_score=hard["structure_score"],
                    soft_ip_consistency=(soft or {}).get("ip_consistency"),
                    soft_collision=(soft or {}).get("collision"),
                    soft_tension=(soft or {}).get("tension"),
                    soft_summary=(soft or {}).get("summary"),
                    backfill_count=hard["backfill_count"],
                    prune_count=hard["prune_count"],
                    soft_warning_count=hard["soft_warning_count"],
                    overall_score=hard["overall_score"],
                    detail={
                        "hard": hard,
                        "soft": soft,
                        "must_have_names": must_have,
                    },
                )
                session.add(row)
                await session.commit()

            logger.info(
                "quality_score_done",
                task_id=task_id,
                overall=hard["overall_score"],
                must_have=f"{hard['must_have_covered']}/{hard['must_have_total']}",
                backfill=hard["backfill_count"],
                soft_ran=bool(soft),
            )
        except Exception:  # noqa: BLE001
            logger.exception("quality_score_failed", task_id=task_id)
