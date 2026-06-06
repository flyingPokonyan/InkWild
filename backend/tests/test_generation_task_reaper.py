"""BUGS #17 — verify stale-task reaper kills zombies before quota check."""
import uuid
from datetime import timedelta

import pytest

from models.generation_task import GenerationTask
from models.user import User
from services.generation_task_service import (
    GenerationTaskService,
    STALE_TASK_AFTER_SECONDS,
)
from utils import utcnow


def _service(test_session_factory) -> GenerationTaskService:
    return GenerationTaskService(
        session_factory=test_session_factory,
        world_creator_factory=lambda: None,
        normalize_world_payload=lambda payload: payload,
        normalize_script_payload=lambda payload: payload,
    )


def _task(user_id: str, status: str, *, updated_at) -> GenerationTask:
    return GenerationTask(
        kind="world",
        draft_type="world_draft",
        draft_id=str(uuid.uuid4()),
        status=status,
        request_payload={},
        created_by_user_id=user_id,
        last_event_seq=0,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_stale_running_task_is_marked_failed(db, test_session_factory):
    user = User(nickname="creator")
    db.add(user)
    await db.flush()

    stale_ts = utcnow() - timedelta(seconds=STALE_TASK_AFTER_SECONDS + 60)
    fresh_ts = utcnow()
    stale = _task(str(user.id), "running", updated_at=stale_ts)
    fresh = _task(str(user.id), "running", updated_at=fresh_ts)
    db.add_all([stale, fresh])
    await db.commit()

    reaped = await _service(test_session_factory)._reap_stale_tasks(db, user_id=str(user.id))
    await db.commit()

    await db.refresh(stale)
    await db.refresh(fresh)
    assert reaped == 1
    assert stale.status == "failed"
    assert "reaped" in (stale.error_message or "")
    assert stale.finished_at is not None
    assert fresh.status == "running"


@pytest.mark.asyncio
async def test_reaper_no_op_when_no_stale_tasks(db, test_session_factory):
    user = User(nickname="creator")
    db.add(user)
    await db.flush()
    db.add(_task(str(user.id), "running", updated_at=utcnow()))
    await db.commit()

    reaped = await _service(test_session_factory)._reap_stale_tasks(db, user_id=str(user.id))
    assert reaped == 0


@pytest.mark.asyncio
async def test_reaper_scoped_to_user(db, test_session_factory):
    a = User(nickname="a")
    b = User(nickname="b")
    db.add_all([a, b])
    await db.flush()
    stale_ts = utcnow() - timedelta(seconds=STALE_TASK_AFTER_SECONDS + 60)
    task_a = _task(str(a.id), "running", updated_at=stale_ts)
    task_b = _task(str(b.id), "running", updated_at=stale_ts)
    db.add_all([task_a, task_b])
    await db.commit()

    reaped = await _service(test_session_factory)._reap_stale_tasks(db, user_id=str(a.id))
    await db.commit()
    await db.refresh(task_a)
    await db.refresh(task_b)
    assert reaped == 1
    assert task_a.status == "failed"
    assert task_b.status == "running"  # b's task untouched
