from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from llm.base import ImageGenerator, LLMProvider, WebSearcher
from llm.deepseek import DeepSeekProvider
from llm.gemini import GeminiImageProvider, GeminiProvider
from llm.grok import GrokProvider
from llm.openai_compatible import OpenAICompatibleImageProvider, OpenAICompatibleProvider
from llm.router import LLMRouter
from llm.seedream import SeedreamImageProvider
from models.model_management import ModelCapabilityProbe, ModelProvider, ModelSlotBinding, ProviderModel
from utils import utcnow


TEXT_MODEL_KIND = "text"
IMAGE_MODEL_KIND = "image"

PROVIDER_TYPES = ("openai_compatible", "xai", "gemini", "seedream_image")
CAPABILITIES = (
    "chat_basic",
    "streaming",
    "tool_use",
    "json_output",
    "image_generation",
    "web_search",
)

SLOT_DEFINITIONS = (
    {
        "slot_name": "game_main",
        "label": "游戏主对话",
        "description": "导演决策、NPC 对话和旁白叙事的主模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming", "tool_use"),
    },
    {
        "slot_name": "npc_agent",
        "label": "NPC 对话（可选廉价档）",
        "description": "NPC 角色发言模型。可绑定较廉价的小模型独立于 game_main，未绑定时自动复用 game_main。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming"),
    },
    {
        "slot_name": "conversation_compression",
        "label": "对话压缩",
        "description": "长会话压缩摘要模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming"),
    },
    {
        "slot_name": "ending_summary",
        "label": "结局总结",
        "description": "生成结局 JSON 总结的模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming", "json_output"),
    },
    {
        "slot_name": "admin_generation",
        "label": "后台生成",
        "description": "世界和剧本生成主链路模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming", "tool_use"),
    },
    {
        "slot_name": "moderation_slot",
        "label": "内容安全审核",
        "description": "玩家输入和模型输出的低成本内容安全分类模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming", "tool_use"),
    },
    {
        "slot_name": "intermission",
        "label": "等待氛围短句",
        "description": "玩家提交输入后、Director 仍在思考时，并行生成 15-25 字的过渡氛围短句给前端做灰色小字，避免空白等待。建议绑廉价快模型（如 deepseek-v4-flash / Haiku）。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming"),
    },
    {
        "slot_name": "research_planning",
        "label": "研究规划",
        "description": "联网研究查询规划模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming", "tool_use"),
    },
    {
        "slot_name": "research_summary",
        "label": "研究摘要",
        "description": "整理搜索结果摘要的模型。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming"),
    },
    {
        "slot_name": "ip_recognition",
        "label": "IP 识别",
        "description": "Stage 0 判断世界描述是否指向已知 IP。需联网（Live Search）能力，建议绑 Grok；未绑定回退 grok-4.3-fast。",
        "model_kind": TEXT_MODEL_KIND,
        "required_capabilities": ("chat_basic", "streaming"),
    },
    {
        "slot_name": "image_generation",
        "label": "图片生成",
        "description": "世界主视觉和角色头像生成模型。",
        "model_kind": IMAGE_MODEL_KIND,
        "required_capabilities": ("image_generation",),
    },
)

SLOT_DEFINITION_BY_NAME = {item["slot_name"]: item for item in SLOT_DEFINITIONS}
DEFAULT_TEXT_SLOT_NAMES = {
    "game_main",
    "conversation_compression",
    "ending_summary",
    "admin_generation",
    "research_planning",
    # intermission slot 现已不再被任何代码解析——思考态过渡短句机制（IntermissionAgent）
    # 已下线，改为蹭 director 流式真实里程碑的演进式进度反馈
    # （docs/plans/play-turn-loading-2026-05.md）。slot 暂留为 vestigial：彻底移除需
    # 同步 bootstrap 绑定 + 既有 DB binding，留作后续 model-admin 清理。
    "intermission",
}
# Realtime game-loop slots: their routers disable model thinking/reasoning
# (reasoning=False) for speed + clean structured output. The full set of slots
# that disable thinking is REASONING_OFF_TEXT_SLOT_NAMES (below); ending_summary
# / research_summary keep the model default where CoT may help quality.
REALTIME_TEXT_SLOT_NAMES = {"game_main", "npc_agent", "intermission"}
# 生成槽：① 关 thinking（reasoning=False）—— 实测 thinking-capable 模型(deepseek-v4-pro)
# 在慢网关(OpenCode)上 CoT 开时会把 token 预算耗在隐藏推理上、正文为空或被截 →
# 批次 JSON 解析失败、事件/角色被静默丢弃(事件数骤减甚至生成失败)。结构化 JSON 生成
# 不需要可见 CoT，关掉更稳更快。② 仍给更长首 token 超时(300s)作余量。
# (2026-05-31：硬证据推翻了"CoT 对生成有帮助"的旧假设——见 [[generation-infra-2026-05-31]])
GENERATION_TEXT_SLOT_NAMES = {"admin_generation", "research_planning"}
# Offline summary slots that also disable thinking. conversation_compression is
# a structured-summary task (CoT never reaches the summary, just burns tokens);
# NPC reflection rides this same router (game_service → orchestrator.
# compression_llm_router), so disabling it here fixes both the compression and
# the reflection CoT leak (~21 reflection calls/session observed leaking in the
# 2026-06 soaks). ending_summary is intentionally NOT included — it produces
# player-facing narrative where visible reasoning may aid quality.
REASONING_OFF_TEXT_SLOT_NAMES = (
    REALTIME_TEXT_SLOT_NAMES
    | GENERATION_TEXT_SLOT_NAMES
    | {"conversation_compression"}
)
GENERATION_FIRST_TOKEN_TIMEOUT_SECONDS = 300.0


def _reasoning_for_slot(slot_name: str) -> bool | None:
    """Thinking on/off for a slot's router. ``False`` disables CoT (realtime,
    generation, compression); ``None`` leaves the model default (e.g.
    ending_summary, research_summary)."""
    return False if slot_name in REASONING_OFF_TEXT_SLOT_NAMES else None


SYSTEM_BOOTSTRAP_SOURCE = "system_bootstrap"
SYSTEM_DEEPSEEK_PROVIDER_NAME = "系统默认 DeepSeek"
SYSTEM_XAI_PROVIDER_NAME = "系统默认 xAI"
SYSTEM_GPTIMAGE_PROVIDER_NAME = "系统默认 gpt-image"


@dataclass
class RuntimeModelConfig:
    provider: ModelProvider
    model: ProviderModel


class ModelManagementError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _serialize_datetime(value) -> str | None:
    return value.isoformat() if value else None


def _settings_api_key_fallback(env_name: str) -> str:
    normalized = env_name.strip().upper()
    mapping = {
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "GROK_API_KEY": settings.grok_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GPTIMAGE_API_KEY": settings.gptimage_api_key,
    }
    return (mapping.get(normalized) or "").strip()


