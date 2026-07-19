import hashlib
import json
from datetime import timedelta

import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock

from models.draft import WorldDraft
from models.generation_task import GenerationTask
from models.ip_knowledge_pack import IPKnowledgePack
from models.user import User
from models.world_quality_score import WorldQualityScore
from services.world_critic_service import score_world_soft
from services.generation_rubric import compute_blocking_flags
from services.world_quality_scorer import WorldQualityScorer
from services.publish_service import publish_world_draft
from utils import utcnow


class _ScoreLLM:
    def __init__(self, outputs: list[dict]):
        self.outputs = list(outputs)
        self.calls = 0
        self.requests: list[dict] = []

    async def stream_with_tools(self, **kwargs):
        self.requests.append(kwargs)
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        yield {"type": "text_delta", "text": json.dumps(output, ensure_ascii=False)}


def _score(ip: int, collision: int, tension: int = 8) -> dict:
    return {
        "ip_consistency": ip,
        "collision": collision,
        "tension": tension,
        "confidence": 0.9,
        "violations": [],
        "summary": "ok",
    }


def _payload() -> dict:
    return {
        "name": "测试世界",
        "base_setting": "完整设定",
        "locations": [{"name": "地点"}],
        "world_characters": [
            {"name": f"角色{i}", "playable": i < 4, "personality": "不同"}
            for i in range(12)
        ],
        "playable": [{"name": f"角色{i}"} for i in range(4)],
        "events_data": [{"id": "evt_1"}],
        "shared_events": [],
        "cover_image": "/generated/cover.png",
        "hero_image": "/generated/hero.png",
        "quality_warnings": [],
    }


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_soft_quality_uses_one_judge_for_healthy_world():
    llm = _ScoreLLM([_score(9, 8)])
    result = await score_world_soft(_payload(), None, llm)
    assert result["judge_count"] == 1
    assert llm.calls == 1


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_soft_quality_escalates_borderline_to_two_judges():
    llm = _ScoreLLM([_score(6, 7), _score(6, 7)])
    result = await score_world_soft(_payload(), None, llm)
    assert result["judge_count"] == 2
    assert llm.calls == 2


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_soft_quality_uses_third_only_on_disagreement():
    llm = _ScoreLLM([_score(4, 8), _score(8, 8), _score(7, 8)])
    result = await score_world_soft(_payload(), None, llm)
    assert result["judge_count"] == 3
    assert result["ip_consistency"] == 7
    assert llm.calls == 3


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_soft_quality_audits_final_content_spec_and_research_evidence():
    payload = _payload()
    payload["lore_pack"] = {
        "dimensions": [
            {"name": "宫廷秩序", "content_blocks": [{"heading": "后宫", "body": "位份约束"}]}
        ]
    }
    payload["shared_events"] = [
        {"id": "shared_1", "title": "入宫", "summary": "角色进入宫廷", "involved_npcs": ["角色0"]}
    ]
    payload["relations_pack"] = {
        "relations_by_npc": {
            "角色0": [{"target": "角色1", "kind": "宿敌", "trust": -8, "why": "character.initial_peer_relations"}]
        }
    }
    pack = {
        "ip_name": "测试原作",
        "fidelity_mode": "strict",
        "characters": [{"name": "角色0", "role_in_story": "主角", "must_have": True}],
        "passages": [{"id": "p1", "source": "wikipedia", "text": "原作证据"}],
    }
    spec = {"ip_name": "测试原作", "fidelity_mode": "strict"}
    llm = _ScoreLLM([_score(9, 9)])

    await score_world_soft(payload, pack, llm, world_spec=spec)

    audit = json.loads(llm.requests[0]["messages"][0]["content"])
    assert audit["world_spec"]["ip_name"] == "测试原作"
    assert audit["world"]["lore_dimensions"][0]["blocks"][0]["body"] == "位份约束"
    assert audit["world"]["shared_events"][0]["title"] == "入宫"
    assert audit["world"]["characters"][0]["runtime_relations"][0]["kind"] == "宿敌"
    assert audit["research"]["characters"][0]["name"] == "角色0"
    assert audit["research"]["evidence_excerpt"][0]["text"] == "原作证据"


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_major_quality_violation_gets_second_judge_and_blocks_shipping():
    violation = {
        "code": "canon_identity_conflict",
        "severity": "major",
        "target": "world.characters.角色0",
        "detail": "身份与原作冲突",
    }
    output = {**_score(8, 8), "violations": [violation]}
    llm = _ScoreLLM([output, output])

    result = await score_world_soft(_payload(), None, llm)
    flags, shippable = compute_blocking_flags(result)

    assert result["judge_count"] == 2
    assert result["confirmed_violations"][0]["votes"] == 2
    assert "quality:canon_identity_conflict" in flags
    assert shippable is False


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_single_major_violation_is_unconfirmed_when_second_judge_fails():
    violation = {
        "code": "canon_identity_conflict",
        "severity": "major",
        "target": "world.characters.角色0",
        "detail": "身份与原作冲突",
    }
    llm = _ScoreLLM([{**_score(8, 8), "violations": [violation]}, {}])

    result = await score_world_soft(_payload(), None, llm)
    flags, shippable = compute_blocking_flags(result)

    assert result["confirmed_violations"] == []
    assert result["unconfirmed_violations"][0]["votes"] == 1
    assert "quality_review:canon_identity_conflict" in flags
    assert shippable is False


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_equivalent_violation_wording_reaches_consensus_by_fixed_category():
    first = {
        **_score(8, 8),
        "violations": [{
            "code": "missing_core_peer_relations",
            "severity": "major",
            "target": "characters.甲",
            "detail": "缺核心关系",
        }],
    }
    second = {
        **_score(8, 8),
        "violations": [{
            "code": "core_relation_missing",
            "severity": "major",
            "target": "relations_pack.甲",
            "detail": "运行时关系图缺失",
        }],
    }
    llm = _ScoreLLM([first, second])

    result = await score_world_soft(_payload(), None, llm)

    assert result["judge_count"] == 2
    assert result["confirmed_violations"][0]["code"] == "canon_relation_conflict"
    assert result["confirmed_violations"][0]["votes"] == 2


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_optional_canon_pool_omission_cannot_become_major():
    output = {
        **_score(8, 8),
        "violations": [{
            "code": "canon_entity_missing",
            "severity": "major",
            "target": "characters.可选配角",
            "detail": "正典池中的可选配角没有进入最终世界",
        }],
    }
    llm = _ScoreLLM([output])
    spec = {
        "must_have_characters": ["角色0"],
        "canon_characters": ["角色0", "可选配角"],
        "scale": {"active_roles_target": 12},
    }

    result = await score_world_soft(_payload(), None, llm, world_spec=spec)

    assert result["judge_count"] == 1
    assert result["confirmed_violations"][0]["severity"] == "warning"


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_underfilled_world_can_keep_missing_entity_major():
    output = {
        **_score(8, 8),
        "violations": [{
            "code": "canon_entity_missing",
            "severity": "major",
            "target": "world_characters",
            "detail": "最终角色数量低于冻结规模",
        }],
    }
    llm = _ScoreLLM([output, output])
    spec = {
        "must_have_characters": ["角色0"],
        "canon_characters": ["角色0", "可选配角"],
        "scale": {"active_roles_target": 20},
    }

    result = await score_world_soft(_payload(), None, llm, world_spec=spec)

    assert result["judge_count"] == 2
    assert result["confirmed_violations"][0]["severity"] == "major"


