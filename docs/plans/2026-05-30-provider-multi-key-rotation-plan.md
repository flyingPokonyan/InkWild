# Provider 多 Key 轮询池 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给每个 provider 配多个 API key，按会话粘连轮询分散负载、被限流的 key 自动冷却跳过，并把 key 存储从"读环境变量名"改为"可直接存 AK 进 DB（admin 管理、全程打码）"。

**Architecture:** 新增 `llm/key_pool.py`（指纹 + sticky 选择 + 冷却 + `KeyCooldownProvider` 薄 wrapper）。`services/model_management.py` 的 `_build_*` 改为解析 key 列表 → `select_key` 选一个 → 用 `KeyCooldownProvider` 包住底层 provider。`LLMRouter` 和三个 provider 类不动。affinity 复用现成的 `current_usage_context()`（`session_id or task_id`）。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, structlog；admin-frontend（Next.js + TanStack Query）。

**测试约定（遵循 CLAUDE.md「轻量测试」）：** 纯逻辑核心（key_pool、key 解析、masking、wrapper）写测试（test-first）；迁移 / 路由 / 前端 / 文档走「实现 + 验证」，不强行 failing-test-first。

**Git 说明：** 当前工作目录不是 git 仓库，**跳过所有 commit 步骤**，每个 Task 末尾以「验证」收尾。若后续 init 了 git，再按 Task 边界提交。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `backend/llm/key_pool.py`（新） | 指纹、`select_key`、`report_rate_limited`、cooldown/round-robin 状态、`KeyCooldownProvider` / `KeyCooldownImageGenerator` |
| `backend/tests/test_key_pool.py`（新） | key_pool 全部单测 |
| `backend/models/model_management.py`（改） | `ModelProvider` 加 `api_keys` 列、`api_key_env_name` 改 nullable |
| `backend/migrations/versions/<new>.py`（新） | 加列 + nullable 迁移 |
| `backend/config.py`（改） | `key_cooldown_seconds` 设置 |
| `backend/services/model_management.py`（改） | `_provider_api_keys_list`、affinity/选 key、`_build_*` 接 wrapper、`serialize_provider` masking、create/update 收 `api_keys`、校验放宽 |
| `backend/tests/test_model_management_api.py`（改） | 解析 + masking 测试 |
| `backend/api/admin_models.py`（改） | 请求模型加 `api_keys`、透传 |
| `admin-frontend/lib/types.ts`（改） | provider 类型加 `api_key_count` / `api_key_previews` |
| `admin-frontend/app/models/page.tsx`（改） | provider 表单多 key 输入 + 列表 masked 展示 |
| `docs/operations/deploy-and-config.md`（改） | 点明 `llm_global_concurrency` / `key_cooldown_seconds` / DB 直存 key |

---

## Task 1: key_pool 选择 + 冷却核心

**Files:**
- Create: `backend/llm/key_pool.py`
- Test: `backend/tests/test_key_pool.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_key_pool.py`:

```python
"""Unit tests for the per-provider API key pool."""
from __future__ import annotations

import llm.key_pool as kp


def setup_function() -> None:
    kp.reset_state()


def test_fingerprint_stable_and_short() -> None:
    fp = kp.fingerprint("sk-abc123")
    assert fp == kp.fingerprint("sk-abc123")
    assert len(fp) == 16
    assert fp != kp.fingerprint("sk-different")


def test_sticky_affinity_maps_same_session_to_same_key() -> None:
    keys = ["k1", "k2", "k3"]
    a = kp.select_key("prov", keys, affinity="session-A")
    b = kp.select_key("prov", keys, affinity="session-A")
    assert a == b
    assert a[0] in keys


def test_round_robin_when_no_affinity() -> None:
    keys = ["k1", "k2", "k3"]
    picks = [kp.select_key("prov", keys, affinity=None)[0] for _ in range(3)]
    assert set(picks) == set(keys)  # cycles through all three


def test_cooldown_key_is_skipped() -> None:
    keys = ["k1", "k2"]
    fp1 = kp.fingerprint("k1")
    kp.report_rate_limited("prov", fp1, cooldown_s=100.0, now=0.0)
    # affinity that would otherwise land on k1 must now avoid it
    for aff in ("a", "b", "c", "d"):
        key, _ = kp.select_key("prov", keys, affinity=aff, now=1.0)
        assert key == "k2"


def test_all_cooled_picks_soonest_to_recover() -> None:
    keys = ["k1", "k2"]
    kp.report_rate_limited("prov", kp.fingerprint("k1"), cooldown_s=10.0, now=0.0)
    kp.report_rate_limited("prov", kp.fingerprint("k2"), cooldown_s=100.0, now=0.0)
    key, _ = kp.select_key("prov", keys, affinity="x", now=1.0)
    assert key == "k1"  # k1 recovers at t=10, k2 at t=100


def test_cooldown_expires() -> None:
    keys = ["k1", "k2"]
    kp.report_rate_limited("prov", kp.fingerprint("k1"), cooldown_s=5.0, now=0.0)
    # after expiry k1 is available again
    available = {kp.select_key("prov", keys, affinity=a, now=10.0)[0] for a in "abcd"}
    assert "k1" in available
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_key_pool.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'llm.key_pool'`）