def _resolve_env_file_path() -> Path | None:
    env_file = settings.model_config.get("env_file")
    if not env_file:
        return None
    candidates = [Path(env_file), Path(__file__).resolve().parents[1] / str(env_file)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=4)
def _load_env_file_values_cached(cache_key: tuple[str, int]) -> dict[str, str]:
    path = Path(cache_key[0])
    values: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = raw_value.strip().strip("'").strip('"')
            if key:
                values[key] = value
    except OSError:
        return {}
    return values


def _env_file_values() -> dict[str, str]:
    path = _resolve_env_file_path()
    if not path:
        return {}
    stat = path.stat()
    return _load_env_file_values_cached((str(path.resolve()), int(stat.st_mtime_ns)))


def _configured_secret_value(env_name: str) -> str:
    normalized = env_name.strip()
    if not normalized:
        return ""
    runtime_value = os.getenv(normalized)
    if runtime_value:
        return runtime_value.strip()
    file_value = _env_file_values().get(normalized, "")
    if file_value:
        return file_value.strip()
    return _settings_api_key_fallback(normalized)


def _provider_defaults(provider_type: str) -> dict[str, str | None]:
    if provider_type == "xai":
        return {"base_url": settings.grok_base_url}
    if provider_type == "gemini":
        return {"base_url": settings.gemini_openai_base_url}
    return {"base_url": None}


def _normalize_base_url(provider_type: str, value: str | None) -> str | None:
    if value and value.strip():
        return value.strip().rstrip("/")
    return _provider_defaults(provider_type)["base_url"]


def _ensure_provider_type(provider_type: str) -> str:
    normalized = provider_type.strip()
    if normalized not in PROVIDER_TYPES:
        raise ModelManagementError("不支持的 provider 类型")
    return normalized


def _ensure_model_kind(model_kind: str) -> str:
    normalized = model_kind.strip()
    if normalized not in {TEXT_MODEL_KIND, IMAGE_MODEL_KIND}:
        raise ModelManagementError("不支持的模型类别")
    return normalized


def _ensure_slot(slot_name: str) -> dict:
    slot = SLOT_DEFINITION_BY_NAME.get(slot_name)
    if not slot:
        raise ModelManagementError("未知的模型槽位", status_code=404)
    return slot


def _validate_provider_input(
    provider_type: str,
    base_url: str | None,
    api_key_env_name: str | None,
    api_keys: list[str] | None,
) -> tuple[str | None, str | None, list[str]]:
    normalized_base = _normalize_base_url(provider_type, base_url)
    normalized_env_name = (api_key_env_name or "").strip() or None
    normalized_keys = [k.strip() for k in (api_keys or []) if isinstance(k, str) and k.strip()]
    if not normalized_keys and not normalized_env_name:
        raise ModelManagementError("必须提供至少一个 API Key（直填）或 API Key 环境变量名")
    if provider_type in {"openai_compatible", "seedream_image"} and not normalized_base:
        raise ModelManagementError("当前 provider 类型必须提供 Base URL")
    return normalized_base, normalized_env_name, normalized_keys


def _provider_supports_model_kind(provider_type: str, model_kind: str) -> bool:
    if provider_type == "seedream_image":
        return model_kind == IMAGE_MODEL_KIND
    return True


def _probe_expiry_deadline():
    return utcnow() + timedelta(hours=settings.model_probe_ttl_hours)


def _latest_probe_map(probes: list[ModelCapabilityProbe]) -> dict[str, ModelCapabilityProbe]:
    latest: dict[str, ModelCapabilityProbe] = {}
    for probe in sorted(probes, key=lambda item: item.verified_at, reverse=True):
        latest.setdefault(probe.capability, probe)
    return latest


def _probe_is_fresh(probe: ModelCapabilityProbe | None) -> bool:
    if not probe:
        return False
    if probe.expires_at is None:
        return True
    return probe.expires_at >= utcnow()


def _derive_model_status(model: ProviderModel, probes: list[ModelCapabilityProbe]) -> str:
    if not model.is_enabled:
        return "disabled"
    latest = _latest_probe_map(probes)
    if not latest:
        return "unverified"
    if all(item.status == "passed" for item in latest.values()):
        return "ready"
    if any(item.status == "passed" for item in latest.values()):
        return "partial"
    return "failed"


def _serialize_probe(probe: ModelCapabilityProbe | None) -> dict | None:
    if not probe:
        return None
    return {
        "capability": probe.capability,
        "status": probe.status,
        "latency_ms": probe.latency_ms,
        "error_message": probe.error_message,
        "response_sample": probe.response_sample,
        "verified_at": _serialize_datetime(probe.verified_at),
        "expires_at": _serialize_datetime(probe.expires_at),
    }


def serialize_provider(provider: ModelProvider, *, model_count: int = 0) -> dict:
    return {
        "id": str(provider.id),
        "name": provider.name,
        "provider_type": provider.provider_type,
        "base_url": provider.base_url,
        "api_key_env_name": provider.api_key_env_name,
        "api_key_previews": (_previews := _provider_key_previews(provider)),
        "api_key_count": len(_previews),
        "api_key_available": bool(_previews),
        "extra_config": provider.extra_config or {},
        "status": provider.status,
        "last_healthcheck_at": _serialize_datetime(provider.last_healthcheck_at),
        "last_healthcheck_error": provider.last_healthcheck_error,
        "model_count": model_count,
        "created_at": _serialize_datetime(provider.created_at),
        "updated_at": _serialize_datetime(provider.updated_at),
    }


def serialize_model(
    model: ProviderModel,
    *,
    provider: ModelProvider,
    probes: list[ModelCapabilityProbe],
    binding_slots: list[str],
) -> dict:
    latest = _latest_probe_map(probes)
    return {
        "id": str(model.id),
        "provider_id": str(model.provider_id),
        "model_id": model.model_id,
        "display_name": model.display_name,
        "model_kind": model.model_kind,
        "is_enabled": model.is_enabled,
        "notes": model.notes,
        "input_price_cents_per_million_tokens": model.input_price_cents_per_million_tokens,
        "output_price_cents_per_million_tokens": model.output_price_cents_per_million_tokens,
        "image_price_cents_per_image": model.image_price_cents_per_image,
        "price_updated_at": _serialize_datetime(model.price_updated_at),
        "status": _derive_model_status(model, probes),
        "binding_slots": binding_slots,
        "provider": serialize_provider(provider),
        "probes": {capability: _serialize_probe(probe) for capability, probe in latest.items()},
        "created_at": _serialize_datetime(model.created_at),
        "updated_at": _serialize_datetime(model.updated_at),
    }


