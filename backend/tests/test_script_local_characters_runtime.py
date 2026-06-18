"""Integration: script-owned 反哺 characters flow through the runtime roster.

Exercises the real DB path (no LLM) for the parts unique to the feature: the
``_load_session_npcs`` union, the duck-typed ``_AttachedNPC`` flowing through
``_load_world_data``, and NPC↔NPC relation seeding off an attached character.
"""
import pytest
from sqlalchemy import select

from models.game import GameSession
from models.npc_relation import NPCRelation
from models.script import Script
from models.user import User
from models.world import World, WorldCharacter
from services.game_service import GameService, _AttachedNPC


class _FakeOrchestrator:
    async def process_action(self, *args, **kwargs):
        if False:
            yield {}


async def _setup(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="三国世界", description="x", genre="历史", era="汉末",
        difficulty=3, estimated_time="60", base_setting="base",
        script_setting="", status="published",
    )
    db.add(world)
    await db.flush()

    player = WorldCharacter(
        world_id=world.id, name="主公", personality="", playable=True,
        description="一方诸侯", abilities=[], initial_location="府邸",
        starting_inventory=[], mode="both",
    )
    world_npc = WorldCharacter(
        world_id=world.id, name="诸葛亮", personality="智", secret="隆中对",
        knowledge=["天下大势"], schedule={}, initial_location="军帐",
        playable=False, mode="both",
    )
    db.add_all([player, world_npc])
    await db.flush()

    script = Script(
        world_id=world.id, name="桃园案", description="d",
        script_setting="真相", events_data=[], endings_data=[],
        is_published=True, status="published",
        # 反哺角色：世界名册里没有的原作 canonical 角色，随剧本走
        local_characters=[
            {
                "name": "关羽", "personality": "忠义", "secret": "夜读春秋",
                "knowledge": ["万人敌"], "schedule": {"evening": "营帐"},
                "initial_location": "营帐", "narrative_weight": 60,
                "voice_style": "傲然", "description": "万人敌",
                "initial_peer_relations": [
                    {"target": "诸葛亮", "trust": 6, "kind": "同僚"}
                ],
            }
        ],
    )
    db.add(script)
    await db.commit()
    return user, world, player, world_npc, script


@pytest.mark.asyncio
async def test_attached_character_joins_runtime_roster(db):
    _, world, player, world_npc, script = await _setup(db)
    service = GameService(_FakeOrchestrator())

    npcs = await service._load_session_npcs(
        db, world_id=world.id, exclude_character_id=player.id,
        player_name=player.name, script_id=script.id,
    )
    names = {n.name for n in npcs}
    assert names == {"诸葛亮", "关羽"}          # world NPC ∪ attached; player excluded
    guan = next(n for n in npcs if n.name == "关羽")
    assert isinstance(guan, _AttachedNPC)
    assert guan.id is None                       # no DB row — name-keyed runtime


@pytest.mark.asyncio
async def test_attached_character_reaches_world_data_npcs(db):
    _, world, player, _, script = await _setup(db)
    service = GameService(_FakeOrchestrator())

    npcs = await service._load_session_npcs(
        db, world_id=world.id, exclude_character_id=player.id,
        player_name=player.name, script_id=script.id,
    )
    world_data = await service._load_world_data(
        db, world, npcs, script_id=script.id, player_character=player,
    )
    by_name = {n["name"]: n for n in world_data["npcs"]}
    assert "关羽" in by_name
    assert by_name["关羽"]["secret"] == "夜读春秋"
    assert by_name["关羽"]["schedule"] == {"evening": "营帐"}


@pytest.mark.asyncio
async def test_attached_character_peer_relation_seeds(db):
    user, world, player, _, script = await _setup(db)
    service = GameService(_FakeOrchestrator())

    npcs = await service._load_session_npcs(
        db, world_id=world.id, exclude_character_id=player.id,
        player_name=player.name, script_id=script.id,
    )
    session = GameSession(
        user_id=user.id, world_id=world.id, character_id=player.id,
        script_id=script.id, mode="script", status="playing",
        game_state={}, rounds_played=0,
    )
    db.add(session)
    await db.flush()

    service._seed_npc_relations(db, session_id=str(session.id), npcs=npcs)
    await db.commit()

    rels = (await db.execute(
        select(NPCRelation).where(NPCRelation.session_id == session.id)
    )).scalars().all()
    pairs = {(r.npc_a, r.npc_b): r for r in rels}
    # 关羽→诸葛亮 declared (kind→label mapped); symmetric backfill adds the reverse.
    assert ("关羽", "诸葛亮") in pairs
    assert pairs[("关羽", "诸葛亮")].trust == 6
    assert pairs[("关羽", "诸葛亮")].relationship_label == "同僚"
    assert ("诸葛亮", "关羽") in pairs
