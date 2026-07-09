"""Light tests for services/publish_service.py (B4)."""
import pytest
from sqlalchemy import select

from engine.content_status import ContentStatus
from models.draft import ScriptDraft, WorldDraft
from models.script import Script
from models.user import User
from models.world import World
from services.publish_service import (
    _derive_narrative_weight,
    apply_script_payload,
    approve_world_draft,
    publish_world_draft,
    publish_script_draft,
    reject_world_draft,
    restore_world,
    restore_script,
    save_world_as_private,
    save_script_as_private,
    submit_script_for_review,
    submit_world_for_review,
    withdraw_world,
    withdraw_world_submission,
    withdraw_script,
)


class TestDeriveNarrativeWeight:
    """Confirms the role_tag / is_image_target → narrative_weight mapping the
    world detail page relies on for character ordering.
    """

    def test_protagonist_role_tag_returns_100(self):
        assert _derive_narrative_weight({"role_tag": "主角"}) == 100
        assert _derive_narrative_weight({"role_tag": "女主角"}) == 100
        assert _derive_narrative_weight({"role_tag": "主"}) == 100

    def test_antagonist_role_tag_returns_90(self):
        assert _derive_narrative_weight({"role_tag": "宿敌"}) == 90
        assert _derive_narrative_weight({"role_tag": "反派"}) == 90

    def test_image_target_without_role_tag_returns_70(self):
        assert _derive_narrative_weight({"is_image_target": True}) == 70

    def test_protagonist_beats_image_target(self):
        # role_tag "主角" should win over is_image_target.
        assert (
            _derive_narrative_weight(
                {"role_tag": "主角", "is_image_target": True}
            )
            == 100
        )

    def test_supporting_default_50(self):
        assert _derive_narrative_weight({}) == 50
        assert _derive_narrative_weight({"role_tag": "市井小贩"}) == 50


def _script_payload(playable_character_ids):
    return {
        "name": "S",
        "description": "d",
        "difficulty": 3,
        "estimated_time": "30-60 min",
        "script_setting": "",
        "script_type": "mystery",
        "events": [],
        "clues": {},
        "endings": [],
        "playable_character_ids": playable_character_ids,
    }


class TestApplyScriptPayloadRoster:
    """剧本可玩名单写入：去重保序 / 按世界可玩集合过滤 / 空名单语义。"""

    def test_no_valid_set_writes_raw_deduped_in_order(self):
        script = Script()
        apply_script_payload(script, _script_payload(["a", "b", "a", "c"]))
        assert script.playable_character_ids == ["a", "b", "c"]

    def test_filters_against_valid_playable_ids(self):
        script = Script()
        apply_script_payload(
            script,
            _script_payload(["a", "x", "b"]),
            valid_playable_ids={"a", "b"},
        )
        assert script.playable_character_ids == ["a", "b"]

    def test_empty_roster_stays_empty(self):
        script = Script()
        apply_script_payload(script, _script_payload([]), valid_playable_ids={"a", "b"})
        assert script.playable_character_ids == []

    def test_all_filtered_out_becomes_empty(self):
        # 全部失效/非可玩 → 空名单 = 运行时放行全部，安全降级。
        script = Script()
        apply_script_payload(script, _script_payload(["x", "y"]), valid_playable_ids={"a"})
        assert script.playable_character_ids == []


def _world_draft_payload():
    return {
        "name": "Test World",
        "description": "test description",
        "genre": "mystery",
        "era": "modern",
        "difficulty": 3,
        "estimated_time": "30",
        "base_setting": "test base",
        "locations": [],
        "world_characters": [],
    }


def _script_draft_payload():
    return {
        "name": "Test Script",
        "description": "test script description",
        "difficulty": 3,
        "estimated_time": "60",
        "script_setting": "test setting",
        "events": [
            {
                "id": f"evt_{i:03d}",
                "kind": "conditional",
                "summary": "stub event",
                "trigger": {"condition_dsl": "time_after('day_1')", "probability": 1.0},
                "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
                "rumors": [],
            }
            for i in range(3)
        ],
        "clues": {},
        "endings": [
            {
                "ending_type": "good",
                "title": "好结局",
                "description": "玩家走向好的结局描述。" * 5,
                "soft_conditions": "玩家在 day_5 前发现关键线索",
                "priority": 1,
                "quality": "best",
            },
            {
                "ending_type": "bad",
                "title": "坏结局",
                "description": "玩家走向坏的结局描述。" * 5,
                "soft_conditions": "玩家被陷害",
                "priority": 0,
                "quality": "worst",
            },
        ],
    }