def serialize_slot(
    slot: dict,
    *,
    binding: ModelSlotBinding | None,
    model: ProviderModel | None,
    provider: ModelProvider | None,
) -> dict:
    return {
        "slot_name": slot["slot_name"],
        "label": slot["label"],
        "description": slot["description"],
        "model_kind": slot["model_kind"],
        "required_capabilities": list(slot["required_capabilities"]),
        "binding": (
            {
                "id": str(binding.id),
                "status": binding.status,
                "last_verified_at": _serialize_datetime(binding.last_verified_at),
                "last_verified_error": binding.last_verified_error,
                "model": (
                    {
                        "id": str(model.id),
                        "model_id": model.model_id,
                        "display_name": model.display_name,
                        "model_kind": model.model_kind,
                        "provider": {
                            "id": str(provider.id),
                            "name": provider.name,
                            "provider_type": provider.provider_type,
                        }
                        if provider
                        else None,
                    }
                    if model
                    else None
                ),
            }
            if binding
            else None
        ),
    }


async def _load_providers(db: AsyncSession) -> list[ModelProvider]:
    return (
        await db.execute(select(ModelProvider).order_by(ModelProvider.updated_at.desc()))
    ).scalars().all()


async def _load_models(db: AsyncSession, *, provider_id: str | None = None) -> list[ProviderModel]:
    stmt = select(ProviderModel).order_by(ProviderModel.updated_at.desc())
    if provider_id:
        stmt = stmt.where(ProviderModel.provider_id == provider_id)
    return (await db.execute(stmt)).scalars().all()


async def _load_probes(db: AsyncSession, *, model_ids: list[str]) -> list[ModelCapabilityProbe]:
    if not model_ids:
        return []
    return (
        await db.execute(
            select(ModelCapabilityProbe)
            .where(ModelCapabilityProbe.model_id.in_(model_ids))
            .order_by(ModelCapabilityProbe.verified_at.desc())
        )
    ).scalars().all()


async def _load_bindings(db: AsyncSession) -> list[ModelSlotBinding]:
    return (
        await db.execute(select(ModelSlotBinding).order_by(ModelSlotBinding.slot_name.asc()))
    ).scalars().all()


def _default_bootstrap_specs() -> list[dict]:
    if not settings.model_management_bootstrap_enabled:
        return []

    specs: list[dict] = []
    deepseek_models: dict[tuple[str, str], dict[str, str]] = {}
    if settings.llm_default_model:
        deepseek_models[(settings.llm_default_model, TEXT_MODEL_KIND)] = {
            "model_id": settings.llm_default_model,
            "display_name": "DeepSeek 默认模型",
            "model_kind": TEXT_MODEL_KIND,
        }
    if settings.llm_compression_model:
        deepseek_models[(settings.llm_compression_model, TEXT_MODEL_KIND)] = {
            "model_id": settings.llm_compression_model,
            "display_name": "DeepSeek 压缩模型",
            "model_kind": TEXT_MODEL_KIND,
        }
    if deepseek_models:
        specs.append(
            {
                "provider_name": SYSTEM_DEEPSEEK_PROVIDER_NAME,
                "provider_type": "openai_compatible",
                "base_url": settings.deepseek_base_url,
                "api_key_env_name": "DEEPSEEK_API_KEY",
                "models": list(deepseek_models.values()),
                "slot_models": {
                    "game_main": (settings.llm_default_model, TEXT_MODEL_KIND),
                    "conversation_compression": (settings.llm_compression_model, TEXT_MODEL_KIND),
                    "ending_summary": (settings.llm_default_model, TEXT_MODEL_KIND),
                    "admin_generation": (settings.llm_default_model, TEXT_MODEL_KIND),
                    "research_planning": (settings.llm_default_model, TEXT_MODEL_KIND),
                    # Bound to game_main by default so intermission TTFB filler
                    # is functional out-of-box; admin can rebind to a faster
                    # cheaper model (deepseek-v4-flash / Haiku) when available.
                    "intermission": (settings.llm_default_model, TEXT_MODEL_KIND),
                },
            }
        )

    if settings.gptimage_image_model:
        specs.append(
            {
                "provider_name": SYSTEM_GPTIMAGE_PROVIDER_NAME,
                "provider_type": "openai_compatible",
                "base_url": settings.gptimage_base_url,
                "api_key_env_name": "GPTIMAGE_API_KEY",
                "models": [
                    {
                        "model_id": settings.gptimage_image_model,
                        "display_name": "gpt-image 生图模型",
                        "model_kind": IMAGE_MODEL_KIND,
                    }
                ],
                "slot_models": {
                    "image_generation": (settings.gptimage_image_model, IMAGE_MODEL_KIND),
                },
            }
        )

    xai_models: dict[tuple[str, str], dict[str, str]] = {}
    if settings.grok_model:
        xai_models[(settings.grok_model, TEXT_MODEL_KIND)] = {
            "model_id": settings.grok_model,
            "display_name": "xAI 文本模型",
            "model_kind": TEXT_MODEL_KIND,
        }
    if settings.grok_image_model:
        xai_models[(settings.grok_image_model, IMAGE_MODEL_KIND)] = {
            "model_id": settings.grok_image_model,
            "display_name": "xAI 生图模型",
            "model_kind": IMAGE_MODEL_KIND,
        }
    if xai_models:
        specs.append(
            {
                "provider_name": SYSTEM_XAI_PROVIDER_NAME,
                "provider_type": "xai",
                "base_url": settings.grok_base_url,
                "api_key_env_name": "GROK_API_KEY",
                "models": list(xai_models.values()),
                "slot_models": {
                    "research_summary": (settings.grok_model, TEXT_MODEL_KIND),
                    "image_generation": (settings.grok_image_model, IMAGE_MODEL_KIND),
                },
            }
        )

    return specs


