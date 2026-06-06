import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.draft import WorldDraft
from models.generation_task import GenerationTask, GenerationTaskEvent
from models.user import User
from services.generation_task_service import GenerationTaskService

_SEED_USER_ID = str(uuid.uuid4())


def _service(test_session_factory, *, world_creator_factory=None) -> GenerationTaskService:
    return GenerationTaskService(
        session_factory=test_session_factory,
        world_creator_factory=world_creator_factory or (lambda: None),
        normalize_world_payload=lambda payload: payload,
        normalize_script_payload=lambda payload: payload,
    )


def _seed_task(user_id: str = _SEED_USER_ID) -> GenerationTask:
    return GenerationTask(
        kind="world",
        draft_type="world_draft",
        draft_id=str(uuid.uuid4()),
        status="running",
        request_payload={"user_id": user_id},
        created_by_user_id=user_id,
        current_phase="boot",
        current_code="task_created",
        current_message="生成任务已创建",
        last_event_seq=3,
    )


@pytest.mark.asyncio
async def test_record_event_rolls_back_when_insert_fails(db, test_session_factory):
    """commit() failure must roll back: last_event_seq stays put + no new event row."""
    user = User(id=_SEED_USER_ID, nickname="seed", is_admin=False)
    db.add(user)
    await db.flush()
    task = _seed_task()
    db.add(task)
    await db.commit()
    task_id = str(task.id)

    service = _service(test_session_factory)

    # Simulate an IntegrityError thrown at commit time (e.g. unique constraint
    # on (task_id, seq) collides with a concurrent writer).
    fake_commit = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("dup")))

    from sqlalchemy.ext.asyncio import AsyncSession

    with patch.object(AsyncSession, "commit", fake_commit):
        with pytest.raises(IntegrityError):
            await service._record_event(
                task_id,
                {"type": "progress", "phase": "draft", "code": "tick", "message": "x"},
            )

    # Re-read in a fresh session: seq must NOT have advanced and no new event
    # row should exist.
    async with test_session_factory() as session:
        refreshed = await session.get(GenerationTask, task_id)
        assert refreshed is not None
        assert refreshed.last_event_seq == 3

        rows = (
            await session.execute(
                select(GenerationTaskEvent).where(GenerationTaskEvent.task_id == task_id)
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_record_event_commits_on_success(db, test_session_factory):
    """Sanity: when nothing fails, both the event row and the seq bump persist."""
    user = User(id=_SEED_USER_ID, nickname="seed", is_admin=False)
    db.add(user)
    await db.flush()
    task = _seed_task()
    db.add(task)
    await db.commit()
    task_id = str(task.id)

    service = _service(test_session_factory)
    await service._record_event(
        task_id,
        {"type": "progress", "phase": "draft", "code": "tick", "message": "ok"},
    )

    async with test_session_factory() as session:
        refreshed = await session.get(GenerationTask, task_id)
        assert refreshed is not None
        assert refreshed.last_event_seq == 4

        rows = (
            await session.execute(
                select(GenerationTaskEvent).where(GenerationTaskEvent.task_id == task_id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].seq == 4
        assert rows[0].event_name == "progress"


@pytest.mark.asyncio
async def test_run_world_generation_surfaces_factory_failure(db, test_session_factory):
    """If world_creator_factory raises (e.g. slot points to a provider whose
    API-key env var is missing), the failure must be emitted as error+done
    events and flip task.status to failed — never leave the task stuck in
    "running" with no terminal event, which deadlocks the SSE stream."""
    user = User(id=_SEED_USER_ID, nickname="seed", is_admin=False)
    db.add(user)
    await db.flush()
    draft = WorldDraft(payload={}, created_by_user_id=_SEED_USER_ID)
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        kind="world",
        draft_type="world_draft",
        draft_id=str(draft.id),
        status="pending",
        request_payload={"description": "x", "phase": "phase_a", "user_id": _SEED_USER_ID},
        created_by_user_id=_SEED_USER_ID,
        current_phase="boot",
        current_code="task_created",
        current_message="生成任务已创建",
        last_event_seq=1,
    )
    db.add(task)
    await db.commit()
    task_id = str(task.id)

    def exploding_factory():
        raise RuntimeError("环境变量 DEEPSEEK_API_KEY 未配置")

    service = _service(test_session_factory, world_creator_factory=exploding_factory)
    await service._run_world_generation(task_id)

    async with test_session_factory() as session:
        refreshed = await session.get(GenerationTask, task_id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.error_message and "DEEPSEEK_API_KEY" in refreshed.error_message

        rows = (
            await session.execute(
                select(GenerationTaskEvent)
                .where(GenerationTaskEvent.task_id == task_id)
                .order_by(GenerationTaskEvent.seq.asc())
            )
        ).scalars().all()
        event_names = [row.event_name for row in rows]
        assert "error" in event_names
        assert event_names[-1] == "done"
