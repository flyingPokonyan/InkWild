import uuid

import pytest

from api import admin as admin_api
from config import settings
from models.generation_task import GenerationTask
from models.user import User
from services.generation_task_service import GenerationTaskLimitExceeded, GenerationTaskService


def _generation_task(user_id: str, status: str) -> GenerationTask:
    return GenerationTask(
        kind="world",
        draft_type="world_draft",
        draft_id=str(uuid.uuid4()),
        status=status,
        request_payload={"user_id": user_id},
        created_by_user_id=user_id,
        current_phase="boot",
        current_code="task_created",
        current_message="生成任务已创建",
        last_event_seq=1,
    )


def _service(test_session_factory) -> GenerationTaskService:
    return GenerationTaskService(
        session_factory=test_session_factory,
        world_creator_factory=lambda: None,
        normalize_world_payload=lambda payload: payload,
        normalize_script_payload=lambda payload: payload,
    )


@pytest.mark.asyncio
async def test_generation_task_limit_counts_active_tasks_for_current_admin(
    db, test_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "generation_task_active_limit_per_user", 2)
    admin = User(nickname="admin", is_admin=True)
    other_admin = User(nickname="other", is_admin=True)
    db.add_all([admin, other_admin])
    await db.flush()
    db.add_all(
        [
            _generation_task(str(admin.id), "pending"),
            _generation_task(str(admin.id), "running"),
            _generation_task(str(admin.id), "succeeded"),
            _generation_task(str(other_admin.id), "running"),
        ]
    )
    await db.commit()

    with pytest.raises(GenerationTaskLimitExceeded) as exc:
        await _service(test_session_factory)._enforce_generation_task_limit(db, str(admin.id))

    http_error = admin_api._generation_task_limit_error(exc.value)
    assert http_error.status_code == 429
    assert http_error.headers == {"Retry-After": "30"}
    assert http_error.detail["code"] == "GENERATION_TASK_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_generation_task_limit_allows_less_than_configured_active_tasks(
    db, test_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "generation_task_active_limit_per_user", 2)
    admin = User(nickname="admin", is_admin=True)
    db.add(admin)
    await db.flush()
    db.add(_generation_task(str(admin.id), "running"))
    await db.commit()

    await _service(test_session_factory)._enforce_generation_task_limit(db, str(admin.id))