async def ensure_default_model_management_state(db: AsyncSession) -> None:
    specs = _default_bootstrap_specs()
    if not specs:
        return

    providers = await _load_providers(db)
    # 一旦 DB 里有任何 provider，就视为"用户已接管，自己管"，不再每次 list 都 reseed。
    # 之前的实现会把用户删掉的 bootstrap 模型/provider 自动重建回来。
    # 真正的首次安装 (providers == 0) 仍走完整 seed。
    if providers:
        return

    models = await _load_models(db)
    bindings = await _load_bindings(db)
    provider_by_name = {provider.name: provider for provider in providers}
    model_by_identity = {
        (str(model.provider_id), model.model_id, model.model_kind): model
        for model in models
    }
    binding_by_slot = {binding.slot_name: binding for binding in bindings}
    changed = False

    bootstrap_providers = [
        p for p in providers
        if (p.extra_config or {}).get("source") == SYSTEM_BOOTSTRAP_SOURCE
    ]

    for spec in specs:
        provider = provider_by_name.get(spec["provider_name"])
        api_key_available = bool(_configured_secret_value(spec["api_key_env_name"]))
        desired_status = "active" if api_key_available else "invalid"
        extra_config = {"source": SYSTEM_BOOTSTRAP_SOURCE}

        if not provider:
            # User may have renamed the bootstrap provider — find by type + key instead
            renamed = next(
                (p for p in bootstrap_providers
                 if p.provider_type == spec["provider_type"]
                 and p.api_key_env_name == spec["api_key_env_name"]),
                None,
            )
            if renamed:
                provider = renamed
            else:
                provider = ModelProvider(
                    name=spec["provider_name"],
                    provider_type=spec["provider_type"],
                    base_url=_normalize_base_url(spec["provider_type"], spec["base_url"]),
                    api_key_env_name=spec["api_key_env_name"],
                    extra_config=extra_config,
                    status=desired_status,
                )
                db.add(provider)
                await db.flush()
                provider_by_name[provider.name] = provider
                changed = True
        elif (provider.extra_config or {}).get("source") == SYSTEM_BOOTSTRAP_SOURCE:
            normalized_base = _normalize_base_url(spec["provider_type"], spec["base_url"])
            if (
                provider.provider_type != spec["provider_type"]
                or provider.base_url != normalized_base
                or provider.api_key_env_name != spec["api_key_env_name"]
                or provider.status != desired_status
                or (provider.extra_config or {}) != extra_config
            ):
                provider.provider_type = spec["provider_type"]
                provider.base_url = normalized_base
                provider.api_key_env_name = spec["api_key_env_name"]
                provider.status = desired_status
                provider.extra_config = extra_config
                changed = True

        provider_model_lookup: dict[tuple[str, str], ProviderModel] = {}
        for model_spec in spec["models"]:
            identity = (str(provider.id), model_spec["model_id"], model_spec["model_kind"])
            model = model_by_identity.get(identity)
            if not model:
                model = ProviderModel(
                    provider_id=provider.id,
                    model_id=model_spec["model_id"],
                    display_name=model_spec["display_name"],
                    model_kind=model_spec["model_kind"],
                    is_enabled=True,
                )
                db.add(model)
                await db.flush()
                model_by_identity[identity] = model
                changed = True
            provider_model_lookup[(model.model_id, model.model_kind)] = model

        if not api_key_available:
            continue

        for slot_name, model_key in spec["slot_models"].items():
            if slot_name in binding_by_slot:
                continue
            target_model = provider_model_lookup.get(model_key)
            if not target_model:
                continue
            binding = ModelSlotBinding(
                slot_name=slot_name,
                model_id=target_model.id,
                status="active",
                last_verified_at=utcnow(),
                last_verified_error=None,
            )
            db.add(binding)
            binding_by_slot[slot_name] = binding
            changed = True

    if changed:
        await db.commit()


async def list_model_providers(db: AsyncSession) -> dict:
    await ensure_default_model_management_state(db)
    providers = await _load_providers(db)
    models = await _load_models(db)
    counts: dict[str, int] = {}
    for model in models:
        counts[str(model.provider_id)] = counts.get(str(model.provider_id), 0) + 1
    return {
        "providers": [serialize_provider(provider, model_count=counts.get(str(provider.id), 0)) for provider in providers],
        "provider_types": list(PROVIDER_TYPES),
    }


