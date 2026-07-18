import json

import pytest
from sqlalchemy import select

from models.generation_task import (
    GenerationAction,
    GenerationNodeRun,
    GenerationTask,
    GenerationViolation,
)
from models.user import User
from schemas.character_v2 import CharacterRosterEntry
from schemas.world_generation import (
    WorldScaleClass,
    WorldSpec,
    derive_scale_plan,
    estimate_normal_phase_b_calls,
)
from services.world_generation_director import WorldGenerationDirector
from services.world_generation_orchestrator import WorldGenerationOrchestrator
from services.world_generation_orchestrator import GenerationBudgetExceeded
from services.generation_task_service import PHASE_A


class _DirectorLLM:
    async def stream_with_tools(self, **_kwargs):
        yield {
            "type": "text_delta",
            "text": json.dumps(
                {
                    "scale_class": "compact",  # forbidden shrink from epic
                    "active_roles_target": 5,
                    "protagonist_candidates": ["角色1", "不存在"],
                    "creative_focus": ["派系冲突"],
                },
                ensure_ascii=False,
            ),
        }


def test_scale_plan_expands_for_large_worlds():
    compact = derive_scale_plan(canon_character_count=7)
    epic = derive_scale_plan(canon_character_count=29, must_have_count=7, place_count=14)
    assert compact.scale_class == WorldScaleClass.COMPACT
    assert compact.playable_min == 3
    assert epic.scale_class == WorldScaleClass.EPIC
    assert epic.active_roles_target == 29
    assert epic.playable_min == 8
    assert epic.playable_max == 15
    assert estimate_normal_phase_b_calls(compact, dedicated_ip_research=False) <= 16
    assert estimate_normal_phase_b_calls(epic, dedicated_ip_research=True) == 21


def test_character_targets_are_backward_compatible_but_splittable():
    legacy = CharacterRosterEntry(name="甲", role_tag="主角", is_image_target=True)
    split = CharacterRosterEntry(
        name="乙", role_tag="关键视角", playable_role=True, portrait_target=False
    )
    assert legacy.playable_role and legacy.portrait_target
    assert split.playable_role is True
    assert split.portrait_target is False
    assert split.is_image_target is False


@pytest.mark.asyncio
async def test_director_cannot_shrink_safety_baseline():
    canon = [f"角色{i}" for i in range(1, 30)]

    class Pack:
        ip_name = "大世界"
        canon_note = "主线"
        places = [object()] * 12
        playable_archetypes = []

        @staticmethod
        def canon_character_names():
            return canon

        @staticmethod
        def must_have_character_names():
            return canon[:6]

    spec = await WorldGenerationDirector(_DirectorLLM()).plan(
        generation_run_id="run-1",
        description="大世界",
        genre="群像",
        era="",
        fidelity_mode="strict",
        recognized_ip_name="大世界",
        ip_pack=Pack(),
    )
    assert spec.scale.scale_class == WorldScaleClass.EPIC
    assert spec.scale.active_roles_target == 29
    assert spec.protagonist_candidates == ["角色1"]
    # epic budget carries headroom for the inline quality judge + one bounded
    # events revise (see WorldGenerationDirector.plan).
    assert spec.text_call_budget == 28


@pytest.mark.asyncio
async def test_director_preserves_recognized_ip_name_without_pack():
    spec = await WorldGenerationDirector(None).plan(
        generation_run_id="run-recognized-ip",
        description="复刻一个已知世界",
        genre="悬疑",
        era="",
        fidelity_mode="strict",
        recognized_ip_name="长安十二时辰",
        ip_pack=None,
    )

    assert spec.ip_name == "长安十二时辰"
    assert spec.fidelity_mode == "strict"


@pytest.mark.asyncio
async def test_orchestrator_rejects_node_before_exceeding_call_budget():
    orchestrator = WorldGenerationOrchestrator(session_factory=None, task_id=None)
    spec = WorldSpec(
        generation_run_id="run-budget",
        description="测试",
        scale=derive_scale_plan(canon_character_count=3),
        text_call_budget=16,
    )
    await orchestrator.set_spec(spec)
    orchestrator.actual_calls = 16

    async def _should_not_run():
        raise AssertionError("budget must stop before node execution")
        yield {}

    with pytest.raises(GenerationBudgetExceeded):
        _ = [
            event
            async for event in orchestrator.stream_node(
                "over_budget", _should_not_run(), estimated_calls=1
            )
        ]


