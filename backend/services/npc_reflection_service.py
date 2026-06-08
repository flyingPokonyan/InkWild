"""Phase 1 NPC reflection — long-term per-NPC memory consolidation.

When a NPC accumulates enough new structured memory entries since the last
reflection (default ≥ 5), trigger a cheap LLM call that rewrites the NPC's
inner self-narrative. The summary is loaded into the NPC system prompt as a
stable prefix so the NPC has continuity across long sessions.

Stanford "Generative Agents" calls this Reflection; we follow the same
pattern but keep it lightweight: single summary text per (session, npc),
threshold-triggered, fire-and-forget. Failure leaves the previous summary in
place (or no summary at all) and the NPC degrades to the legacy structured-
memory recall path.
"""
from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from llm.usage_context import usage_context
from models.memory import MemoryEntry
from models.npc_reflection import NPCReflection
from utils import utcnow

logger = structlog.get_logger()

# How many new memory_entries must accumulate (since last_memory_id) before
# we re-reflect for an NPC. Configurable via settings; default 5 keeps cost
# modest while still capturing meaningful arc shifts.
def _reflection_threshold() -> int:
    return max(1, settings.npc_reflection_threshold)


# Cap the per-run reflection prompt to the most recent N memories. A backlog
# (failed runs don't advance last_memory_id; very active NPCs) would otherwise
# dump every accumulated memory and balloon the input (~5.5k tokens observed).
REFLECTION_MEMORY_LINE_CAP = 30


def _format_recent_memory_lines(memories: list, cap: int = REFLECTION_MEMORY_LINE_CAP) -> list[str]:
    """Format the most recent ``cap`` memories (assumes ascending order) as
    prompt lines."""
    return [
        f"- [第{m.round_number}轮·重要度{m.importance}] {m.content}"
        for m in memories[-cap:]
    ]


