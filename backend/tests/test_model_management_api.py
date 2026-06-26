import pytest

from services import model_management as model_management_service
from config import settings


MODEL_SLOTS = [
    "game_main",
    "npc_agent",
    "conversation_compression",
    "ending_summary",
    "admin_generation",
    "moderation_slot",
    "intermission",
    "research_planning",
    "research_summary",
    "ip_recognition",
    "image_generation",
]


@pytest.mark.asyncio
async def test_model_management_lists_start_empty(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", False)
    providers_response = await client.get(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
    )
    assert providers_response.status_code == 200
    assert providers_response.json()["data"]["providers"] == []

    models_response = await client.get(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
    )
    assert models_response.status_code == 200
    assert models_response.json()["data"]["models"] == []

    slots_response = await client.get(
        "/api/admin/model-slots",
        cookies=admin_auth_cookies,
    )
    assert slots_response.status_code == 200
    payload = slots_response.json()["data"]["slots"]
    assert [item["slot_name"] for item in payload] == MODEL_SLOTS
    assert all(item["binding"] is None for item in payload)


@pytest.mark.asyncio
async def test_create_provider_and_model_then_list_them(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", False)
    provider_response = await client.post(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
        json={
            "name": "DeepSeek Production",
            "provider_type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key_env_name": "DEEPSEEK_API_KEY",
            "extra_config": {},
        },
    )
    assert provider_response.status_code == 200
    provider_id = provider_response.json()["data"]["provider"]["id"]

    model_response = await client.post(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
        json={
            "provider_id": provider_id,
            "model_id": "deepseek-chat",
            "display_name": "DeepSeek Chat",
            "model_kind": "text",
            "is_enabled": True,
        },
    )
    assert model_response.status_code == 200

    providers_after = await client.get(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
    )
    provider_payload = providers_after.json()["data"]["providers"]
    assert len(provider_payload) == 1
    assert provider_payload[0]["name"] == "DeepSeek Production"
    assert provider_payload[0]["model_count"] == 1

    models_after = await client.get(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
    )
    model_payload = models_after.json()["data"]["models"]
    assert len(model_payload) == 1
    assert model_payload[0]["model_id"] == "deepseek-chat"
    assert model_payload[0]["provider"]["id"] == provider_id


@pytest.mark.asyncio
async def test_bind_slot_runs_capability_validation_and_persists_binding(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", False)

    async def fake_probe(config, capability):
        return "passed", f"{capability}-ok"

    monkeypatch.setattr(model_management_service, "_run_capability_probe", fake_probe)

    provider_response = await client.post(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
        json={
            "name": "DeepSeek Runtime",
            "provider_type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key_env_name": "DEEPSEEK_API_KEY",
            "extra_config": {},
        },
    )
    provider_id = provider_response.json()["data"]["provider"]["id"]

    model_response = await client.post(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
        json={
            "provider_id": provider_id,
            "model_id": "deepseek-chat",
            "display_name": "DeepSeek Chat",
            "model_kind": "text",
            "is_enabled": True,
        },
    )
    model_id = model_response.json()["data"]["model"]["id"]

    bind_response = await client.put(
        "/api/admin/model-slots/game_main",
        cookies=admin_auth_cookies,
        json={"model_id": model_id},
    )
    assert bind_response.status_code == 200
    slot = bind_response.json()["data"]["slot"]
    assert slot["slot_name"] == "game_main"
    assert slot["binding"]["model"]["id"] == model_id

    models_after = await client.get(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
    )
    probes = models_after.json()["data"]["models"][0]["probes"]
    assert probes["chat_basic"]["status"] == "passed"
    assert probes["streaming"]["status"] == "passed"
    assert probes["tool_use"]["status"] == "passed"


@pytest.mark.asyncio
async def test_bind_slot_rejects_wrong_model_kind(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", False)
    provider_response = await client.post(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
        json={
            "name": "Seedream Images",
            "provider_type": "seedream_image",
            "base_url": "https://seedream.example.com/v1",
            "api_key_env_name": "SEEDREAM_API_KEY",
            "extra_config": {},
        },
    )
    provider_id = provider_response.json()["data"]["provider"]["id"]

    model_response = await client.post(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
        json={
            "provider_id": provider_id,
            "model_id": "seedream-v3",
            "display_name": "Seedream V3",
            "model_kind": "image",
            "is_enabled": True,
        },
    )
    model_id = model_response.json()["data"]["model"]["id"]

    bind_response = await client.put(
        "/api/admin/model-slots/game_main",
        cookies=admin_auth_cookies,
        json={"model_id": model_id},
    )
    assert bind_response.status_code == 400
    assert "模型类别" in bind_response.text


@pytest.mark.asyncio
async def test_bootstrap_seeds_current_runtime_models_and_bindings(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek-secret")
    monkeypatch.setattr(settings, "grok_api_key", "grok-secret")
    monkeypatch.setattr(settings, "llm_default_model", "deepseek-chat")
    monkeypatch.setattr(settings, "llm_compression_model", "deepseek-lite")
    monkeypatch.setattr(settings, "grok_model", "grok-4")
    monkeypatch.setattr(settings, "grok_image_model", "grok-imagine")
    # gpt-image is the preferred default for the image_generation slot since the
    # 2026-05 cover-image redesign; set it explicitly so the binding is deterministic.
    monkeypatch.setattr(settings, "gptimage_image_model", "gpt-image-2")
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", True)

    providers_response = await client.get(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
    )
    providers = providers_response.json()["data"]["providers"]
    provider_names = {provider["name"] for provider in providers}
    assert "系统默认 DeepSeek" in provider_names
    assert "系统默认 xAI" in provider_names

    slots_response = await client.get(
        "/api/admin/model-slots",
        cookies=admin_auth_cookies,
    )
    slots = {slot["slot_name"]: slot for slot in slots_response.json()["data"]["slots"]}
    assert slots["game_main"]["binding"]["model"]["model_id"] == "deepseek-chat"
    assert slots["conversation_compression"]["binding"]["model"]["model_id"] == "deepseek-lite"
    assert slots["research_summary"]["binding"]["model"]["model_id"] == "grok-4"
    assert slots["image_generation"]["binding"]["model"]["model_id"] == "gpt-image-2"


@pytest.mark.asyncio
async def test_provider_healthcheck_updates_provider_status(client, admin_auth_cookies, monkeypatch):
    monkeypatch.setattr(settings, "model_management_bootstrap_enabled", False)

    async def fake_probe(config, capability):
        return "passed", f"{capability}-ok"

    monkeypatch.setattr(model_management_service, "_run_capability_probe", fake_probe)

    provider_response = await client.post(
        "/api/admin/model-providers",
        cookies=admin_auth_cookies,
        json={
            "name": "DeepSeek Production",
            "provider_type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "api_key_env_name": "DEEPSEEK_API_KEY",
            "extra_config": {},
        },
    )
    provider_id = provider_response.json()["data"]["provider"]["id"]

    await client.post(
        "/api/admin/provider-models",
        cookies=admin_auth_cookies,
        json={
            "provider_id": provider_id,
            "model_id": "deepseek-chat",
            "display_name": "DeepSeek Chat",
            "model_kind": "text",
            "is_enabled": True,
        },
    )

    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek-secret")
    healthcheck_response = await client.post(
        f"/api/admin/model-providers/{provider_id}/healthcheck",
        cookies=admin_auth_cookies,
    )
    assert healthcheck_response.status_code == 200
    payload = healthcheck_response.json()["data"]
    assert payload["ok"] is True
    assert payload["model_results"][0]["capability"] == "chat_basic"
    assert payload["model_results"][0]["status"] == "passed"
    assert payload["provider"]["status"] == "active"
    assert payload["provider"]["last_healthcheck_at"] is not None


# ─────────── 多 key 池：解析 + masking（纯函数）───────────

from types import SimpleNamespace  # noqa: E402

import services.model_management as mm  # noqa: E402


def _fake_provider(**kw):
    base = dict(
        id="p1", name="P", provider_type="openai_compatible",
        base_url="https://x/v1", api_key_env_name=None, api_keys=[],
        extra_config={}, status="active",
        last_healthcheck_at=None, last_healthcheck_error=None,
        created_at=None, updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_keys_list_prefers_direct():
    p = _fake_provider(api_keys=["sk-aaaa1111", "sk-bbbb2222"], api_key_env_name="DEEPSEEK_API_KEY")
    assert mm._provider_api_keys_list(p) == ["sk-aaaa1111", "sk-bbbb2222"]


def test_keys_list_env_comma_split(monkeypatch):
    monkeypatch.setattr(mm, "_configured_secret_value", lambda name: "k1, k2 ,k3")
    p = _fake_provider(api_keys=[], api_key_env_name="DEEPSEEK_API_KEY")
    assert mm._provider_api_keys_list(p) == ["k1", "k2", "k3"]


def test_keys_list_empty_raises():
    p = _fake_provider(api_keys=[], api_key_env_name=None)
    with pytest.raises(mm.ModelManagementError):
        mm._provider_api_keys_list(p)


def test_serialize_masks_keys():
    p = _fake_provider(api_keys=["sk-secret-abcd", "short"])
    out = mm.serialize_provider(p)
    assert out["api_key_count"] == 2
    assert out["api_key_previews"] == ["sk-…abcd", "…"]
    assert out["api_key_available"] is True
    assert "sk-secret-abcd" not in repr(out)  # 原始 key 绝不出现在序列化结果