@pytest.mark.asyncio
async def test_orchestrator_actual_call_floor_covers_unmetered_provider_calls():
    orchestrator = WorldGenerationOrchestrator(session_factory=None, task_id=None)

    async def _source():
        yield {"type": "progress", "phase": "ip_research", "code": "completed"}

    events = [
        event
        async for event in orchestrator.stream_node(
            "ip_research", _source(), estimated_calls=4, actual_call_floor=4
        )
    ]

    assert events[-1]["code"] == "completed"
    assert orchestrator.actual_calls == 4


@pytest.mark.asyncio
async def test_orchestrator_persists_reported_calls_when_node_fails():
    orchestrator = WorldGenerationOrchestrator(session_factory=None, task_id=None)

    class _FailedAfterSearch(RuntimeError):
        actual_calls = 2

    async def _source():
        raise _FailedAfterSearch("evidence missing")
        yield {}

    with pytest.raises(_FailedAfterSearch):
        _ = [
            event
            async for event in orchestrator.stream_node(
                "ip_research", _source(), estimated_calls=4, actual_call_floor=4
            )
        ]

    assert orchestrator.actual_calls == 2


@pytest.mark.asyncio
async def test_orchestrator_repairs_and_persists_contract_audit(db, test_session_factory):
    user = User(nickname="workflow")
    db.add(user)
    await db.flush()
    task = GenerationTask(
        generation_run_id="11111111-1111-1111-1111-111111111111",
        root_task_id=None,
        kind="world",
        draft_type="world_draft",
        draft_id="22222222-2222-2222-2222-222222222222",
        created_by_user_id=user.id,
        request_payload={},
    )
    db.add(task)
    await db.commit()

    orchestrator = WorldGenerationOrchestrator(
        session_factory=test_session_factory, task_id=str(task.id)
    )
    await orchestrator.initialize()
    scale = derive_scale_plan(canon_character_count=8)
    spec = WorldSpec(
        generation_run_id=orchestrator.generation_run_id,
        description="测试",
        scale=scale,
    )
    await orchestrator.set_spec(spec)

    async def _node_stream():
        yield {"type": "progress", "phase": "test"}

    assert [event async for event in orchestrator.stream_node(
        "test_node", _node_stream(), estimated_calls=0
    )]
    chars = [
        {
            "name": f"角色{i}",
            "initial_location": "新地点" if i == 1 else "旧地点",
            "schedule": {},
        }
        for i in range(1, 9)
    ]
    chars.append({"name": "角色8", "initial_location": "旧地点", "schedule": {}})
    payload = {
        "name": "测试世界",
        "locations": [{"name": "旧地点", "description": ""}],
        "world_characters": chars,
        "playable": [{"name": f"角色{i}"} for i in range(1, 4)],
        "events_data": [{"id": f"evt_{i}"} for i in range(3)],
        "cover_image": "/cover.png",
        "hero_image": "/hero.png",
    }
    await orchestrator.validate_and_repair_payload(payload, final=True)
    assert len(payload["world_characters"]) == 8
    assert "新地点" in {loc["name"] for loc in payload["locations"]}

    async with test_session_factory() as session:
        node_runs = (await session.execute(select(GenerationNodeRun))).scalars().all()
        actions = (await session.execute(select(GenerationAction))).scalars().all()
        violations = (await session.execute(select(GenerationViolation))).scalars().all()
    assert len(node_runs) == 1
    assert node_runs[0].status == "succeeded"
    assert any(a.action_type == "repair" for a in actions)
    assert {v.code for v in violations} >= {
        "character_name_duplicate",
        "location_reference_unknown",
    }
    assert all(v.resolved for v in violations)


@pytest.mark.asyncio
async def test_phase_a_and_b_share_generation_run_identity(
    db, test_session_factory, generation_task_service
):
    user = User(nickname="run-chain")
    db.add(user)
    await db.commit()
    draft_id, phase_a_id = await generation_task_service.start_world_generation(
        description="测试", user_id=str(user.id), phase=PHASE_A
    )
    phase_b_id = await generation_task_service.start_world_phase_b_task(
        draft_id=draft_id,
        description="测试",
        user_id=str(user.id),
        fidelity_mode="none",
    )
    async with test_session_factory() as session:
        phase_a = await session.get(GenerationTask, phase_a_id)
        phase_b = await session.get(GenerationTask, phase_b_id)
    assert phase_a.generation_run_id == phase_b.generation_run_id
    assert phase_a.root_task_id == phase_a.id
    assert phase_b.root_task_id == phase_a.id
    assert phase_b.parent_task_id == phase_a.id
