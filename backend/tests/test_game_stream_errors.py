import pytest

from dependencies import get_current_user
from main import app
from models.user import User


@pytest.fixture(autouse=True)
def override_current_user():
    async def fake_current_user():
        return User(id="test-user", nickname="Tester", avatar_url=None)

    app.dependency_overrides[get_current_user] = fake_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


class FailingStartService:
    async def start_game(self, db, player_id, world_id, character_id, mode, script_id=None, authors_note=None, force_abandon_session_id=None):
        yield {"type": "session_created", "session_id": "sess-1"}
        raise RuntimeError("upstream 502")


class NonSerializableDoneService:
    async def start_game(self, db, player_id, world_id, character_id, mode, script_id=None, authors_note=None, force_abandon_session_id=None):
        yield {"type": "session_created", "session_id": "sess-1"}
        yield {"type": "narrative", "text": "开场仍然正常输出。"}
        yield {"type": "done", "new_state": object()}


@pytest.mark.asyncio
async def test_start_game_stream_returns_error_event_when_provider_fails(client, monkeypatch):
    monkeypatch.setattr("api.game.get_game_service", lambda: FailingStartService())

    response = await client.post(
        "/api/game/start",
        headers={"X-Player-Id": "test-player"},
        json={
            "world_id": "world-1",
            "character_id": "character-1",
            "mode": "script",
        },
    )

    assert response.status_code == 200
    assert "event: session_created" in response.text
    assert 'event: error' in response.text
    assert "LLM 服务暂时不可用" in response.text
    assert "event: done" in response.text


@pytest.mark.asyncio
async def test_start_game_stream_done_event_does_not_fall_back_to_generic_error(client, monkeypatch):
    monkeypatch.setattr("api.game.get_game_service", lambda: NonSerializableDoneService())

    response = await client.post(
        "/api/game/start",
        headers={"X-Player-Id": "test-player"},
        json={
            "world_id": "world-1",
            "character_id": "character-1",
            "mode": "script",
        },
    )

    assert response.status_code == 200
    assert "event: session_created" in response.text
    assert "开场仍然正常输出。" in response.text
    assert "event: error" not in response.text
    assert "LLM 服务暂时不可用" not in response.text
    assert response.text.count("event: done") == 1