async def get_reflection(
    db: AsyncSession,
    session_id: str,
    npc_name: str,
) -> NPCReflection | None:
    stmt = select(NPCReflection).where(
        NPCReflection.session_id == session_id,
        NPCReflection.npc_name == npc_name,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def should_reflect(
    db: AsyncSession,
    session_id: str,
    npc_name: str,
) -> bool:
    """True if this NPC has accumulated >= threshold new memory entries since the last reflect."""
    if not settings.npc_reflection_enabled:
        return False

    existing = await get_reflection(db, session_id, npc_name)
    last_id = existing.last_memory_id if existing else 0

    count_stmt = (
        select(func.count(MemoryEntry.id))
        .where(
            MemoryEntry.session_id == session_id,
            MemoryEntry.related_npc == npc_name,
            MemoryEntry.id > last_id,
        )
    )
    result = await db.execute(count_stmt)
    new_count = result.scalar_one()
    return new_count >= _reflection_threshold()


def _build_reflection_prompt(
    npc_name: str,
    npc_personality: str,
    previous_summary: str | None,
    memory_lines: list[str],
) -> tuple[str, str]:
    """Return (system, user) prompt strings for the reflection LLM call."""
    system = (
        f"你扮演 NPC「{npc_name}」。请用第一人称写一段你作为这个角色的内心总结，"
        "融合下面的近期经历和你之前的反思（如果有）。"
        "目标 150-200 字，要包含：\n"
        "- 你对玩家的整体看法和信任度变化\n"
        "- 最近经历中的关键发现或情绪转折\n"
        "- 你内心一直在意但还没解决的事\n\n"
        "## 严格约束\n"
        "- 第一人称内心独白，不要列举事件\n"
        "- 不要写成日记或时间流水账\n"
        "- 语言风格符合你的性格\n"
        "- 不要打破第四面墙、不要提及游戏/系统/AI 概念\n\n"
        f"## 你的性格\n{npc_personality or '（未提供）'}"
    )
    user_parts = []
    if previous_summary:
        user_parts.append(f"## 你之前的反思（基础上延展，不要重复）\n{previous_summary}")
    if memory_lines:
        user_parts.append("## 你最近经历的记忆\n" + "\n".join(memory_lines))
    user_parts.append("请写出你最新的内心独白。")
    user = "\n\n".join(user_parts)
    return system, user


async def reflect(
    db: AsyncSession,
    *,
    session_id: str,
    npc_name: str,
    npc_personality: str,
    llm_router,
) -> NPCReflection | None:
    """Run a single reflection pass. Commits the new/updated row on success.

    Returns None on any failure path (no new memories, LLM error, empty
    output). Caller should treat None as "skip this round, retry next time".
    """
    if not settings.npc_reflection_enabled or llm_router is None:
        return None

    existing = await get_reflection(db, session_id, npc_name)
    last_id = existing.last_memory_id if existing else 0

    new_memories_stmt = (
        select(MemoryEntry)
        .where(
            MemoryEntry.session_id == session_id,
            MemoryEntry.related_npc == npc_name,
            MemoryEntry.id > last_id,
        )
        .order_by(MemoryEntry.id.asc())
    )
    new_memories = (await db.execute(new_memories_stmt)).scalars().all()
    if not new_memories:
        return None

    memory_lines = _format_recent_memory_lines(new_memories)
    # Advance the cursor past ALL fetched memories (incl. any dropped by the
    # cap), so a backlog isn't re-fetched and re-dumped on the next run.
    new_max_id = max(m.id for m in new_memories)

    system, user = _build_reflection_prompt(
        npc_name=npc_name,
        npc_personality=npc_personality,
        previous_summary=existing.summary if existing else None,
        memory_lines=memory_lines,
    )

    summary_parts: list[str] = []
    try:
        # Override the inherited ``purpose`` so this fire-and-forget LLM
        # call is billed as ``reflection``, not the parent turn's ``game``.
        with usage_context(purpose="reflection", session_id=session_id):
            async for event in llm_router.stream_with_tools(
                messages=[{"role": "user", "content": user}],
                tools=[],
                system=system,
                max_tokens=600,
            ):
                if event.get("type") == "text_delta":
                    summary_parts.append(event.get("text", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "npc_reflection.llm_failed",
            session_id=session_id,
            npc_name=npc_name,
            error=str(exc),
        )
        return None

    summary = "".join(summary_parts).strip()
    if not summary:
        logger.warning(
            "npc_reflection.empty_output",
            session_id=session_id,
            npc_name=npc_name,
        )
        return None

    if existing:
        existing.summary = summary
        existing.last_memory_id = new_max_id
        existing.reflection_count = (existing.reflection_count or 1) + 1
        existing.updated_at = utcnow()
        record = existing
    else:
        record = NPCReflection(
            session_id=session_id,
            npc_name=npc_name,
            summary=summary,
            last_memory_id=new_max_id,
            reflection_count=1,
        )
        db.add(record)
    await db.commit()

    logger.info(
        "npc_reflection.updated",
        session_id=session_id,
        npc_name=npc_name,
        new_memories=len(new_memories),
        summary_chars=len(summary),
        reflection_count=record.reflection_count,
    )
    return record


async def maybe_reflect(
    db: AsyncSession,
    *,
    session_id: str,
    npc_name: str,
    npc_personality: str,
    llm_router,
) -> None:
    """Threshold-check then reflect if needed. Silent on failure."""
    try:
        if not await should_reflect(db, session_id, npc_name):
            return
        await reflect(
            db,
            session_id=session_id,
            npc_name=npc_name,
            npc_personality=npc_personality,
            llm_router=llm_router,
        )
    except Exception:  # noqa: BLE001
        # Reflection is fire-and-forget; never bubble up into the player turn.
        logger.warning(
            "npc_reflection.maybe_failed",
            session_id=session_id,
            npc_name=npc_name,
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
