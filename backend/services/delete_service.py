"""Hard-delete service for published worlds and scripts.

权限 / 安全规则：
- 必须是 owner 或 admin
- 有 active game sessions（status='playing'）时拒绝，避免崩用户游戏；
  调用方传 force=True（且是 admin）可绕过 — 已结束的 session 直接级联删
- world 下有 published scripts 时拒绝；admin force=True 时一并删

级联范围：
- world: world_characters / endings / characters / events / npcs / ip_knowledge_packs
         / world_drafts / scripts (含其 script_drafts) / game_sessions (含 messages / memory_entries / token_usage)
- script: script_drafts.script_id 解关联 / game_sessions (含 messages 等)
"""
from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.case_board_history import CaseBoardHistory
from models.draft import ScriptDraft, WorldDraft
from models.game import GameSession, Message, TokenUsage
from models.ip_knowledge_pack import IPKnowledgePack
from models.memory import MemoryEntry
from models.npc_relation import NPCRelation
from models.npc_reflection import NPCReflection
from models.script import Script
from models.world import Character, Ending, Event, NPC, World, WorldCharacter


class DeleteConflictError(Exception):
    """Conflicting state prevents delete (e.g. active sessions, published children)."""


async def _purge_game_sessions(db: AsyncSession, *, world_id: str | None = None, script_id: str | None = None) -> int:
    """删除一批 sessions 及其子记录（messages / memory / token_usage）。返回删除条数。"""
    q = select(GameSession.id)
    if world_id is not None:
        q = q.where(GameSession.world_id == world_id)
    if script_id is not None:
        q = q.where(GameSession.script_id == script_id)
    session_ids = [row[0] for row in (await db.execute(q)).all()]
    if not session_ids:
        return 0
    await db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
    await db.execute(delete(MemoryEntry).where(MemoryEntry.session_id.in_(session_ids)))
    await db.execute(delete(TokenUsage).where(TokenUsage.session_id.in_(session_ids)))
    await db.execute(delete(NPCRelation).where(NPCRelation.session_id.in_(session_ids)))
    await db.execute(delete(NPCReflection).where(NPCReflection.session_id.in_(session_ids)))
    await db.execute(delete(CaseBoardHistory).where(CaseBoardHistory.session_id.in_(session_ids)))
    await db.execute(delete(GameSession).where(GameSession.id.in_(session_ids)))
    return len(session_ids)


async def delete_world(
    db: AsyncSession,
    *,
    world_id: str,
    actor_user_id: str,
    by_admin: bool,
    force: bool = False,
) -> dict:
    """硬删世界（含一切级联）。返回 summary。"""
    world = await db.get(World, world_id)
    if world is None:
        raise ValueError("世界不存在")

    if not by_admin and world.created_by_user_id != actor_user_id:
        raise PermissionError("Not owner of world")

    active_sessions = (
        await db.execute(
            select(GameSession.id)
            .where(GameSession.world_id == world_id, GameSession.status == "playing")
            .limit(1)
        )
    ).first()
    if active_sessions and not (by_admin and force):
        raise DeleteConflictError("有用户正在该世界游玩，无法删除（admin 可强制）")

    child_scripts = (
        await db.execute(select(Script.id).where(Script.world_id == world_id))
    ).scalars().all()
    if child_scripts and not by_admin and not force:
        raise DeleteConflictError("该世界下存在剧本，请先删除剧本（或由 admin 强删）")

    # ---- cascade ----
    sessions_purged = await _purge_game_sessions(db, world_id=world_id)
    if child_scripts:
        await db.execute(update(ScriptDraft).where(ScriptDraft.script_id.in_(child_scripts)).values(script_id=None))
        await db.execute(delete(Script).where(Script.id.in_(child_scripts)))
    await db.execute(delete(IPKnowledgePack).where(IPKnowledgePack.world_id == world_id))
    await db.execute(delete(WorldCharacter).where(WorldCharacter.world_id == world_id))
    await db.execute(delete(Ending).where(Ending.world_id == world_id))
    await db.execute(delete(Character).where(Character.world_id == world_id))
    await db.execute(delete(Event).where(Event.world_id == world_id))
    await db.execute(delete(NPC).where(NPC.world_id == world_id))
    await db.execute(update(WorldDraft).where(WorldDraft.world_id == world_id).values(world_id=None))
    await db.execute(update(ScriptDraft).where(ScriptDraft.world_id == world_id).values(world_id=None))
    await db.delete(world)
    await db.commit()

    return {
        "world_id": world_id,
        "scripts_deleted": len(child_scripts),
        "sessions_purged": sessions_purged,
    }


async def delete_script(
    db: AsyncSession,
    *,
    script_id: str,
    actor_user_id: str,
    by_admin: bool,
    force: bool = False,
) -> dict:
    """硬删剧本。"""
    script = await db.get(Script, script_id)
    if script is None:
        raise ValueError("剧本不存在")

    if not by_admin and script.created_by_user_id != actor_user_id:
        raise PermissionError("Not owner of script")

    active_sessions = (
        await db.execute(
            select(GameSession.id)
            .where(GameSession.script_id == script_id, GameSession.status == "playing")
            .limit(1)
        )
    ).first()
    if active_sessions and not (by_admin and force):
        raise DeleteConflictError("有用户正在该剧本游玩，无法删除（admin 可强制）")

    sessions_purged = await _purge_game_sessions(db, script_id=script_id)
    await db.execute(update(ScriptDraft).where(ScriptDraft.script_id == script_id).values(script_id=None))
    await db.delete(script)
    await db.commit()

    return {"script_id": script_id, "sessions_purged": sessions_purged}
