"""把一局 game_session 从 DB 抓成评测记录（逐回合）。

数据底座（已查证 2026-06-01）：
- messages.npc_dialogues：逐 NPC 台词 dict
- messages.state_snapshot：每回合状态（narrative_arc/discovered_clues/...）
- messages.content：旁白成品；role=user 是玩家动作
"""
from __future__ import annotations

from sqlalchemy import select, text

from models.game import Message


async def capture_session(db, session_id: str) -> dict:
    """Pull one session → {session_id, world_id, cost_cents, turns:[...]}.

    turn = {turn, player_action, narrative, npc_dialogues, state_snapshot}.
    Opening narrative (assistant with no preceding user) is turn 0.
    """
    rows = (
        await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        )
    ).scalars().all()

    turns: list[dict] = []
    pending_action: str | None = None
    idx = 0
    for m in rows:
        if m.role == "user":
            pending_action = (m.content or "").strip()
            continue
        if m.role == "assistant":
            turns.append({
                "turn": idx,
                "player_action": pending_action,
                "narrative": (m.content or "").strip(),
                "npc_dialogues": m.npc_dialogues or {},
                "state_snapshot": m.state_snapshot or {},
            })
            pending_action = None
            idx += 1

    world_id = (
        await db.execute(text("SELECT world_id FROM game_sessions WHERE id = :sid"), {"sid": session_id})
    ).scalar_one_or_none()

    cost = (
        await db.execute(
            text("SELECT COALESCE(SUM(cost_cents),0) FROM token_usage WHERE session_id = :sid"),
            {"sid": session_id},
        )
    ).scalar_one_or_none() or 0

    return {
        "session_id": session_id,
        "world_id": str(world_id) if world_id else None,
        "cost_cents": int(cost),
        "turns": turns,
    }


async def world_secrets(db, world_id: str) -> dict[str, str]:
    """{npc_name: secret} for leak-detection. Empty/None secrets skipped."""
    rows = (
        await db.execute(
            text("SELECT name, secret FROM world_characters WHERE world_id = :wid AND secret IS NOT NULL AND secret <> ''"),
            {"wid": world_id},
        )
    ).all()
    return {r[0]: r[1] for r in rows}
