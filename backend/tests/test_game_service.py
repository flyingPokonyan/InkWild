import pytest
from sqlalchemy import select

from config import settings
from middleware.error_handler import AppError
from models.case_board_history import CaseBoardHistory
from models.game import GameSession
from models.user import User
from models.script import Script
from models.world import World, WorldCharacter
from services.game_service import GameService
from engine.state_manager import GameState


class FakeOrchestrator:
    async def process_action(self, *args, **kwargs):
        if False:
            yield {}


@pytest.mark.asyncio
async def test_start_game_requires_available_script_for_script_mode(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.commit()

    service = GameService(FakeOrchestrator())

    with pytest.raises(AppError) as exc:
        async for _ in service.start_game(db, user.id, world.id, character.id, "script", None, None):
            pass

    assert exc.value.code == 40008


@pytest.mark.asyncio
async def test_start_game_rejects_character_not_in_script_roster(db):
    """剧本可玩名单非空时，选了不在名单里的角色 → 40009。"""
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="W", description="", genre="悬疑", era="现代", difficulty=1,
        estimated_time="30分钟", base_setting="base", script_setting="", status="published",
    )
    db.add(world)
    await db.flush()
    allowed = WorldCharacter(
        world_id=world.id, name="主角", personality="", playable=True, description="",
        abilities=[], initial_location="镇口", starting_inventory=[], mode="both",
    )
    disallowed = WorldCharacter(
        world_id=world.id, name="配角", personality="", playable=True, description="",
        abilities=[], initial_location="镇口", starting_inventory=[], mode="both",
    )
    db.add_all([allowed, disallowed])
    await db.flush()
    script = Script(
        world_id=world.id, name="剧本", description="", script_setting="s",
        is_published=True, status="published", playable_character_ids=[str(allowed.id)],
    )
    db.add(script)
    await db.commit()

    service = GameService(FakeOrchestrator())
    with pytest.raises(AppError) as exc:
        async for _ in service.start_game(db, user.id, world.id, disallowed.id, "script", script.id, None):
            pass
    assert exc.value.code == 40009


@pytest.mark.asyncio
async def test_start_game_rejects_cross_world_character(db):
    """角色不属于该世界（API 直传跨世界 character_id）→ 40002。"""
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    def _world(name):
        return World(
            name=name, description="", genre="悬疑", era="现代", difficulty=1,
            estimated_time="30分钟", base_setting="base", free_setting="夜里有动静", status="published",
        )

    world_a = _world("A")
    world_b = _world("B")
    db.add_all([world_a, world_b])
    await db.flush()
    char_b = WorldCharacter(
        world_id=world_b.id, name="外人", personality="", playable=True, description="",
        abilities=[], initial_location="别处", starting_inventory=[], mode="both",
    )
    db.add(char_b)
    await db.commit()

    service = GameService(FakeOrchestrator())
    with pytest.raises(AppError) as exc:
        async for _ in service.start_game(db, user.id, world_a.id, char_b.id, "free", None, None):
            pass
    assert exc.value.code == 40002


