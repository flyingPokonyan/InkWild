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


class FakeStartService:
    def __init__(self):
        self.called_with = None

    async def start_game(self, db, player_id, world_id, character_id, mode, script_id=None, authors_note=None, force_abandon_session_id=None):
        self.called_with = (player_id, world_id, character_id, mode, script_id, authors_note)
        yield {"type": "session_created", "session_id": "sess-1"}
        yield {"type": "done"}


class FakeRetryService:
    def __init__(self):
        self.called_with = None

    async def retry_action(self, db, user_id, session_id):
        self.called_with = (user_id, session_id)
        yield {"type": "narrative", "text": "重试中。"}
        yield {"type": "done"}


@pytest.mark.asyncio
async def test_start_game_passes_script_fields(client, monkeypatch):
    service = FakeStartService()
    monkeypatch.setattr("api.game.get_game_service", lambda: service)

    response = await client.post(
        "/api/game/start",
        headers={"X-Player-Id": "test-player"},
        json={
            "world_id": "world-1",
            "character_id": "character-1",
            "mode": "script",
            "script_id": "script-1",
            "authors_note": "保持悬疑。",
        },
    )

    assert response.status_code == 200
    assert "event: session_created" in response.text
    assert service.called_with == ("test-user", "world-1", "character-1", "script", "script-1", "保持悬疑。")


@pytest.mark.asyncio
async def test_retry_game_streams_response(client, monkeypatch):
    service = FakeRetryService()
    monkeypatch.setattr("api.game.get_game_service", lambda: service)

    response = await client.post(
        "/api/game/session-1/retry",
        headers={"X-Player-Id": "test-player"},
    )

    assert response.status_code == 200
    assert "event: narrative" in response.text
    assert "event: done" in response.text
    assert service.called_with == ("test-user", "session-1")