async def create_model_provider(
    db: AsyncSession,
    *,
    name: str,
    provider_type: str,
    base_url: str | None,
    api_key_env_name: str | None,
    api_keys: list[str] | None = None,
    extra_config: dict | None = None,
) -> dict:
    normalized_type = _ensure_provider_type(provider_type)
    normalized_base, normalized_env_name, normalized_keys = _validate_provider_input(
        normalized_type, base_url, api_key_env_name, api_keys
    )
    provider = ModelProvider(
        name=name.strip(),
        provider_type=normalized_type,
        base_url=normalized_base,
        api_key_env_name=normalized_env_name,
        api_keys=normalized_keys,
        extra_config=extra_config or {},
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return serialize_provider(provider, model_count=0)


async def update_model_provider(
    db: AsyncSession,
    provider_id: str,
    *,
    name: str,
    provider_type: str,
    base_url: str | None,
    api_key_env_name: str | None,
    api_keys: list[str] | None = None,
    extra_config: dict | None = None,
    status: str = "active",
) -> dict:
    provider = await db.get(ModelProvider, provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)
    normalized_type = _ensure_provider_type(provider_type)
    normalized_base, normalized_env_name, normalized_keys = _validate_provider_input(
        normalized_type, base_url, api_key_env_name,
        # None = 保持原有；[] = 清空；[...] = 整组替换
        provider.api_keys if api_keys is None else api_keys,
    )
    provider.name = name.strip()
    provider.provider_type = normalized_type
    provider.base_url = normalized_base
    provider.api_key_env_name = normalized_env_name
    provider.api_keys = normalized_keys
    # 系统标记 source 不能被用户编辑覆盖 —— 否则 ensure_default_model_management_state
    # 找不到原来的 bootstrap provider，会再 seed 一个出来。
    existing_extra = provider.extra_config or {}
    new_extra = dict(extra_config or {})
    if "source" in existing_extra and "source" not in new_extra:
        new_extra["source"] = existing_extra["source"]
    provider.extra_config = new_extra
    provider.status = status
    await db.commit()
    await db.refresh(provider)
    model_count = len(await _load_models(db, provider_id=provider_id))
    return serialize_provider(provider, model_count=model_count)


async def delete_model_provider(db: AsyncSession, provider_id: str) -> dict:
    provider = await db.get(ModelProvider, provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)

    models = await _load_models(db, provider_id=provider_id)
    model_ids = [str(model.id) for model in models]

    affected_slots: list[str] = []
    if model_ids:
        bindings = (
            await db.execute(
                select(ModelSlotBinding).where(ModelSlotBinding.model_id.in_(model_ids))
            )
        ).scalars().all()
        affected_slots = [b.slot_name for b in bindings]

        await db.execute(delete(ModelCapabilityProbe).where(ModelCapabilityProbe.model_id.in_(model_ids)))
        await db.execute(delete(ModelSlotBinding).where(ModelSlotBinding.model_id.in_(model_ids)))
        await db.execute(delete(ProviderModel).where(ProviderModel.id.in_(model_ids)))
    await db.delete(provider)
    await db.commit()
    return {"affected_slots": affected_slots}


async def list_provider_models(db: AsyncSession, *, provider_id: str | None = None) -> dict:
    await ensure_default_model_management_state(db)
    providers = await _load_providers(db)
    provider_by_id = {str(item.id): item for item in providers}
    models = await _load_models(db, provider_id=provider_id)
    probes = await _load_probes(db, model_ids=[str(item.id) for item in models])
    probes_by_model: dict[str, list[ModelCapabilityProbe]] = {}
    for probe in probes:
        probes_by_model.setdefault(str(probe.model_id), []).append(probe)

    bindings = await _load_bindings(db)
    binding_slots_by_model: dict[str, list[str]] = {}
    for binding in bindings:
        binding_slots_by_model.setdefault(str(binding.model_id), []).append(binding.slot_name)

    serialized_models = []
    for model in models:
        provider = provider_by_id.get(str(model.provider_id))
        if not provider:
            continue
        serialized_models.append(
            serialize_model(
                model,
                provider=provider,
                probes=probes_by_model.get(str(model.id), []),
                binding_slots=binding_slots_by_model.get(str(model.id), []),
            )
        )

    return {
        "models": serialized_models,
        "providers": [serialize_provider(provider, model_count=0) for provider in providers],
        "model_kinds": [TEXT_MODEL_KIND, IMAGE_MODEL_KIND],
        "capabilities": list(CAPABILITIES),
    }


async def create_provider_model(
    db: AsyncSession,
    *,
    provider_id: str,
    model_id: str,
    display_name: str,
    model_kind: str,
    is_enabled: bool = True,
    notes: str | None = None,
    input_price_cents_per_million_tokens: int | None = None,
    output_price_cents_per_million_tokens: int | None = None,
    image_price_cents_per_image: int | None = None,
    price_updated_at=None,
) -> dict:
    provider = await db.get(ModelProvider, provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)

    normalized_kind = _ensure_model_kind(model_kind)
    if not _provider_supports_model_kind(provider.provider_type, normalized_kind):
        raise ModelManagementError("当前 provider 类型不支持该模型类别")

    model = ProviderModel(
        provider_id=provider.id,
        model_id=model_id.strip(),
        display_name=display_name.strip() or model_id.strip(),
        model_kind=normalized_kind,
        is_enabled=is_enabled,
        notes=notes,
        input_price_cents_per_million_tokens=input_price_cents_per_million_tokens,
        output_price_cents_per_million_tokens=output_price_cents_per_million_tokens,
        image_price_cents_per_image=image_price_cents_per_image,
        price_updated_at=price_updated_at,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return serialize_model(model, provider=provider, probes=[], binding_slots=[])


async def update_provider_model(
    db: AsyncSession,
    model_id: str,
    *,
    display_name: str,
    model_kind: str,
    is_enabled: bool,
    notes: str | None = None,
    input_price_cents_per_million_tokens: int | None = None,
    output_price_cents_per_million_tokens: int | None = None,
    image_price_cents_per_image: int | None = None,
    price_updated_at=None,
) -> dict:
    model = await db.get(ProviderModel, model_id)
    if not model:
        raise ModelManagementError("模型不存在", status_code=404)
    provider = await db.get(ModelProvider, model.provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)

    normalized_kind = _ensure_model_kind(model_kind)
    if not _provider_supports_model_kind(provider.provider_type, normalized_kind):
        raise ModelManagementError("当前 provider 类型不支持该模型类别")

    model.display_name = display_name.strip() or model.model_id
    model.model_kind = normalized_kind
    model.is_enabled = is_enabled
    model.notes = notes
    model.input_price_cents_per_million_tokens = input_price_cents_per_million_tokens
    model.output_price_cents_per_million_tokens = output_price_cents_per_million_tokens
    model.image_price_cents_per_image = image_price_cents_per_image
    if price_updated_at is not None:
        model.price_updated_at = price_updated_at
    await db.commit()
    await db.refresh(model)
    probes = await _load_probes(db, model_ids=[str(model.id)])
    bindings = await _load_bindings(db)
    binding_slots = [binding.slot_name for binding in bindings if str(binding.model_id) == str(model.id)]
    return serialize_model(model, provider=provider, probes=probes, binding_slots=binding_slots)


async def delete_provider_model(db: AsyncSession, model_id: str) -> None:
    model = await db.get(ProviderModel, model_id)
    if not model:
        raise ModelManagementError("模型不存在", status_code=404)
    await db.execute(delete(ModelCapabilityProbe).where(ModelCapabilityProbe.model_id == model.id))
    await db.execute(delete(ModelSlotBinding).where(ModelSlotBinding.model_id == model.id))
    await db.delete(model)
    await db.commit()


def _split_keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


def _provider_api_keys_list(provider: ModelProvider) -> list[str]:
    """All usable API keys for a provider. Direct DB keys win; else env (comma-aware)."""
    direct = [k.strip() for k in (provider.api_keys or []) if isinstance(k, str) and k.strip()]
    if direct:
        return direct
    if provider.api_key_env_name:
        value = _configured_secret_value(provider.api_key_env_name)
        if value:
            return _split_keys(value)
    raise ModelManagementError(
        f"Provider「{provider.name}」未配置任何 API Key（直填或环境变量均为空）",
        status_code=400,
    )


def _affinity_from_context(explicit_affinity: str | None = None) -> str | None:
    if explicit_affinity:
        return explicit_affinity

    from llm.usage_context import current_usage_context

    ctx = current_usage_context()
    if ctx is None:
        return None
    return ctx.session_id or ctx.task_id


def _select_provider_key(provider: ModelProvider, *, key_affinity: str | None = None) -> tuple[str, str]:
    from llm.key_pool import select_key

    keys = _provider_api_keys_list(provider)
    return select_key(str(provider.id), keys, _affinity_from_context(key_affinity))


def _mask_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "…"
    return f"{k[:3]}…{k[-4:]}"


def _provider_key_previews(provider: ModelProvider) -> list[str]:
    try:
        keys = _provider_api_keys_list(provider)
    except ModelManagementError:
        return []
    return [_mask_key(k) for k in keys]


def _provider_api_key(provider: ModelProvider) -> str:
    """First usable key. Raises ModelManagementError when none configured."""
    return _provider_api_keys_list(provider)[0]


# The recipe to DISABLE a model's thinking phase is endpoint-specific and fails
# SILENTLY when wrong — a vendor ignores an unknown extra_body key and keeps
# thinking ON. That exact mismatch (DashScope's {"enable_thinking": false} left
# on the DeepSeek endpoint) caused a ~2x realtime TTFT regression. So for known
# vendor hosts we DERIVE the recipe authoritatively; an explicit per-provider
# extra_config["reasoning_off"] is only honored for unknown hosts. Matched by
# host (exact or subdomain). Note: provider_type alone is insufficient — DeepSeek
# direct, OpenCode (proxies DeepSeek) and DashScope are all "openai_compatible"
# yet need different recipes, so we key on host.
_REASONING_OFF_BY_HOST: tuple[tuple[str, dict], ...] = (
    ("dashscope.aliyuncs.com", {"enable_thinking": False}),
    ("api.deepseek.com", {"thinking": {"type": "disabled"}}),
    ("opencode.ai", {"thinking": {"type": "disabled"}}),
)


def _resolve_reasoning_off(provider: ModelProvider) -> dict | None:
    """extra_body that turns the thinking phase off for this provider's endpoint.

    Known vendor hosts are authoritative (can't be silently misconfigured by a
    stale recipe); unknown hosts fall back to the explicit per-provider override.
    """
    host = (urlparse(provider.base_url or "").hostname or "").lower()
    if host:
        for needle, recipe in _REASONING_OFF_BY_HOST:
            if host == needle or host.endswith("." + needle):
                return dict(recipe)
    return (provider.extra_config or {}).get("reasoning_off") or None


def _build_llm_provider(config: RuntimeModelConfig, *, key_affinity: str | None = None) -> LLMProvider:
    from llm.key_pool import KeySwitchingProvider

    provider = config.provider
    model = config.model
    keys = _provider_api_keys_list(provider)
    affinity = _affinity_from_context(key_affinity)
    base_url = provider.base_url or ""

    def build(api_key: str) -> LLMProvider:
        if provider.provider_type == "openai_compatible":
            reasoning_off = _resolve_reasoning_off(provider)
            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url,
                model=model.model_id,
                reasoning_off_extra_body=reasoning_off,
            )
        if provider.provider_type == "xai":
            return GrokProvider(api_key=api_key, base_url=base_url or settings.grok_base_url, model=model.model_id)
        if provider.provider_type == "gemini":
            return GeminiProvider(api_key=api_key, base_url=base_url or None, model=model.model_id)
        raise ModelManagementError("当前 provider 类型不支持文本能力")

    return KeySwitchingProvider(
        provider_id=str(provider.id),
        keys=keys,
        affinity=affinity,
        build=build,
        model=model.model_id,
    )


def _build_image_provider(config: RuntimeModelConfig, *, key_affinity: str | None = None) -> ImageGenerator:
    from llm.key_pool import KeyCooldownImageGenerator

    provider = config.provider
    model = config.model
    api_key, fp = _select_provider_key(provider, key_affinity=key_affinity)
    base_url = provider.base_url or ""

    inner: ImageGenerator
    if provider.provider_type == "openai_compatible":
        inner = OpenAICompatibleImageProvider(api_key=api_key, base_url=base_url, model=model.model_id)
    elif provider.provider_type == "xai":
        inner = GrokProvider(api_key=api_key, base_url=base_url or settings.grok_base_url, image_model=model.model_id)
    elif provider.provider_type == "gemini":
        inner = GeminiImageProvider(api_key=api_key, base_url=base_url or None, model=model.model_id)
    elif provider.provider_type == "seedream_image":
        inner = SeedreamImageProvider(api_key=api_key, base_url=base_url, model=model.model_id)
    else:
        raise ModelManagementError("当前 provider 类型不支持生图能力")
    return KeyCooldownImageGenerator(inner, provider_id=str(provider.id), fp=fp)


def _build_web_searcher(config: RuntimeModelConfig, *, key_affinity: str | None = None) -> WebSearcher | None:
    if config.provider.provider_type != "xai":
        return None
    api_key, _ = _select_provider_key(config.provider, key_affinity=key_affinity)
    return GrokProvider(
        api_key=api_key,
        base_url=config.provider.base_url or settings.grok_base_url,
        model=config.model.model_id,
    )


async def _collect_text(provider: LLMProvider, *, prompt: str, system: str = "你是一个测试助手。") -> str:
    parts: list[str] = []
    async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        system=system,
        max_tokens=256,
    ):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