@pytest.mark.asyncio
async def test_start_game_blocks_non_owner_on_private_world(db):
    """Privacy gate: a private world is only playable by its owner."""
    owner = User(nickname="owner")
    intruder = User(nickname="intruder")
    db.add_all([owner, intruder])
    await db.flush()

    world = World(
        name="私有世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        free_setting="夜里有人失踪",
        status="private",
        created_by_user_id=owner.id,
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.commit()

    service = GameService(FakeOrchestrator())

    with pytest.raises(AppError) as exc:
        async for _ in service.start_game(db, intruder.id, world.id, character.id, "free", None, None):
            pass

    assert exc.value.code == 40001


class FakeTurnOrchestrator:
    async def process_action(self, *args, **kwargs):
        yield {
            "type": "state_update",
            "game_state": {"current_location": "茶摊", "current_time": "第1天·下午"},
            "quick_actions": ["继续观察"],
            "triggered_events": [],
        }
        yield {
            "type": "done",
            "new_state": type(
                "FakeState",
                (),
                {"to_dict": lambda self: {"current_location": "茶摊", "current_time": "第1天·下午"}},
            )(),
            "usage": None,
        }


class StateReadyOrchestrator:
    async def process_action(self, *args, **kwargs):
        new_state = GameState(
            current_time="第1天·下午",
            current_location="茶摊",
            player_inventory=[],
            discovered_clues=[],
            npc_relations={},
            triggered_events=[],
            visited_locations=["镇口", "茶摊"],
            time_index=1,
            round_number=1,
        )
        yield {"type": "processing", "phase": "thinking"}
        yield {"type": "state_ready", "new_state": new_state}
        yield {"type": "narrative", "text": "你走向茶摊。"}
        yield {
            "type": "state_update",
            "game_state": new_state.to_dict(),
            "quick_actions": ["继续观察"],
            "triggered_events": [],
        }
        yield {"type": "done", "new_state": new_state, "usage": None}


class CaseBoardStateReadyOrchestrator:
    async def process_action(self, *args, **kwargs):
        new_state = GameState(
            current_time="第1天·下午",
            current_location="茶摊",
            player_inventory=[],
            discovered_clues=[{"id": "clue_001", "content": "门槛血迹", "found_at": "第1天·上午"}],
            npc_relations={},
            triggered_events=[],
            visited_locations=["镇口", "茶摊"],
            time_index=1,
            round_number=1,
            case_board={"evidence": [{"clue_id": "clue_001", "category": "physical"}]},
        )
        history_entries = [
            {
                "op_type": "upsert_list_item",
                "path": ["evidence"],
                "payload": {
                    "match": {"clue_id": "clue_001"},
                    "value": {"clue_id": "clue_001", "category": "physical"},
                },
                "before": None,
                "after": {"clue_id": "clue_001", "category": "physical"},
                "reason": "新增门槛血迹证据。",
            }
        ]
        yield {
            "type": "state_ready",
            "new_state": new_state,
            "case_board_history_entries": history_entries,
        }
        yield {"type": "narrative", "text": "你发现门槛边的血迹。"}
        yield {
            "type": "state_update",
            "game_state": new_state.to_dict(),
            "quick_actions": ["继续观察"],
            "triggered_events": [],
        }
        yield {
            "type": "done",
            "new_state": new_state,
            "usage": None,
            "case_board_history_entries": history_entries,
        }


@pytest.mark.asyncio
async def test_start_game_retires_other_active_sessions_same_script(db, monkeypatch):
    """强制单局（剧本模式）：开新局时同 (user, world, script) 下所有进行中旧局
    自动结束（status=ended, ending_type=abandoned）；不同剧本的局不受影响。"""
    # 关掉开局态度推断：它会调 orchestrator.npc_llm_router（fake 没有），与本测试无关。
    monkeypatch.setattr(settings, "npc_initial_stance_enabled", False)

    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="W", description="", genre="悬疑", era="现代", difficulty=1,
        estimated_time="30分钟", base_setting="base", script_setting="", status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id, name="调查员", personality="", playable=True, description="",
        abilities=[], initial_location="镇口", starting_inventory=[], mode="both",
    )
    db.add(character)
    await db.flush()
    script = Script(
        world_id=world.id, name="剧本A", description="", script_setting="s",
        is_published=True, status="published", playable_character_ids=[],
        events_data=[], endings_data=[],
    )
    other_script = Script(
        world_id=world.id, name="剧本B", description="", script_setting="s2",
        is_published=True, status="published", playable_character_ids=[],
        events_data=[], endings_data=[],
    )
    db.add_all([script, other_script])
    await db.flush()

    def _sess(script_id, status):
        return GameSession(
            user_id=user.id, world_id=world.id, character_id=character.id,
            script_id=script_id, mode="script", status=status,
            game_state={"current_location": "镇口", "current_time": "第1天·上午"},
            rounds_played=1,
        )

    old_playing = _sess(script.id, "playing")
    old_paused = _sess(script.id, "paused")
    other = _sess(other_script.id, "playing")  # 控制组：不同剧本，不应被结束
    db.add_all([old_playing, old_paused, other])
    await db.commit()
    old_ids = {old_playing.id, old_paused.id}

    service = GameService(FakeTurnOrchestrator())
    async for _ in service.start_game(db, user.id, world.id, character.id, "script", script.id, None):
        pass

    await db.refresh(old_playing)
    await db.refresh(old_paused)
    await db.refresh(other)
    assert old_playing.status == "ended" and old_playing.ending_type == "abandoned"
    assert old_paused.status == "ended" and old_paused.ending_type == "abandoned"
    assert other.status == "playing"  # 不同剧本不动

    rows = (await db.execute(
        select(GameSession).where(
            GameSession.script_id == script.id, GameSession.status == "playing"
        )
    )).scalars().all()
    assert len(rows) == 1  # 只剩新开的那一个
    assert rows[0].id not in old_ids