@pytest.mark.asyncio
async def test_quality_job_is_idempotent_versioned_and_durable(
    db, test_session_factory, monkeypatch
):
    user = User(nickname="quality")
    db.add(user)
    await db.flush()
    payload = _payload()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    draft = WorldDraft(
        payload=payload,
        payload_revision=1,
        payload_hash=payload_hash,
        quality_status="pending",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        generation_run_id="11111111-1111-1111-1111-111111111111",
        kind="world",
        draft_type="world_draft",
        draft_id=draft.id,
        created_by_user_id=user.id,
        request_payload={},
        status="succeeded",
        payload_revision=1,
        payload_hash=payload_hash,
    )
    db.add(task)
    await db.commit()

    monkeypatch.setattr(
        "services.world_quality_scorer.score_world_soft",
        AsyncMock(return_value={**_score(9, 9), "judge_count": 1}),
    )
    scorer = WorldQualityScorer(test_session_factory, object())
    first = await scorer.enqueue(str(task.id))
    second = await scorer.enqueue(str(task.id))
    assert first is not None
    assert second is None
    await scorer.run_job(first)

    async with test_session_factory() as session:
        row = await session.get(WorldQualityScore, first)
        saved_draft = await session.get(WorldDraft, draft.id)
        rows = (await session.execute(select(WorldQualityScore))).scalars().all()
    assert len(rows) == 1
    assert row.status == "passed"
    assert row.payload_revision == 1
    assert row.payload_hash == payload_hash
    assert saved_draft.quality_status == "passed"