@pytest.fixture
async def sample_user(db):
    user = User(nickname="creator", is_admin=False)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def sample_world(db, sample_user):
    world = World(
        name="Existing World",
        description="desc",
        genre="mystery",
        era="modern",
        difficulty=3,
        estimated_time="30",
        base_setting="base",
        status="published",
        created_by_user_id=sample_user.id,
    )
    db.add(world)
    await db.commit()
    await db.refresh(world)
    return world


@pytest.fixture
async def sample_script(db, sample_user, sample_world):
    script = Script(
        world_id=sample_world.id,
        name="Existing Script",
        description="desc",
        status="published",
        is_published=True,
        created_by_user_id=sample_user.id,
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


# ---------------------------------------------------------------------------
# World publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_world_draft_creates_world(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    world = await publish_world_draft(db, draft_id=draft.id, actor_user_id=sample_user.id)

    assert world.name == "Test World"
    assert world.status == ContentStatus.PUBLISHED
    assert world.created_by_user_id == sample_user.id
    # draft.world_id should be updated
    await db.refresh(draft)
    assert draft.world_id == world.id


@pytest.mark.asyncio
async def test_publish_world_draft_writes_v2_jsonb_fields(db, sample_user):
    """Regression for 2026-05-24 bug: apply_world_payload skipped events_data
    / shared_events / lore_pack so the worlds row had NULL JSONB columns even
    when the draft payload had content. Free-mode runtime + admin editor
    silently saw empty content.
    """
    payload = _world_draft_payload()
    payload["events_data"] = [{"id": "evt_1", "summary": "test event"}]
    payload["shared_events"] = [{"id": "se_1", "title": "shared event"}]
    payload["lore_pack"] = {"timeline": [{"year": 2020, "note": "x"}]}
    payload["visual_style"] = {
        "version": 1,
        "genre_category": "古风宫廷",
        "culture": "中式古典",
        "art_style": "古籍绣像",
    }
    draft = WorldDraft(payload=payload, created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    world = await publish_world_draft(db, draft_id=draft.id, actor_user_id=sample_user.id)
    await db.refresh(world)

    assert world.events_data == [{"id": "evt_1", "summary": "test event"}]
    assert world.shared_events == [{"id": "se_1", "title": "shared event"}]
    assert world.lore_pack == {
        "timeline": [{"year": 2020, "note": "x"}],
        "visual_style": {
            "version": 1,
            "genre_category": "古风宫廷",
            "culture": "中式古典",
            "art_style": "古籍绣像",
        },
    }


@pytest.mark.asyncio
async def test_publish_world_draft_rejects_non_owner(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    other = User(nickname="other", is_admin=False)
    db.add(other)
    await db.commit()

    with pytest.raises(PermissionError):
        await publish_world_draft(db, draft_id=draft.id, actor_user_id=other.id)


# ---------------------------------------------------------------------------
# World withdraw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withdraw_world_owner_returns_to_private(db, sample_user, sample_world):
    world = await withdraw_world(
        db, world_id=sample_world.id, actor_user_id=sample_user.id, by_admin=False
    )
    assert world.status == ContentStatus.PRIVATE


@pytest.mark.asyncio
async def test_withdraw_world_admin_marks_withdrawn(db, sample_user, sample_world):
    admin = User(nickname="admin", is_admin=True)
    db.add(admin)
    await db.commit()

    world = await withdraw_world(
        db, world_id=sample_world.id, actor_user_id=admin.id, by_admin=True
    )
    assert world.status == ContentStatus.WITHDRAWN


@pytest.mark.asyncio
async def test_withdraw_world_admin_cascades_published_scripts(
    db, sample_user, sample_world, sample_script
):
    """admin 下架世界 → 配下「已发布」剧本连锁到 WITHDRAWN 终态并下线。

    回归：旧实现只改 world.status，剧本仍挂 published，工坊出现
    「世界已下架但剧本已发布」的矛盾态。
    """
    admin = User(nickname="admin_cascade", is_admin=True)
    db.add(admin)
    await db.commit()

    await withdraw_world(
        db, world_id=sample_world.id, actor_user_id=admin.id, by_admin=True
    )

    await db.refresh(sample_script)
    assert sample_script.status == ContentStatus.WITHDRAWN
    assert sample_script.is_published is False


@pytest.mark.asyncio
async def test_withdraw_world_owner_cascades_published_scripts_to_private(
    db, sample_user, sample_world, sample_script
):
    """owner 下架世界 → 配下「已发布」剧本回退 PRIVATE 并下线。"""
    await withdraw_world(
        db, world_id=sample_world.id, actor_user_id=sample_user.id, by_admin=False
    )

    await db.refresh(sample_script)
    assert sample_script.status == ContentStatus.PRIVATE
    assert sample_script.is_published is False


# ---------------------------------------------------------------------------
# Script publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_script_draft_creates_script(db, sample_user, sample_world):
    draft = ScriptDraft(
        world_id=sample_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    script = await publish_script_draft(db, draft_id=draft.id, actor_user_id=sample_user.id)

    assert script.name == "Test Script"
    assert script.status == ContentStatus.PUBLISHED
    assert script.is_published is True
    assert script.created_by_user_id == sample_user.id
    await db.refresh(draft)
    assert draft.script_id == script.id


@pytest.mark.asyncio
async def test_publish_script_draft_syncs_endings_table(db, sample_user, sample_world):
    """Regression for 2026-05-24 bug: nothing in services/api/models was
    inserting Ending rows. Pipeline-generated worlds had 0 Endings in the
    table (free-mode runtime + Tier1 read it). publish_script_draft now
    wipes + repopulates Ending rows for the script's world.
    """
    from models.world import Ending
    draft = ScriptDraft(
        world_id=sample_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    await publish_script_draft(db, draft_id=draft.id, actor_user_id=sample_user.id)

    rows = (await db.execute(select(Ending).where(Ending.world_id == sample_world.id))).scalars().all()
    titles = {r.title for r in rows}
    assert titles == {"好结局", "坏结局"}, f"expected 2 endings synced, got {titles}"


@pytest.mark.asyncio
async def test_publish_script_draft_rejects_non_owner(db, sample_user, sample_world):
    draft = ScriptDraft(
        world_id=sample_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    other = User(nickname="other2", is_admin=False)
    db.add(other)
    await db.commit()

    with pytest.raises(PermissionError):
        await publish_script_draft(db, draft_id=draft.id, actor_user_id=other.id)


# ---------------------------------------------------------------------------
# Script withdraw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withdraw_script_owner_returns_to_private(db, sample_user, sample_script):
    script = await withdraw_script(
        db, script_id=sample_script.id, actor_user_id=sample_user.id, by_admin=False
    )
    assert script.status == ContentStatus.PRIVATE
    assert script.is_published is False


@pytest.mark.asyncio
async def test_withdraw_script_admin_marks_withdrawn(db, sample_user, sample_script):
    admin = User(nickname="admin2", is_admin=True)
    db.add(admin)
    await db.commit()

    script = await withdraw_script(
        db, script_id=sample_script.id, actor_user_id=admin.id, by_admin=True
    )
    assert script.status == ContentStatus.WITHDRAWN
    assert script.is_published is False


# ---------------------------------------------------------------------------
# Restore (admin un-withdraw → republish)
# ---------------------------------------------------------------------------


@pytest.fixture
async def withdrawn_world(db, sample_user):
    world = World(
        name="Taken Down World",
        description="d",
        genre="g",
        era="e",
        difficulty=3,
        estimated_time="30",
        base_setting="b",
        status=ContentStatus.WITHDRAWN,
        created_by_user_id=sample_user.id,
    )
    db.add(world)
    await db.commit()
    await db.refresh(world)
    return world


@pytest.mark.asyncio
async def test_restore_world_republishes(db, sample_user, withdrawn_world):
    """admin 恢复被下架世界 → 重新 PUBLISHED 上架。"""
    admin = User(nickname="restorer", is_admin=True)
    db.add(admin)
    await db.commit()

    restored = await restore_world(
        db, world_id=withdrawn_world.id, actor_user_id=admin.id
    )
    assert restored.status == ContentStatus.PUBLISHED


@pytest.mark.asyncio
async def test_restore_non_withdrawn_world_raises(db, sample_user, sample_world):
    """已发布世界没什么可恢复 → 非法迁移。"""
    admin = User(nickname="restorer2", is_admin=True)
    db.add(admin)
    await db.commit()

    with pytest.raises(ValueError, match="Invalid restore"):
        await restore_world(db, world_id=sample_world.id, actor_user_id=admin.id)


@pytest.mark.asyncio
async def test_restore_script_republishes_under_published_world(
    db, sample_user, sample_world
):
    """世界已发布时，恢复被下架剧本 → PUBLISHED + 重新上线。"""
    script = Script(
        world_id=sample_world.id,
        name="Taken Down Script",
        description="d",
        status=ContentStatus.WITHDRAWN,
        is_published=False,
        created_by_user_id=sample_user.id,
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)

    admin = User(nickname="restorer3", is_admin=True)
    db.add(admin)
    await db.commit()

    restored = await restore_script(
        db, script_id=script.id, actor_user_id=admin.id
    )
    assert restored.status == ContentStatus.PUBLISHED
    assert restored.is_published is True


@pytest.mark.asyncio
async def test_restore_script_requires_published_world(
    db, sample_user, withdrawn_world
):
    """所属世界仍是 withdrawn 时，剧本不能单独恢复（否则世界下公开剧本矛盾）。"""
    script = Script(
        world_id=withdrawn_world.id,
        name="Orphan Script",
        description="d",
        status=ContentStatus.WITHDRAWN,
        is_published=False,
        created_by_user_id=sample_user.id,
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)

    admin = User(nickname="restorer4", is_admin=True)
    db.add(admin)
    await db.commit()

    with pytest.raises(ValueError, match="请先恢复所属世界"):
        await restore_script(db, script_id=script.id, actor_user_id=admin.id)


# ---------------------------------------------------------------------------
# State machine: invalid transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withdraw_withdrawn_world_raises(db, sample_user):
    world = World(
        name="Already Withdrawn",
        description="d",
        genre="g",
        era="e",
        difficulty=3,
        estimated_time="30",
        base_setting="b",
        status=ContentStatus.WITHDRAWN,
        created_by_user_id=sample_user.id,
    )
    db.add(world)
    await db.commit()

    # WITHDRAWN → PRIVATE is not a valid transition — owner cannot self-recover.
    with pytest.raises(ValueError, match="Invalid withdraw"):
        await withdraw_world(
            db, world_id=world.id, actor_user_id=sample_user.id, by_admin=False
        )


# ---------------------------------------------------------------------------
# Save as private (owner-only, playable) + private → public
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_world_as_private_creates_private_world(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    world = await save_world_as_private(db, draft_id=draft.id, actor_user_id=sample_user.id)

    assert world.status == ContentStatus.PRIVATE
    assert world.name == "Test World"
    assert world.created_by_user_id == sample_user.id
    await db.refresh(draft)
    assert draft.world_id == world.id


@pytest.mark.asyncio
async def test_save_world_as_private_then_publish(db, sample_user):
    """The private → public path: a saved private world can later be published."""
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    private_world = await save_world_as_private(
        db, draft_id=draft.id, actor_user_id=sample_user.id
    )
    assert private_world.status == ContentStatus.PRIVATE

    published = await publish_world_draft(
        db, draft_id=draft.id, actor_user_id=sample_user.id
    )
    assert published.id == private_world.id  # same row, flipped status
    assert published.status == ContentStatus.PUBLISHED


@pytest.mark.asyncio
async def test_save_world_as_private_rejects_non_owner(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()

    other = User(nickname="intruder", is_admin=False)
    db.add(other)
    await db.commit()

    with pytest.raises(PermissionError):
        await save_world_as_private(db, draft_id=draft.id, actor_user_id=other.id)


@pytest.mark.asyncio
async def test_save_script_as_private_creates_unpublished_script(db, sample_user, sample_world):
    draft = ScriptDraft(
        world_id=sample_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    script = await save_script_as_private(db, draft_id=draft.id, actor_user_id=sample_user.id)

    assert script.status == ContentStatus.PRIVATE
    # is_published is the runtime gate — a private script must NOT be public.
    assert script.is_published is False
    assert script.created_by_user_id == sample_user.id


# ---------------------------------------------------------------------------
# Review flow (P2): submit / approve / reject + script dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_world_then_approve_publishes(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()
    await save_world_as_private(db, draft_id=draft.id, actor_user_id=sample_user.id)

    submitted = await submit_world_for_review(db, draft_id=draft.id, actor_user_id=sample_user.id)
    assert submitted.review_status == "submitted"

    world = await approve_world_draft(db, draft_id=draft.id)
    assert world.status == ContentStatus.PUBLISHED
    await db.refresh(draft)
    # review state cleared after approval
    assert draft.review_status == "editing"


@pytest.mark.asyncio
async def test_reject_world_sets_rejected_with_note(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()
    await save_world_as_private(db, draft_id=draft.id, actor_user_id=sample_user.id)
    await submit_world_for_review(db, draft_id=draft.id, actor_user_id=sample_user.id)

    rejected = await reject_world_draft(db, draft_id=draft.id, note="设定不够清晰")
    assert rejected.review_status == "rejected"
    assert rejected.review_note == "设定不够清晰"


@pytest.mark.asyncio
async def test_withdraw_submission_returns_to_editing(db, sample_user):
    draft = WorldDraft(payload=_world_draft_payload(), created_by_user_id=sample_user.id)
    db.add(draft)
    await db.commit()
    await save_world_as_private(db, draft_id=draft.id, actor_user_id=sample_user.id)
    await submit_world_for_review(db, draft_id=draft.id, actor_user_id=sample_user.id)

    draft = await withdraw_world_submission(db, draft_id=draft.id, actor_user_id=sample_user.id)
    assert draft.review_status == "editing"


@pytest.mark.asyncio
async def test_submit_script_requires_published_world(db, sample_user):
    """A script can only be submitted when its world is already published."""
    # private (unpublished) world
    private_world = World(
        name="私有世界", description="d", genre="g", era="e", difficulty=3,
        estimated_time="30", base_setting="b", status="private",
        created_by_user_id=sample_user.id,
    )
    db.add(private_world)
    await db.flush()
    draft = ScriptDraft(
        world_id=private_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    with pytest.raises(ValueError, match="请先发布所属世界"):
        await submit_script_for_review(db, draft_id=draft.id, actor_user_id=sample_user.id)


@pytest.mark.asyncio
async def test_submit_script_succeeds_with_published_world(db, sample_user, sample_world):
    # sample_world fixture is status="published"
    draft = ScriptDraft(
        world_id=sample_world.id,
        payload=_script_draft_payload(),
        created_by_user_id=sample_user.id,
    )
    db.add(draft)
    await db.commit()

    submitted = await submit_script_for_review(db, draft_id=draft.id, actor_user_id=sample_user.id)
    assert submitted.review_status == "submitted"


# ---- voice_style / gender must survive draft normalization (regression) ----

from services.publish_service import normalize_world_payload, _coerce_world_character  # noqa: E402


@pytest.mark.no_db
def test_coerce_world_character_forwards_voice_style_and_gender():
    out = _coerce_world_character(
        {"name": "苏无名", "personality": "沉稳", "voice_style": "自称在下，口头禅此事蹊跷", "gender": "男"}
    )
    assert out["voice_style"] == "自称在下，口头禅此事蹊跷"
    assert out["gender"] == "男"


@pytest.mark.no_db
def test_normalize_world_payload_preserves_voice_style():
    """voice_style 生成阶段产出后必须穿过写库归一化，否则 NPC 失去专属口吻。"""
    payload = {
        "name": "唐朝诡事录",
        "world_characters": [
            {"name": "苏无名", "personality": "x", "voice_style": "VS-A", "gender": "男"},
            {"name": "卢凌风", "personality": "y", "voice_style": "VS-B"},
        ],
        "character_images": {"苏无名": "http://oss/su.png"},
    }
    out = normalize_world_payload(payload)
    by_name = {c["name"]: c for c in out["world_characters"]}
    assert by_name["苏无名"]["voice_style"] == "VS-A"
    assert by_name["卢凌风"]["voice_style"] == "VS-B"
    assert by_name["苏无名"]["avatar"] == "http://oss/su.png"  # avatar 注入未受影响


@pytest.mark.no_db
def test_normalize_world_payload_preserves_visual_style():
    payload = {
        "name": "甄嬛传",
        "visual_style": {
            "version": 1,
            "genre_category": "古风宫廷",
            "culture": "中式古典",
            "art_style": "古籍绣像",
        },
    }
    out = normalize_world_payload(payload)
    assert out["visual_style"]["art_style"] == "古籍绣像"


@pytest.mark.no_db
def test_normalize_world_payload_does_not_let_placeholder_override_real_avatar():
    payload = {
        "name": "权力的游戏",
        "world_characters": [
            {
                "name": "琼恩·雪诺",
                "personality": "x",
                "avatar": "https://oss.test/characters/jon.png",
            }
        ],
        "character_images": {"琼恩·雪诺": "/static/placeholder-cover.png"},
    }
    out = normalize_world_payload(payload)
    assert out["world_characters"][0]["avatar"] == "https://oss.test/characters/jon.png"