@pytest.mark.asyncio
async def test_start_game_retires_other_active_sessions_same_free_character(db, monkeypatch):
    """强制单局（自由模式）：开新局时同 (user, world, character) 下进行中旧局
    自动结束；同世界但不同角色的自由局不受影响。"""
    monkeypatch.setattr(settings, "npc_initial_stance_enabled", False)

    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="自由世界", description="", genre="悬疑", era="现代", difficulty=1,
        estimated_time="30分钟", base_setting="base", free_setting="夜里有动静",
        status="published",
    )
    db.add(world)
    await db.flush()
    hero = WorldCharacter(
        world_id=world.id, name="主角", personality="", playable=True, description="",
        abilities=[], initial_location="镇口", starting_inventory=[], mode="both",
    )
    other_hero = WorldCharacter(
        world_id=world.id, name="另一个", personality="", playable=True, description="",
        abilities=[], initial_location="镇口", starting_inventory=[], mode="both",
    )
    db.add_all([hero, other_hero])
    await db.flush()

    def _free_sess(char_id):
        return GameSession(
            user_id=user.id, world_id=world.id, character_id=char_id,
            script_id=None, mode="free", status="playing",
            game_state={"current_location": "镇口", "current_time": "第1天·上午"},
            rounds_played=1,
        )

    old_same = _free_sess(hero.id)
    old_other_char = _free_sess(other_hero.id)  # 控制组：不同角色，不应被结束
    db.add_all([old_same, old_other_char])
    await db.commit()
    old_same_id = old_same.id

    service = GameService(FakeTurnOrchestrator())
    async for _ in service.start_game(db, user.id, world.id, hero.id, "free", None, None):
        pass

    await db.refresh(old_same)
    await db.refresh(old_other_char)
    assert old_same.status == "ended" and old_same.ending_type == "abandoned"
    assert old_other_char.status == "playing"  # 不同角色不动

    rows = (await db.execute(
        select(GameSession).where(
            GameSession.character_id == hero.id, GameSession.status == "playing"
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].id != old_same_id


@pytest.mark.asyncio
async def test_process_action_preserves_previous_state_for_retry(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "镇口", "current_time": "第1天·上午"},
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    service = GameService(FakeTurnOrchestrator())

    async for _ in service.process_action(db, user.id, session.id, "我去茶摊"):
        pass

    await db.refresh(session)
    assert session.state_snapshot == {"current_location": "镇口", "current_time": "第1天·上午"}
    assert session.last_action_text == "我去茶摊"
    assert session.retry_count == 0


@pytest.mark.asyncio
async def test_process_action_commits_state_before_narrative_is_yielded(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()
    initial_state = GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        visited_locations=["镇口"],
        time_index=0,
    )
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state=initial_state.to_dict(),
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    service = GameService(StateReadyOrchestrator())
    stream = service.process_action(db, user.id, session.id, "我去茶摊")

    first_event = await anext(stream)
    assert first_event["type"] == "processing"
    narrative_event = await anext(stream)
    assert narrative_event == {"type": "narrative", "text": "你走向茶摊。"}

    await db.refresh(session)
    assert session.game_state["current_location"] == "茶摊"
    assert session.rounds_played == 1
    assert session.version == 1

    await stream.aclose()


@pytest.mark.asyncio
async def test_process_action_persists_case_board_history_with_state_ready(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()
    initial_state = GameState(
        current_time="第1天·上午",
        current_location="镇口",
        player_inventory=[],
        discovered_clues=[{"id": "clue_001", "content": "门槛血迹", "found_at": "第1天·上午"}],
        npc_relations={},
        triggered_events=[],
        visited_locations=["镇口"],
        time_index=0,
    )
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state=initial_state.to_dict(),
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    service = GameService(CaseBoardStateReadyOrchestrator())

    async for _ in service.process_action(db, user.id, session.id, "我检查门槛"):
        pass

    result = await db.execute(
        select(CaseBoardHistory).where(CaseBoardHistory.session_id == session.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].round_number == 1
    assert rows[0].op_type == "upsert_list_item"
    assert rows[0].payload["value"]["clue_id"] == "clue_001"


@pytest.mark.asyncio
async def test_retry_action_respects_max_retry_limit(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()

    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "镇口", "current_time": "第1天·上午"},
        state_snapshot={"current_location": "镇口", "current_time": "第1天·上午"},
        last_action_text="我去茶摊",
        retry_count=3,
        rounds_played=1,
    )
    db.add(session)
    await db.commit()

    service = GameService(FakeTurnOrchestrator())

    with pytest.raises(AppError) as exc:
        async for _ in service.retry_action(db, user.id, session.id):
            pass

    assert exc.value.code == 40007


@pytest.mark.asyncio
async def test_retry_action_versions_restore_before_replayed_turn(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()

    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "错误路径", "current_time": "第1天·夜晚"},
        state_snapshot={"current_location": "镇口", "current_time": "第1天·上午"},
        last_action_text="我去茶摊",
        retry_count=0,
        rounds_played=1,
    )
    db.add(session)
    await db.flush()
    db.add(
        CaseBoardHistory(
            session_id=session.id,
            round_number=1,
            op_type="upsert_list_item",
            path=["evidence"],
            payload={"value": {"clue_id": "clue_001"}},
            before=None,
            after={"clue_id": "clue_001"},
            reason="废弃回合的案件面板更新。",
        )
    )
    await db.commit()

    service = GameService(FakeTurnOrchestrator())

    async for _ in service.retry_action(db, user.id, session.id):
        pass

    await db.refresh(session)
    assert session.version == 2
    assert session.retry_count == 1
    assert session.game_state == {"current_location": "茶摊", "current_time": "第1天·下午"}

    history_result = await db.execute(
        select(CaseBoardHistory).where(CaseBoardHistory.session_id == session.id)
    )
    assert history_result.scalars().all() == []


@pytest.mark.asyncio
async def test_load_world_data_includes_npc_schedule_and_initial_location(db):
    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    db.add(
        WorldCharacter(
            world_id=world.id,
            name="陈医生",
            personality="谨慎",
            secret="藏了一个人",
            initial_location="诊所",
            schedule={"上午": "诊所", "夜晚": "后山"},
            playable=False,
        )
    )
    await db.commit()

    npcs = (await db.execute(
        select(WorldCharacter).where(WorldCharacter.world_id == world.id)
    )).scalars().all()
    service = GameService(FakeOrchestrator())

    world_data = await service._load_world_data(db, world, npcs)

    assert world_data["npcs"] == [
        {
            "name": "陈医生",
            "personality": "谨慎",
            "secret": "藏了一个人",
            "knowledge": [],
            "initial_location": "诊所",
            "schedule": {"上午": "诊所", "夜晚": "后山"},
        }
    ]


# BUGS #22 regression: v2 director / world_simulator / orchestrator-intent paths
# all read world_data["events_data"]. Producer must populate that key, not just
# the legacy "events" bucket used by check_events.
@pytest.mark.asyncio
async def test_load_world_data_exposes_events_data_for_script_mode(db):
    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="唐",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        status="published",
    )
    db.add(world)
    await db.flush()
    v2_events = [
        {
            "id": "evt_1",
            "kind": "conditional",
            "summary": "test",
            "trigger": {"condition_dsl": "round >= 3", "probability": 1.0},
            "effects": {"spawn_clues": ["c"]},
        }
    ]
    script = Script(
        world_id=world.id,
        name="s",
        description="d",
        status="published",
        is_published=True,
        script_setting="setting",
        events_data=v2_events,
        endings_data=[],
    )
    db.add(script)
    await db.commit()

    service = GameService(FakeOrchestrator())
    world_data = await service._load_world_data(db, world, [], script_id=script.id)

    assert world_data["events_data"] == v2_events
    # script mode: legacy "events" bucket stays empty (check_events reads it).
    assert world_data["events"] == []


@pytest.mark.asyncio
async def test_load_world_data_exposes_world_events_data_for_free_mode(db):
    v2_events = [
        {
            "id": "evt_a",
            "kind": "conditional",
            "summary": "free-mode event",
            "trigger": {"condition_dsl": "round >= 1", "probability": 1.0},
            "effects": {},
        }
    ]
    world = World(
        name="自由世界",
        description="d",
        genre="g",
        era="e",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        status="published",
        events_data=v2_events,
    )
    db.add(world)
    await db.commit()

    service = GameService(FakeOrchestrator())
    world_data = await service._load_world_data(db, world, [])

    assert world_data["events_data"] == v2_events