- [ ] **Step 3: 写实现**

Create `backend/llm/key_pool.py`:

```python
"""Per-provider API key pool: sticky selection + rate-limit cooldown.

Providers may carry multiple API keys to spread load across an upstream's
per-key concurrency / RPM limits. This module decides *which* key a given
provider build uses, and remembers which keys are currently rate-limited so
they can be skipped.

Selection is **sticky by affinity** (a game ``session_id`` or generation
``task_id``): the same session deterministically maps to the same key,
preserving the upstream prompt cache for that session, while different
sessions fan out across keys. With no affinity, a per-provider round-robin
counter is used instead.

State (round-robin counters + cooldown deadlines) is process-local. Under
multiple workers each process keeps its own view — a soft optimisation, not
a correctness guarantee. Cross-process coordination (Redis) is a future step.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import AsyncIterator

import structlog

from llm.base import ImageGenerator, ImageResult, LLMProvider

logger = structlog.get_logger()

# (provider_id, fingerprint) -> monotonic deadline after which the key is usable again.
_cooldowns: dict[tuple[str, str], float] = {}
# provider_id -> next round-robin index (used when no affinity is available).
_rr_counters: dict[str, int] = {}
_lock = threading.Lock()


def fingerprint(key: str) -> str:
    """Stable short id for a key. Cooldowns / logs reference this, never the raw key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _stable_hash(value: str) -> int:
    """PYTHONHASHSEED-independent hash (builtin ``hash()`` is salted per process)."""
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def _cooldown_seconds() -> float:
    from config import settings

    return float(getattr(settings, "key_cooldown_seconds", 45.0))


def select_key(
    provider_id: str,
    keys: list[str],
    affinity: str | None,
    *,
    now: float | None = None,
) -> tuple[str, str]:
    """Pick one key for this provider build. Returns ``(key, fingerprint)``.

    - Keys in cooldown are skipped.
    - If every key is cooling down, the one whose cooldown expires soonest is
      used anyway (never hard-fail just because all keys were recently limited).
    - Among available keys: sticky by ``affinity`` when set, else round-robin.
    """
    if not keys:
        raise ValueError("select_key requires at least one key")
    now = time.monotonic() if now is None else now

    fps = [(k, fingerprint(k)) for k in keys]
    with _lock:
        available = [
            (k, fp)
            for (k, fp) in fps
            if _cooldowns.get((provider_id, fp), 0.0) <= now
        ]
        if not available:
            return min(fps, key=lambda kf: _cooldowns.get((provider_id, kf[1]), 0.0))
        if affinity:
            return available[_stable_hash(affinity) % len(available)]
        n = _rr_counters.get(provider_id, 0)
        _rr_counters[provider_id] = n + 1
        return available[n % len(available)]


def report_rate_limited(
    provider_id: str,
    fp: str,
    *,
    cooldown_s: float | None = None,
    now: float | None = None,
) -> None:
    """Mark a key as rate-limited; it'll be skipped until the cooldown expires."""
    now = time.monotonic() if now is None else now
    cd = _cooldown_seconds() if cooldown_s is None else cooldown_s
    with _lock:
        _cooldowns[(provider_id, fp)] = now + cd
    logger.info("llm.key_cooldown", provider_id=provider_id, fp=fp, cooldown_s=cd)


def reset_state() -> None:
    """Test helper: clear all cooldowns + round-robin counters."""
    with _lock:
        _cooldowns.clear()
        _rr_counters.clear()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_key_pool.py -v`