async def _probe_chat_basic(provider: LLMProvider) -> tuple[str, str | None]:
    text = await _collect_text(provider, prompt="请只回复 ok")
    return ("passed", text[:200] or None) if text else ("failed", "模型没有返回文本")


async def _probe_streaming(provider: LLMProvider) -> tuple[str, str | None]:
    saw_delta = False
    parts: list[str] = []
    async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": "请用一句很短的话回应"}],
        tools=[],
        system="你是一个流式输出测试助手。",
        max_tokens=128,
    ):
        if event.get("type") == "text_delta":
            saw_delta = True
            parts.append(event.get("text", ""))
    return ("passed", "".join(parts)[:200] or None) if saw_delta else ("failed", "未收到流式文本分片")


async def _probe_tool_use(provider: LLMProvider) -> tuple[str, str | None]:
    tool = {
        "name": "probe_echo",
        "description": "回显测试文本",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    }
    tool_input = None
    async for event in provider.stream_with_tools(
        messages=[{"role": "user", "content": "请调用 probe_echo，并把 text 设置为 probe-ok"}],
        tools=[tool],
        system="你必须调用工具，不要输出纯文本。",
        max_tokens=256,
    ):
        if event.get("type") == "tool_use" and event.get("name") == "probe_echo":
            tool_input = event.get("input") or {}
    if tool_input and str(tool_input.get("text", "")).strip():
        return "passed", str(tool_input.get("text", ""))[:200]
    return "failed", "模型未触发工具调用"


async def _probe_json_output(provider: LLMProvider) -> tuple[str, str | None]:
    text = await _collect_text(
        provider,
        prompt='请只输出 JSON，不要 markdown：{"status":"ok"}',
        system="你是一个 JSON 输出测试助手。",
    )
    if text.startswith("{") and text.endswith("}"):
        return "passed", text[:200]
    return "failed", "模型未返回有效 JSON"


async def _probe_web_search(searcher: WebSearcher) -> tuple[str, str | None]:
    result = await searcher.web_search("today weather in Shanghai")
    if result.text.strip() or result.citations:
        return "passed", (result.text or "")[:200] or None
    return "failed", "模型未返回可用的联网搜索结果"


async def _probe_image_generation(generator: ImageGenerator) -> tuple[str, str | None]:
    result = await generator.generate_image("a simple black circle on white background", aspect_ratio="1:1")
    if result.has_url:
        return "passed", result.url[:200]
    if result.has_data:
        return "passed", f"inline:{len(result.base64_data)}"
    return "failed", "模型未返回图片结果"


async def _run_capability_probe(config: RuntimeModelConfig, capability: str) -> tuple[str, str | None]:
    if capability in {"chat_basic", "streaming", "tool_use", "json_output"}:
        provider = _build_llm_provider(config)
        if capability == "chat_basic":
            return await _probe_chat_basic(provider)
        if capability == "streaming":
            return await _probe_streaming(provider)
        if capability == "tool_use":
            return await _probe_tool_use(provider)
        return await _probe_json_output(provider)
    if capability == "web_search":
        searcher = _build_web_searcher(config)
        if not searcher:
            return "failed", "当前 provider 不支持联网搜索能力"
        return await _probe_web_search(searcher)
    if capability == "image_generation":
        generator = _build_image_provider(config)
        return await _probe_image_generation(generator)
    raise ModelManagementError("未知的探测能力")


async def _runtime_model_config(db: AsyncSession, model_id: str) -> RuntimeModelConfig:
    model = await db.get(ProviderModel, model_id)
    if not model:
        raise ModelManagementError("模型不存在", status_code=404)
    provider = await db.get(ModelProvider, model.provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)
    return RuntimeModelConfig(provider=provider, model=model)


