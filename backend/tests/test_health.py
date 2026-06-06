from unittest.mock import AsyncMock

import pytest

import main


pytestmark = pytest.mark.no_db


async def test_health_returns_component_status(monkeypatch, client):
    monkeypatch.setattr(main, "check_database", AsyncMock(return_value="ok"))
    monkeypatch.setattr(main, "check_redis", AsyncMock(return_value="ok"))

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "components": {
            "database": "ok",
            "redis": "ok",
        },
    }


async def test_health_returns_503_when_dependency_fails(monkeypatch, client):
    monkeypatch.setattr(main, "check_database", AsyncMock(return_value="ok"))
    monkeypatch.setattr(main, "check_redis", AsyncMock(side_effect=RuntimeError("redis down")))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "degraded",
        "components": {
            "database": "ok",
            "redis": "error",
        },
    }