Expected: PASS（6 个用例全过）

- [ ] **Step 5: 验证** `python -c "import llm.key_pool"` 无导入错误。

---

## Task 2: KeyCooldownProvider / KeyCooldownImageGenerator wrapper

**Files:**
- Modify: `backend/llm/key_pool.py`（追加）
- Test: `backend/tests/test_key_pool.py`（追加）

- [ ] **Step 1: 追加失败测试**

Append to `backend/tests/test_key_pool.py`:

```python
import pytest

from llm.key_pool import KeyCooldownProvider, _is_rate_limit


class _FakeRateLimit(Exception):
    """Stands in for openai.RateLimitError (matched by class name)."""


_FakeRateLimit.__name__ = "RateLimitError"


class _BoomProvider:
    model = "fake"

    def __init__(self, exc: Exception):
        self._exc = exc

    async def stream_with_tools(self, *a, **k):
        if False:
            yield {}
        raise self._exc

    async def stream_json(self, *a, **k):
        if False:
            yield {}
        raise self._exc


def test_is_rate_limit_by_class_name() -> None:
    assert _is_rate_limit(_FakeRateLimit("429"))


def test_is_rate_limit_by_status_code() -> None:
    exc = Exception("x")
    exc.status_code = 429
    assert _is_rate_limit(exc)
    exc2 = Exception("y")
    exc2.status_code = 500
    assert not _is_rate_limit(exc2)


async def test_wrapper_reports_cooldown_on_rate_limit_and_reraises() -> None:
    kp.reset_state()
    fp = kp.fingerprint("k1")
    wrapped = KeyCooldownProvider(_BoomProvider(_FakeRateLimit("429")), provider_id="p", fp=fp)
    with pytest.raises(Exception):
        async for _ in wrapped.stream_with_tools([], []):
            pass
    # k1 is now cooling -> a 2-key pool skips it
    key, _ = kp.select_key("p", ["k1", "k2"], affinity="any")
    assert key == "k2"


async def test_wrapper_does_not_cooldown_on_other_errors() -> None:
    kp.reset_state()
    fp = kp.fingerprint("k1")
    wrapped = KeyCooldownProvider(_BoomProvider(ValueError("nope")), provider_id="p", fp=fp)
    with pytest.raises(ValueError):
        async for _ in wrapped.stream_with_tools([], []):
            pass
    assert kp._cooldowns == {}  # no cooldown recorded
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_key_pool.py -v`
Expected: FAIL（`ImportError: cannot import name 'KeyCooldownProvider'`）

- [ ] **Step 3: 写实现**

Append to `backend/llm/key_pool.py`:

```python
def _is_rate_limit(exc: BaseException) -> bool:
    """Whether an exception is an upstream rate-limit (HTTP 429)."""
    if exc.__class__.__name__ == "RateLimitError":
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status == 429


class KeyCooldownProvider(LLMProvider):
    """Transparent passthrough that puts its key in cooldown on a 429.

    Re-raises every exception so ``LLMRouter``'s existing retry / fallback
    still runs. Exposes ``.model`` because the router reads it for identity
    stamping.
    """

    def __init__(self, inner: LLMProvider, *, provider_id: str, fp: str):
        self._inner = inner
        self._provider_id = provider_id
        self._fp = fp

    @property
    def model(self):  # noqa: ANN201 - mirrors inner provider's attribute
        return getattr(self._inner, "model", None)

    async def stream_with_tools(self, *args, **kwargs) -> AsyncIterator[dict]:
        try:
            async for ev in self._inner.stream_with_tools(*args, **kwargs):
                yield ev
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise

    async def stream_json(self, *args, **kwargs) -> AsyncIterator[dict]:
        try:
            async for ev in self._inner.stream_json(*args, **kwargs):
                yield ev
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise


class KeyCooldownImageGenerator(ImageGenerator):
    """Same cooldown-on-429 behaviour for the image generation path."""

    def __init__(self, inner: ImageGenerator, *, provider_id: str, fp: str):
        self._inner = inner
        self._provider_id = provider_id
        self._fp = fp

    @property
    def model(self):  # noqa: ANN201
        return getattr(self._inner, "model", None)

    async def generate_image(self, *args, **kwargs) -> ImageResult:
        try:
            return await self._inner.generate_image(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if _is_rate_limit(exc):
                report_rate_limited(self._provider_id, self._fp)
            raise
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_key_pool.py -v`
Expected: PASS（全部用例）