async def probe_model_capabilities(
    db: AsyncSession,
    *,
    model_id: str,
    capabilities: list[str],
) -> dict:
    config = await _runtime_model_config(db, model_id)
    invalid = [capability for capability in capabilities if capability not in CAPABILITIES]
    if invalid:
        raise ModelManagementError("包含不支持的能力探测项")

    async def _run_single_probe(
        capability: str,
    ) -> tuple[str, str, str | None, str | None, int]:
        started = perf_counter()
        status = "failed"
        sample: str | None = None
        error_message: str | None = None
        try:
            status, sample = await _run_capability_probe(config, capability)
            if status != "passed":
                error_message = sample or "验证失败"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
        latency_ms = int((perf_counter() - started) * 1000)
        return capability, status, sample, error_message, latency_ms

    raw_results = await asyncio.gather(
        *[_run_single_probe(capability) for capability in capabilities]
    )

    results: dict[str, dict] = {}
    for capability, status, sample, error_message, latency_ms in raw_results:
        probe = ModelCapabilityProbe(
            model_id=config.model.id,
            capability=capability,
            status=status,
            latency_ms=latency_ms,
            error_message=error_message,
            response_sample=sample if status == "passed" else None,
            verified_at=utcnow(),
            expires_at=_probe_expiry_deadline(),
        )
        db.add(probe)
        results[capability] = _serialize_probe(probe) or {}
    await db.commit()
    return {"model_id": model_id, "probes": results}


async def _ensure_capabilities(
    db: AsyncSession,
    *,
    model: ProviderModel,
    provider: ModelProvider,
    capabilities: tuple[str, ...],
) -> tuple[bool, str | None, list[ModelCapabilityProbe]]:
    existing = await _load_probes(db, model_ids=[str(model.id)])
    latest = _latest_probe_map(existing)
    missing = [capability for capability in capabilities if not _probe_is_fresh(latest.get(capability))]
    if missing:
        await probe_model_capabilities(db, model_id=str(model.id), capabilities=missing)
        existing = await _load_probes(db, model_ids=[str(model.id)])
        latest = _latest_probe_map(existing)

    for capability in capabilities:
        probe = latest.get(capability)
        if not probe or probe.status != "passed":
            return False, probe.error_message if probe else f"{capability} 验证未通过", existing
    return True, None, existing


async def list_model_slots(db: AsyncSession) -> dict:
    await ensure_default_model_management_state(db)
    bindings = await _load_bindings(db)
    models = await _load_models(db)
    model_by_id = {str(model.id): model for model in models}
    provider_ids = list({str(model.provider_id) for model in models})
    providers = await _load_providers(db)
    provider_by_id = {str(provider.id): provider for provider in providers if str(provider.id) in provider_ids}

    serialized_slots = []
    binding_by_slot = {binding.slot_name: binding for binding in bindings}
    for slot in SLOT_DEFINITIONS:
        binding = binding_by_slot.get(slot["slot_name"])
        model = model_by_id.get(str(binding.model_id)) if binding else None
        provider = provider_by_id.get(str(model.provider_id)) if model else None
        serialized_slots.append(serialize_slot(slot, binding=binding, model=model, provider=provider))
    return {"slots": serialized_slots}


async def get_model_dashboard(db: AsyncSession) -> dict:
    await ensure_default_model_management_state(db)

    providers = await _load_providers(db)
    models = await _load_models(db)
    probes = await _load_probes(db, model_ids=[str(m.id) for m in models])
    bindings = await _load_bindings(db)

    provider_by_id = {str(p.id): p for p in providers}
    probes_by_model: dict[str, list[ModelCapabilityProbe]] = {}
    for probe in probes:
        probes_by_model.setdefault(str(probe.model_id), []).append(probe)

    binding_slots_by_model: dict[str, list[str]] = {}
    binding_by_slot: dict[str, ModelSlotBinding] = {}
    for binding in bindings:
        binding_slots_by_model.setdefault(str(binding.model_id), []).append(binding.slot_name)
        binding_by_slot[binding.slot_name] = binding

    model_counts: dict[str, int] = {}
    for model in models:
        model_counts[str(model.provider_id)] = model_counts.get(str(model.provider_id), 0) + 1

    serialized_providers = [
        serialize_provider(p, model_count=model_counts.get(str(p.id), 0))
        for p in providers
    ]

    serialized_models = []
    for model in models:
        provider = provider_by_id.get(str(model.provider_id))
        if not provider:
            continue
        serialized_models.append(
            serialize_model(
                model,
                provider=provider,
                probes=probes_by_model.get(str(model.id), []),
                binding_slots=binding_slots_by_model.get(str(model.id), []),
            )
        )

    model_by_id = {str(m.id): m for m in models}
    serialized_slots = []
    for slot in SLOT_DEFINITIONS:
        binding = binding_by_slot.get(slot["slot_name"])
        model = model_by_id.get(str(binding.model_id)) if binding else None
        provider = provider_by_id.get(str(model.provider_id)) if model else None
        serialized_slots.append(serialize_slot(slot, binding=binding, model=model, provider=provider))

    return {
        "providers": serialized_providers,
        "provider_types": list(PROVIDER_TYPES),
        "models": serialized_models,
        "model_kinds": [TEXT_MODEL_KIND, IMAGE_MODEL_KIND],
        "capabilities": list(CAPABILITIES),
        "slots": serialized_slots,
    }


async def bind_model_slot(
    db: AsyncSession,
    *,
    slot_name: str,
    model_id: str | None,
) -> dict:
    slot = _ensure_slot(slot_name)
    existing_binding = (
        await db.execute(select(ModelSlotBinding).where(ModelSlotBinding.slot_name == slot_name))
    ).scalar_one_or_none()

    if not model_id:
        if existing_binding:
            await db.delete(existing_binding)
            await db.commit()
        return (await list_model_slots(db))["slots"][list(SLOT_DEFINITION_BY_NAME).index(slot_name)]

    model = await db.get(ProviderModel, model_id)
    if not model:
        raise ModelManagementError("模型不存在", status_code=404)
    provider = await db.get(ModelProvider, model.provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)
    if not model.is_enabled:
        raise ModelManagementError("模型已禁用，不能绑定到槽位")
    if model.model_kind != slot["model_kind"]:
        raise ModelManagementError("该模型类别不能绑定到当前槽位")

    ok, error, _ = await _ensure_capabilities(
        db,
        model=model,
        provider=provider,
        capabilities=slot["required_capabilities"],
    )
    if not ok:
        raise ModelManagementError(error or "模型能力验证未通过")

    binding = existing_binding or ModelSlotBinding(slot_name=slot_name, model_id=model.id)
    binding.model_id = model.id
    binding.status = "active"
    binding.last_verified_at = utcnow()
    binding.last_verified_error = None
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return serialize_slot(slot, binding=binding, model=model, provider=provider)


async def _bound_runtime_config(db: AsyncSession, slot_name: str) -> RuntimeModelConfig | None:
    await ensure_default_model_management_state(db)
    binding = (
        await db.execute(select(ModelSlotBinding).where(ModelSlotBinding.slot_name == slot_name))
    ).scalar_one_or_none()
    if not binding:
        return None
    return await _runtime_model_config(db, str(binding.model_id))


