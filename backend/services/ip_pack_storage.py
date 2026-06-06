"""IPKnowledgePack 持久化：保存到 ip_knowledge_packs 表。

供 world_creator_agent_v2 在 ip_research 阶段调用。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.ip_knowledge_pack import IPKnowledgePack as IPKnowledgePackRow
from schemas.ip_knowledge_pack import IPKnowledgePack


async def save_ip_knowledge_pack(
    db: AsyncSession,
    pack: IPKnowledgePack,
    *,
    draft_id: str,
    world_id: str | None = None,
) -> IPKnowledgePackRow:
    """Persist an IPKnowledgePack JSON snapshot to ``ip_knowledge_packs``.

    Caller is responsible for committing the session — this helper only
    flushes so the row ID is materialised before returning.
    """
    row = IPKnowledgePackRow(
        world_id=world_id,
        draft_id=draft_id,
        ip_name=pack.ip_name,
        fidelity_mode=pack.fidelity_mode,
        pack_json=pack.model_dump(),
    )
    db.add(row)
    await db.flush()
    return row