- [ ] **Step 5: 验证** `cd backend && python -c "from llm.key_pool import KeyCooldownProvider, KeyCooldownImageGenerator"` 无错误。

---

## Task 3: DB 模型 + 迁移

**Files:**
- Modify: `backend/models/model_management.py:19-22`
- Create: `backend/migrations/versions/<new>.py`

- [ ] **Step 1: 改模型**

In `backend/models/model_management.py`, 把 `ModelProvider` 的两行：

```python
    api_key_env_name: Mapped[str] = mapped_column(String(80))
```

改为（保留上下文 `base_url` 行不动，在其后）：

```python
    api_key_env_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 直填的原始 API key（明文，admin 管理）。非空时优先于 api_key_env_name。
    # 多个 key 用于分散单 key 并发上限，见 llm/key_pool.py。序列化时必须打码。
    api_keys: Mapped[list] = mapped_column(JSON, default=list)
```

（`JSON` 已在文件顶部导入，无需新增 import。）

- [ ] **Step 2: 生成迁移骨架**

Run: `cd backend && alembic revision -m "add provider api_keys and nullable env name"`
Expected: 在 `migrations/versions/` 生成一个新文件，`down_revision` 自动指向当前 head。

- [ ] **Step 3: 填迁移体**

在新生成文件里写 `upgrade` / `downgrade`（保留自动生成的 `revision` / `down_revision`）：

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "model_providers",
        sa.Column("api_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("model_providers", "api_keys", server_default=None)
    op.alter_column(
        "model_providers", "api_key_env_name",
        existing_type=sa.String(length=80), nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "model_providers", "api_key_env_name",
        existing_type=sa.String(length=80), nullable=False,
    )
    op.drop_column("model_providers", "api_keys")
```

- [ ] **Step 4: 应用并验证**

Run: `cd backend && alembic upgrade head`
Expected: 无报错。

Run: `cd backend && python -c "from sqlalchemy import inspect; from database import engine; import asyncio
async def main():
    async with engine.connect() as c:
        cols = await c.run_sync(lambda s: [col['name'] for col in inspect(s).get_columns('model_providers')])
        print(cols)
asyncio.run(main())"`
Expected: 输出含 `'api_keys'`。

> 若本地无 DB 连接，跳过 Step 4 的运行验证，改为人工核对迁移文件内容正确（在容器内 `docker compose ... alembic upgrade head`，见 memory「Docker dev 工作流」）。

---

## Task 4: config 设置

**Files:**
- Modify: `backend/config.py:126`

- [ ] **Step 1: 加设置**

In `backend/config.py`, 在 `llm_global_concurrency: int = 8` 这一行后新增：

```python
    # 单个 API key 被 429/限流命中后冷却多少秒再被轮询选中（见 llm/key_pool.py）。
    key_cooldown_seconds: float = 45.0
```

- [ ] **Step 2: 验证**

Run: `cd backend && python -c "from config import settings; print(settings.key_cooldown_seconds)"`
Expected: `45.0`

---

## Task 5: service — key 解析、选 key、masking、校验、create/update

**Files:**
- Modify: `backend/services/model_management.py`
- Test: `backend/tests/test_model_management_api.py`（追加纯函数测试）

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_model_management_api.py`（若文件顶部没有这些 import 就补上）:

```python
from types import SimpleNamespace

import services.model_management as mm


def _fake_provider(**kw):
    base = dict(id="p1", name="P", provider_type="openai_compatible",
               base_url="https://x/v1", api_key_env_name=None, api_keys=[],
               extra_config={}, status="active",
               last_healthcheck_at=None, last_healthcheck_error=None,
               created_at=None, updated_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_keys_list_prefers_direct() -> None:
    p = _fake_provider(api_keys=["sk-aaaa1111", "sk-bbbb2222"], api_key_env_name="DEEPSEEK_API_KEY")
    assert mm._provider_api_keys_list(p) == ["sk-aaaa1111", "sk-bbbb2222"]


def test_keys_list_env_comma_split(monkeypatch) -> None:
    monkeypatch.setattr(mm, "_configured_secret_value", lambda name: "k1, k2 ,k3")
    p = _fake_provider(api_keys=[], api_key_env_name="DEEPSEEK_API_KEY")
    assert mm._provider_api_keys_list(p) == ["k1", "k2", "k3"]


def test_keys_list_empty_raises() -> None:
    p = _fake_provider(api_keys=[], api_key_env_name=None)
    import pytest
    with pytest.raises(mm.ModelManagementError):
        mm._provider_api_keys_list(p)


def test_serialize_masks_keys() -> None:
    p = _fake_provider(api_keys=["sk-secret-abcd", "short"])
    out = mm.serialize_provider(p)
    assert out["api_key_count"] == 2
    assert out["api_key_previews"] == ["sk-…abcd", "…"]
    assert out["api_key_available"] is True
    # 原始 key 绝不出现在序列化结果任何字段里
    assert "sk-secret-abcd" not in repr(out)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_model_management_api.py -k "keys_list or masks" -v`
Expected: FAIL（`_provider_api_keys_list` 不存在 / 序列化无 `api_key_count`）

- [ ] **Step 3: 加 helper（key 解析 + 选 key + masking）**

In `backend/services/model_management.py`，在 `_provider_api_key`（约 862 行）**之前**新增：

```python
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


def _affinity_from_context() -> str | None:
    from llm.usage_context import current_usage_context

    ctx = current_usage_context()
    if ctx is None:
        return None
    return ctx.session_id or ctx.task_id


def _select_provider_key(provider: ModelProvider) -> tuple[str, str]:
    from llm.key_pool import select_key

    keys = _provider_api_keys_list(provider)
    return select_key(str(provider.id), keys, _affinity_from_context())


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
```

- [ ] **Step 4: 改 `_provider_api_key` 复用列表**

把现有 `_provider_api_key`（约 862-869 行）整段替换为：

```python
def _provider_api_key(provider: ModelProvider) -> str:
    """First usable key. Raises ModelManagementError when none configured."""
    return _provider_api_keys_list(provider)[0]
```

- [ ] **Step 5: 改 serialize_provider 打码**

把 `serialize_provider`（约 312-327 行）里这一行：

```python
        "api_key_available": bool(_configured_secret_value(provider.api_key_env_name)),
```

替换为：

```python
        "api_key_previews": (_previews := _provider_key_previews(provider)),
        "api_key_count": len(_previews),
        "api_key_available": bool(_previews),
```

（`api_key_env_name` 字段保留——那只是变量名，不是密钥。）

- [ ] **Step 6: 三个 `_build_*` 接 wrapper**

替换 `_build_llm_provider`（约 872-890）：

```python
def _build_llm_provider(config: RuntimeModelConfig) -> LLMProvider:
    from llm.key_pool import KeyCooldownProvider

    provider = config.provider
    model = config.model
    api_key, fp = _select_provider_key(provider)
    base_url = provider.base_url or ""

    inner: LLMProvider
    if provider.provider_type == "openai_compatible":
        reasoning_off = (provider.extra_config or {}).get("reasoning_off") or None
        inner = OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model=model.model_id,
            reasoning_off_extra_body=reasoning_off,
        )
    elif provider.provider_type == "xai":
        inner = GrokProvider(api_key=api_key, base_url=base_url or settings.grok_base_url, model=model.model_id)
    elif provider.provider_type == "gemini":
        inner = GeminiProvider(api_key=api_key, base_url=base_url or None, model=model.model_id)
    else:
        raise ModelManagementError("当前 provider 类型不支持文本能力")
    return KeyCooldownProvider(inner, provider_id=str(provider.id), fp=fp)
```

替换 `_build_image_provider`（约 893-907）：

```python
def _build_image_provider(config: RuntimeModelConfig) -> ImageGenerator:
    from llm.key_pool import KeyCooldownImageGenerator

    provider = config.provider
    model = config.model
    api_key, fp = _select_provider_key(provider)
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
```

`_build_web_searcher`（约 910-918）只换取 key 的那行（web_search 走 Grok 专用方法，不套 wrapper）：把
`api_key = _provider_api_key(config.provider)` 改为 `api_key, _ = _select_provider_key(config.provider)`。

- [ ] **Step 7: 放宽校验 + create/update 收 api_keys**

替换 `_validate_provider_input`（约 250-257）：

```python
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
```

替换 `create_model_provider`（约 651-672）签名 + 体：

```python
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
```

替换 `update_model_provider`（约 675-706）签名 + 相关赋值。在签名加 `api_keys: list[str] | None = None,`（放在 `api_key_env_name` 后）。把校验那行改为：

```python
    normalized_base, normalized_env_name, normalized_keys = _validate_provider_input(
        normalized_type, base_url, api_key_env_name,
        # None = 保持原有；[] = 清空；[...] = 整组替换
        provider.api_keys if api_keys is None else api_keys,
    )
```

并把 `provider.api_key_env_name = normalized_env_name` 之后补一行：

```python
    provider.api_keys = normalized_keys
```

> 注意：`update` 校验时若 `api_keys=None`（不改），用 `provider.api_keys` 兜底，保证「只改名字、不动 key」也能通过校验。

- [ ] **Step 8: 跑纯函数测试**

Run: `cd backend && python -m pytest tests/test_model_management_api.py -k "keys_list or masks" -v`
Expected: PASS

- [ ] **Step 9: 跑全量 model management + router 测试回归**

Run: `cd backend && python -m pytest tests/test_model_management_api.py tests/test_llm_router.py tests/test_llm_router_concurrency.py tests/test_router_current_model.py -v`
Expected: 全 PASS（注意 `serialize_provider` 字段变化是否影响既有断言；若有断言旧 `api_key_available` 形态，更新断言而非回退实现）。

---

## Task 6: admin 路由收 api_keys

**Files:**
- Modify: `backend/api/admin_models.py:33-42, 120-127, 153-162`

- [ ] **Step 1: 改请求模型**

替换 `CreateModelProviderRequest`（33-38）：

```python
class CreateModelProviderRequest(BaseModel):
    name: str
    provider_type: str
    base_url: str | None = None
    api_key_env_name: str | None = None
    # None=不变（编辑时）；[]=清空；[...]=整组替换。原始 key，响应永不回显。
    api_keys: list[str] | None = None
    extra_config: dict = Field(default_factory=dict)
```

（`UpdateModelProviderRequest(CreateModelProviderRequest)` 自动继承，无需改。）

- [ ] **Step 2: 透传 create**

在 `post_model_provider` 的 `create_model_provider(...)` 调用里（约 120-127），`api_key_env_name=req.api_key_env_name,` 之后加一行：

```python
            api_keys=req.api_keys,
```

- [ ] **Step 3: 透传 update**

在 `put_model_provider` 的 `update_model_provider(...)` 调用里（约 153-162），`api_key_env_name=req.api_key_env_name,` 之后加一行：

```python
            api_keys=req.api_keys,
```

- [ ] **Step 4: 验证 import / 启动**

Run: `cd backend && python -c "import api.admin_models"`
Expected: 无报错。

Run: `cd backend && python -m pytest tests/test_model_management_api.py -v`
Expected: 全 PASS（含路由级用例，如有）。

---

## Task 7: admin-frontend 多 key 输入 + masked 展示

**Files:**
- Modify: `admin-frontend/lib/types.ts:58-66`
- Modify: `admin-frontend/app/models/page.tsx:285-295, 816-943`

- [ ] **Step 1: 改类型**

In `admin-frontend/lib/types.ts`，`ModelProviderSummary` 里 `api_key_available: boolean;` 之后加两行：

```typescript
  api_key_count: number;
  api_key_previews: string[];
```

- [ ] **Step 2: 表单加多 key 输入**

In `admin-frontend/app/models/page.tsx` 的 `ProviderModal`，`form` 初始 state（约 816-822）加一个字段：

```typescript
    api_keys_text: (item?.api_key_previews || []).length
      ? "" // 编辑时不回填明文；留空=保持原有
      : "",
```

（即新增 `api_keys_text: "",`。）

在提交 `body`（约 829-836）里，`api_key_env_name: form.api_key_env_name,` 之后加：

```typescript
        // 一行/一个逗号一个 key；留空时编辑=不动(null)、新建=不发
        ...(() => {
          const parsed = form.api_keys_text
            .split(/[\n,]+/)
            .map((k) => k.trim())
            .filter(Boolean);
          if (parsed.length) return { api_keys: parsed };
          return isNew ? {} : { api_keys: null };
        })(),
```

在 env 名输入那个 `<div className="field">`（约 934-943）之后，新增一个多 key 文本域：

```tsx
      <div className="field">
        <label className="field-label">API Keys（直填，一行一个）</label>
        <textarea
          className="input mono"
          rows={3}
          value={form.api_keys_text}
          onChange={(e) => setForm({ ...form, api_keys_text: e.target.value })}
          placeholder={isNew ? "sk-xxx\nsk-yyy" : "留空 = 保持原有 key 不变"}
        />
        <div className="field-hint">
          {isNew
            ? "直填的 key 存数据库（优先于环境变量名）；多个 key 会按会话轮询分散并发"
            : `当前 ${item?.api_key_count ?? 0} 个 key：${(item?.api_key_previews || []).join("、") || "—"}。重填将整组替换。`}
        </div>
      </div>
```

并把上面 env 名输入的 label 由必填改为可选——把 `field-label field-label-req` 改成 `field-label`，hint 文案改为「可选：从环境变量读 key（可逗号分隔多个）」。

- [ ] **Step 3: 列表展示 masked**

In `page.tsx` provider 卡片里展示 env 名那段（约 288-294），把单显 `{p.api_key_env_name}` 改为同时显示 key 数 / 预览：

```tsx
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {p.api_key_count > 0
                    ? `${p.api_key_count} key：${p.api_key_previews.join("、")}`
                    : p.api_key_env_name || "—"}
                </span>
```

`{!p.api_key_available && (…)}` 的告警保留不动。

- [ ] **Step 4: 验证构建/类型**

Run: `cd admin-frontend && npx tsc --noEmit`
Expected: 无类型错误（若项目用别的检查命令，按 `admin-frontend` 既有脚本，如 `npm run build`）。

---

## Task 8: 文档 — 全局并发旋钮 + DB 直存 key

**Files:**
- Modify: `docs/operations/deploy-and-config.md`

- [ ] **Step 1: 补一节**

在 `docs/operations/deploy-and-config.md` 里 LLM / provider 配置相关章节，追加：

```markdown
### 多 Key 轮询与并发

- 每个 provider 可配多个 API key（admin「模型管理 → Provider 编辑 → API Keys」直填，或
  环境变量值逗号分隔）。运行时按**会话粘连**轮询：同一局恒定同 key（保 prompt 缓存），
  跨会话散开，被 429 限流的 key 自动冷却 `key_cooldown_seconds`（默认 45s）后再用。
- `llm_global_concurrency`（默认 8）封顶所有在途 LLM stream。**多 key 想真正提总并发，
  需相应调高它**，否则总并发被这道闸卡住、散到每个 key 都远低于其单 key 限额。
  经验值：`llm_global_concurrency ≈ key 数 × 单 key 可用并发预算`。
- 冷却状态是进程内存，多 worker 各自一份（软优化）。跨进程一致后续可接 Redis。
```

- [ ] **Step 2: 验证** 人工通读该节，确认与实现一致（设置名、默认值）。

---

## Self-Review（已核对）

- **Spec 覆盖：** 存储模型→T3/T5；masking→T5；select_key/sticky→T1；冷却+wrapper→T2；`_build_*` 接线→T5；config→T4；admin 路由→T6；admin UI→T7；全局闸提示→T8。✅ 全覆盖。
- **占位符：** 无 TBD/TODO（Redis 跨进程是显式「不在本期」，非占位）。✅
- **类型一致：** `select_key`→`(key, fp)`；`KeyCooldownProvider(inner, *, provider_id, fp)`；`_provider_api_keys_list`/`_select_provider_key`/`_provider_key_previews`；`_validate_provider_input` 返回三元组（调用方 create/update 已同步解三元组）。✅
- **风险点：** T5 Step 9 提示既有 `serialize_provider` 断言可能需同步更新；T3 Step 4 DB 验证在无本地 DB 时降级为容器内执行。