def _legacy_text_router(slot_name: str) -> LLMRouter | None:
    if slot_name in DEFAULT_TEXT_SLOT_NAMES:
        model_name = settings.llm_compression_model if slot_name == "conversation_compression" else settings.llm_default_model
        provider = DeepSeekProvider(model=model_name)
        return LLMRouter(
            providers={"legacy": provider},
            fallback_chain=["legacy"],
            identity={"provider_name": "deepseek-legacy", "model_id": model_name},
            reasoning=_reasoning_for_slot(slot_name),
            timeout_seconds=GENERATION_FIRST_TOKEN_TIMEOUT_SECONDS if slot_name in GENERATION_TEXT_SLOT_NAMES else None,
        )
    if slot_name == "research_summary" and settings.grok_api_key:
        provider = GrokProvider(model=settings.grok_model)
        return LLMRouter(
            providers={"legacy": provider},
            fallback_chain=["legacy"],
            identity={"provider_name": "grok-legacy", "model_id": settings.grok_model},
        )
    if slot_name == "ip_recognition" and settings.grok_api_key:
        # 槽未绑定时的兜底：用 ip_recognition_model（grok-4.3-fast）建 grok provider，
        # 保留判断 + web_search 联网取证能力（与绑定态行为一致）。
        provider = GrokProvider(model=settings.ip_recognition_model)
        return LLMRouter(
            providers={"legacy": provider},
            fallback_chain=["legacy"],
            identity={"provider_name": "grok-legacy", "model_id": settings.ip_recognition_model},
        )
    return None


async def resolve_slot_router(
    db: AsyncSession,
    slot_name: str,
    *,
    key_affinity: str | None = None,
) -> LLMRouter | None:
    slot = _ensure_slot(slot_name)
    if slot["model_kind"] != TEXT_MODEL_KIND:
        raise ModelManagementError("当前槽位不是文本模型槽位")
    config = await _bound_runtime_config(db, slot_name)
    if not config:
        return _legacy_text_router(slot_name)
    provider = _build_llm_provider(config, key_affinity=key_affinity)
    return LLMRouter(
        providers={str(config.model.id): provider},
        fallback_chain=[str(config.model.id)],
        identity={
            "provider_name": config.provider.name,
            "model_id": config.model.model_id,
        },
        reasoning=_reasoning_for_slot(slot_name),
        timeout_seconds=GENERATION_FIRST_TOKEN_TIMEOUT_SECONDS if slot_name in GENERATION_TEXT_SLOT_NAMES else None,
    )


async def resolve_slot_provider(
    db: AsyncSession,
    slot_name: str,
    *,
    key_affinity: str | None = None,
) -> LLMProvider | None:
    config = await _bound_runtime_config(db, slot_name)
    if config:
        return _build_llm_provider(config, key_affinity=key_affinity)
    router = _legacy_text_router(slot_name)
    if not router:
        return None
    return next(iter(router.providers.values()))


async def resolve_slot_image_generator(
    db: AsyncSession,
    slot_name: str,
    *,
    key_affinity: str | None = None,
) -> ImageGenerator | None:
    slot = _ensure_slot(slot_name)
    if slot["model_kind"] != IMAGE_MODEL_KIND:
        raise ModelManagementError("当前槽位不是图片模型槽位")
    # Wrap the resolved generator in MeteredImageGenerator so every
    # successful generate_image call attributes one row to the ambient
    # UsageContext (cost = admin-configured image_price_cents_per_image).
    # Imported here to keep the model_management → services import graph
    # one-directional.
    from services.metered_image_generator import MeteredImageGenerator, MockImageGenerator

    if settings.mock_images:
        return MeteredImageGenerator(
            MockImageGenerator(),
            provider_name="mock",
            model_id="mock",
        )

    config = await _bound_runtime_config(db, slot_name)
    if config:
        return MeteredImageGenerator(
            _build_image_provider(config, key_affinity=key_affinity),
            provider_name=config.provider.name,
            model_id=config.model.model_id,
        )
    if settings.grok_api_key:
        return MeteredImageGenerator(
            GrokProvider(image_model=settings.grok_image_model),
            provider_name=None,
            model_id=settings.grok_image_model,
        )
    return None


async def resolve_research_web_searcher(
    db: AsyncSession,
    *,
    key_affinity: str | None = None,
) -> WebSearcher | None:
    config = await _bound_runtime_config(db, "research_summary")
    if config:
        return _build_web_searcher(config, key_affinity=key_affinity)
    if settings.grok_api_key:
        return GrokProvider(model=settings.grok_model)
    return None


async def healthcheck_model_provider(db: AsyncSession, provider_id: str) -> dict:
    await ensure_default_model_management_state(db)
    provider = await db.get(ModelProvider, provider_id)
    if not provider:
        raise ModelManagementError("Provider 不存在", status_code=404)

    models = [model for model in await _load_models(db, provider_id=provider_id) if model.is_enabled]

    try:
        _provider_api_key(provider)
    except ModelManagementError as exc:
        provider.status = "invalid"
        provider.last_healthcheck_error = exc.message
        provider.last_healthcheck_at = utcnow()
        await db.commit()
        await db.refresh(provider)
        model_count = len(await _load_models(db, provider_id=provider_id))
        return {
            "ok": False,
            "message": exc.message,
            "error": exc.message,
            "model_results": [],
            "provider": serialize_provider(provider, model_count=model_count),
        }

    model_results: list[dict] = []
    any_failed = False

    for model in models:
        capability = "chat_basic" if model.model_kind == TEXT_MODEL_KIND else "image_generation"
        try:
            result = await probe_model_capabilities(
                db, model_id=str(model.id), capabilities=[capability]
            )
            probe = result["probes"][capability]
            model_results.append({
                "model_id": str(model.id),
                "display_name": model.display_name,
                "capability": capability,
                "status": probe["status"],
                "error": probe.get("error_message"),
            })
            if probe["status"] != "passed":
                any_failed = True
        except Exception as exc:  # noqa: BLE001
            any_failed = True
            model_results.append({
                "model_id": str(model.id),
                "display_name": model.display_name,
                "capability": capability,
                "status": "failed",
                "error": str(exc),
            })

    if not models:
        message = "Provider 已连通，但尚未添加可验证的模型"
    elif any_failed:
        message = f"已验证 {len(models)} 个模型，部分失败"
    else:
        message = f"已验证 {len(models)} 个模型"

    error_message: str | None = None
    if any_failed:
        failed_names = [r["display_name"] for r in model_results if r["status"] != "passed"]
        error_message = f"失败模型: {', '.join(failed_names)}"

    provider.status = "active" if not any_failed else "invalid"
    provider.last_healthcheck_at = utcnow()
    provider.last_healthcheck_error = error_message
    await db.commit()
    await db.refresh(provider)
    model_count = len(await _load_models(db, provider_id=provider_id))
    return {
        "ok": not any_failed,
        "message": message,
        "error": error_message,
        "model_results": model_results,
        "provider": serialize_provider(provider, model_count=model_count),
    }