@pytest.mark.asyncio
async def test_quality_job_uses_latest_ip_pack_for_regenerated_draft(
    db, test_session_factory, monkeypatch
):
    user = User(nickname="quality-latest-pack")
    db.add(user)
    await db.flush()
    payload = _payload()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    draft = WorldDraft(
        payload=payload,
        payload_revision=1,
        payload_hash=payload_hash,
        quality_status="pending",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        generation_run_id="22222222-2222-2222-2222-222222222222",
        kind="world",
        draft_type="world_draft",
        draft_id=draft.id,
        created_by_user_id=user.id,
        request_payload={},
        status="succeeded",
        payload_revision=1,
        payload_hash=payload_hash,
    )
    db.add(task)
    db.add_all(
        [
            IPKnowledgePack(
                draft_id=draft.id,
                ip_name="旧版本",
                fidelity_mode="strict",
                pack_json={"characters": [{"name": "不存在的旧角色", "must_have": True}]},
                created_at=utcnow() - timedelta(minutes=1),
            ),
            IPKnowledgePack(
                draft_id=draft.id,
                ip_name="新版本",
                fidelity_mode="strict",
                pack_json={"characters": [{"name": "角色0", "must_have": True}]},
                created_at=utcnow(),
            ),
        ]
    )
    await db.commit()

    monkeypatch.setattr(
        "services.world_quality_scorer.score_world_soft",
        AsyncMock(return_value={**_score(9, 9), "judge_count": 1}),
    )
    scorer = WorldQualityScorer(test_session_factory, object())
    job_id = await scorer.enqueue(str(task.id))
    await scorer.run_job(job_id)

    async with test_session_factory() as session:
        row = await session.get(WorldQualityScore, job_id)
    assert row.must_have_total == 1
    assert row.must_have_covered == 1
    assert row.detail["must_have_names"] == ["角色0"]


@pytest.mark.asyncio
async def test_failed_generation_task_never_enqueues_quality_job(db, test_session_factory):
    user = User(nickname="quality-failed-task")
    db.add(user)
    await db.flush()
    draft = WorldDraft(
        payload=_payload(),
        payload_revision=1,
        payload_hash="b" * 64,
        quality_status="pending",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        generation_run_id="33333333-3333-3333-3333-333333333333",
        kind="world",
        draft_type="world_draft",
        draft_id=draft.id,
        created_by_user_id=user.id,
        request_payload={},
        status="failed",
        payload_revision=1,
        payload_hash=draft.payload_hash,
    )
    db.add(task)
    await db.commit()

    scorer = WorldQualityScorer(test_session_factory, None)
    assert await scorer.enqueue(str(task.id)) is None

    rows = (await db.execute(select(WorldQualityScore))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_strict_ip_task_without_pack_is_not_shippable(db, test_session_factory):
    user = User(nickname="quality-missing-pack")
    db.add(user)
    await db.flush()
    payload = _payload()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    draft = WorldDraft(
        payload=payload,
        payload_revision=1,
        payload_hash=payload_hash,
        quality_status="pending",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        generation_run_id="44444444-4444-4444-4444-444444444444",
        kind="world",
        draft_type="world_draft",
        draft_id=draft.id,
        created_by_user_id=user.id,
        request_payload={},
        status="succeeded",
        world_spec={"ip_name": "测试原作", "fidelity_mode": "strict"},
        payload_revision=1,
        payload_hash=payload_hash,
    )
    db.add(task)
    await db.commit()

    scorer = WorldQualityScorer(test_session_factory, None)
    job_id = await scorer.enqueue(str(task.id))
    assert job_id is not None
    await scorer.run_job(job_id, run_soft=False)

    async with test_session_factory() as session:
        row = await session.get(WorldQualityScore, job_id)
    assert row.status == "needs_review"
    assert row.shippable is False
    assert "strict_ip_pack_missing" in row.blocking_flags


@pytest.mark.asyncio
async def test_public_publish_rejects_unchecked_current_revision(db):
    user = User(nickname="quality-gate")
    db.add(user)
    await db.flush()
    draft = WorldDraft(
        payload=_payload(),
        payload_revision=1,
        payload_hash="a" * 64,
        quality_status="pending",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.commit()

    with pytest.raises(ValueError, match="质量门"):
        await publish_world_draft(
            db,
            draft_id=str(draft.id),
            actor_user_id=str(user.id),
        )


@pytest.mark.asyncio
async def test_admin_bypasses_quality_gate(db):
    # Same unchecked/needs_review draft — an admin publisher is NOT blocked.
    user = User(nickname="admin-owner", is_admin=True)
    db.add(user)
    await db.flush()
    draft = WorldDraft(
        payload=_payload(),
        payload_revision=1,
        payload_hash="b" * 64,
        quality_status="needs_review",
        created_by_user_id=user.id,
    )
    db.add(draft)
    await db.commit()

    world = await publish_world_draft(
        db,
        draft_id=str(draft.id),
        actor_user_id=str(user.id),
        actor_is_admin=True,
    )
    assert world.id is not None
