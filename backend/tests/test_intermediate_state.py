"""Tests for Task 1.10: GenerationTaskService.record_intermediate + v2 agent injection.

Tests verify:
1. record_intermediate creates initial state from None → {phase: snapshot}
2. record_intermediate merges multiple phases without overwriting others
3. record_intermediate overwrites the same phase on re-run
4. Unknown task_id raises an exception
5. Integration: v2 agent records research_pack intermediate state after running
"""
import pytest
import uuid
from sqlalchemy import select

from models.generation_task import GenerationTask
from models.draft import WorldDraft
from models.user import User


@pytest.fixture
async def gen_user(db):
    """A plain user suitable for seeding generation tasks in this module."""
    user = User(nickname="gen_tester", is_admin=False)
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_record_intermediate_creates_initial_state(generation_task_service, db, test_session_factory, gen_user):
    """首次 record 时 intermediate_state 从 None → {phase: snapshot}"""
    draft_id, task_id = await generation_task_service.start_world_generation(
        description="x", genre="", era="", user_id=str(gen_user.id),
    )

    await generation_task_service.record_intermediate(
        task_id, phase="research_pack", snapshot={"passages": [], "summary": ""}
    )

    async with test_session_factory() as session:
        task = (await session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )).scalar_one()
        assert task.intermediate_state == {"research_pack": {"passages": [], "summary": ""}}


@pytest.mark.asyncio
async def test_record_intermediate_merges_multiple_phases(generation_task_service, db, test_session_factory, gen_user):
    """连续 record 不同 phase 时 merge 不覆盖。"""
    draft_id, task_id = await generation_task_service.start_world_generation(
        description="x", genre="", era="", user_id=str(gen_user.id),
    )

    await generation_task_service.record_intermediate(
        task_id, phase="research_pack", snapshot={"summary": "s1"}
    )
    await generation_task_service.record_intermediate(
        task_id, phase="lore_pack", snapshot={"dimensions": [{"key": "tech"}]}
    )

    async with test_session_factory() as session:
        task = (await session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )).scalar_one()
        assert "research_pack" in task.intermediate_state
        assert "lore_pack" in task.intermediate_state
        assert task.intermediate_state["research_pack"]["summary"] == "s1"
        assert task.intermediate_state["lore_pack"]["dimensions"] == [{"key": "tech"}]


@pytest.mark.asyncio
async def test_record_intermediate_overwrites_same_phase(generation_task_service, db, test_session_factory, gen_user):
    """同 phase 第二次 record 覆盖第一次（同 phase 重做的语义）。"""
    draft_id, task_id = await generation_task_service.start_world_generation(
        description="x", genre="", era="", user_id=str(gen_user.id),
    )

    await generation_task_service.record_intermediate(
        task_id, phase="research_pack", snapshot={"v": 1}
    )
    await generation_task_service.record_intermediate(
        task_id, phase="research_pack", snapshot={"v": 2}
    )

    async with test_session_factory() as session:
        task = (await session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )).scalar_one()
        assert task.intermediate_state["research_pack"] == {"v": 2}


@pytest.mark.asyncio
async def test_record_intermediate_unknown_task_raises(generation_task_service, db):
    """未知 task_id 应抛错（NoResultFound）。"""
    fake_id = str(uuid.uuid4())
    with pytest.raises(Exception):
        await generation_task_service.record_intermediate(
            fake_id, phase="x", snapshot={}
        )


@pytest.mark.asyncio
async def test_v2_agent_records_research_pack_intermediate(monkeypatch, generation_task_service, db, test_session_factory, gen_user):
    """集成测试：v2 agent 跑完 research_pack 阶段后，intermediate_state.research_pack 应被写入。"""
    import config
    monkeypatch.setattr(config.settings, "world_creator_v2_enabled", True)

    draft_id, task_id = await generation_task_service.start_world_generation(
        description="测试 IP 复刻", genre="", era="", user_id=str(gen_user.id),
    )

    # mock v2 agent 的 build_research_pack 返回固定 pack
    from schemas.research_pack import IPCanon, Passage, ResearchPack
    fake_pack = ResearchPack(
        summary="固定摘要",
        passages=[Passage(id="p1", text="x", tags=[], source="admin_note")],
        ip_canon=IPCanon(canonical_names=["A"]),
    )

    async def fake_build(*args, **kwargs):
        return fake_pack

    monkeypatch.setattr("services.research_pack_builder.build_research_pack", fake_build)
    monkeypatch.setattr("services.world_creator_agent_v2.build_research_pack", fake_build)

    # We also need world_creator_factory to return something non-None
    # so v2 can steal its attributes. Use a minimal stub.
    from unittest.mock import MagicMock, AsyncMock
    stub_agent = MagicMock()
    stub_agent.llm = MagicMock()
    stub_agent.image_gen = None
    stub_agent.research_broker = MagicMock()

    monkeypatch.setattr(generation_task_service, "world_creator_factory", lambda: stub_agent)

    # 让 generation_task_service 跑完 v2
    await generation_task_service._run_world_generation(task_id)

    async with test_session_factory() as session:
        task = (await session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )).scalar_one()
        assert task.intermediate_state is not None
        assert "research_pack" in task.intermediate_state
        rp = task.intermediate_state["research_pack"]
        assert rp["summary"] == "固定摘要"
        assert "canonical_names" in rp.get("ip_canon", {})
