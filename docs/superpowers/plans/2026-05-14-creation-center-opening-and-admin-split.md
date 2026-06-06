# 创作中心开放给用户 + 管理站拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把创作工坊从 admin-only 放开给所有登录用户使用（含 Beta 白名单 + 每日配额）、让 `provider_models` 单价驱动 token_usage 成本计算、formalize 草稿/发布状态机；同时保留 `/admin/*` 作为 admin 过渡入口（新管理员站独立子项目，由用户提供 HTML 后单独立 plan）。

**Architecture:** 单 backend、双前端路由（`/workshop/*` 用户、`/admin/*` admin 过渡）。改造分 3 个 phase：A 成本数据基建 → B 数据模型扩展 → C 路由开放。任务尽量按文件边界切，便于 subagent 并行。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / PostgreSQL / Next.js 16 / React 19 / TanStack Query / Tailwind v4。

**前置说明：**
- 本项目当前**无 git**，每个 task 完成后不 commit，而是用「Checkpoint」步骤确认 tests + manual sanity。
- 设计 spec：`docs/superpowers/specs/2026-05-14-creation-center-opening-and-admin-split-design.md`
- 不在本 plan 范围：新管理员站本体（Phase 9-11，等 HTML 设计）、积分系统、tier、审核 UI。

**并行机会（subagent 调度建议）：**

```
Wave 1（独立，可并发 4 个 subagent）：A1 / B1 / B2 / B3
Wave 2（依赖 Wave 1）：           A2（依赖 A1）/ B4（依赖 B1）
Wave 3：                         A3 / C1（依赖 B1-B4）
Wave 4：                         C2 / C3（依赖 C1）
Wave 5：                         D1 验证
```

---

## Phase A — 成本数据基建

### Task A1: 给 provider_models 加单价字段

**Files:**
- Modify: `backend/models/model_management.py`（line 31-46，ProviderModel class）
- Create: `backend/migrations/versions/<timestamp>_add_pricing_to_provider_models.py`
- Modify: `backend/api/admin_models.py`（add/edit provider_model 端点）
- Test: `backend/tests/test_provider_models_pricing.py`

- [ ] **Step 1: 写 ProviderModel pricing 字段 schema 测试（failing）**

Create `backend/tests/test_provider_models_pricing.py`:

```python
import pytest
from sqlalchemy import select
from models.model_management import ProviderModel, ModelProvider


@pytest.mark.asyncio
async def test_provider_model_accepts_pricing_fields(db_session):
    provider = ModelProvider(
        name="test-provider",
        provider_type="openai_compatible",
        api_key_env_name="TEST_KEY",
    )
    db_session.add(provider)
    await db_session.flush()

    model = ProviderModel(
        provider_id=provider.id,
        model_id="gpt-test",
        display_name="GPT Test",
        model_kind="text",
        input_price_cents_per_million_tokens=150,
        output_price_cents_per_million_tokens=600,
    )
    db_session.add(model)
    await db_session.commit()

    row = (await db_session.execute(select(ProviderModel).where(ProviderModel.model_id == "gpt-test"))).scalar_one()
    assert row.input_price_cents_per_million_tokens == 150
    assert row.output_price_cents_per_million_tokens == 600
    assert row.image_price_cents_per_image is None  # text model 不填
    assert row.price_updated_at is not None  # 写入时应该触发更新
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_provider_models_pricing.py -v
```

预期：`AttributeError: type object 'ProviderModel' has no attribute 'input_price_cents_per_million_tokens'`

- [ ] **Step 3: 修改 ProviderModel ORM 加字段**

Modify `backend/models/model_management.py` ProviderModel class（在 `notes` 之后、`created_at` 之前插入）：

```python
    input_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_price_cents_per_image: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

记得在文件顶部 import 已经包含 `Integer` 和 `datetime` —— 当前文件 import `String, Boolean, Text, JSON, Uuid` 等，需要补：

```python
from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, Uuid, UniqueConstraint
```

- [ ] **Step 4: 写 Alembic 迁移**

```bash
cd backend && alembic revision -m "add pricing to provider_models"
```

修改新生成的迁移文件：

```python
def upgrade():
    op.add_column('provider_models', sa.Column('input_price_cents_per_million_tokens', sa.Integer(), nullable=True))
    op.add_column('provider_models', sa.Column('output_price_cents_per_million_tokens', sa.Integer(), nullable=True))
    op.add_column('provider_models', sa.Column('image_price_cents_per_image', sa.Integer(), nullable=True))
    op.add_column('provider_models', sa.Column('price_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('provider_models', 'price_updated_at')
    op.drop_column('provider_models', 'image_price_cents_per_image')
    op.drop_column('provider_models', 'output_price_cents_per_million_tokens')
    op.drop_column('provider_models', 'input_price_cents_per_million_tokens')
```

跑迁移：

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 5: 扩展 admin_models 路由接受 pricing 字段**

打开 `backend/api/admin_models.py`，定位 ProviderModel 的 create / update 处理函数（找到 `POST /api/admin/models` / `PUT /api/admin/models/{id}` 或类似入口），在 request body schema（通常在 `backend/schemas/` 或文件内部 inline）里加：

```python
class ProviderModelCreateRequest(BaseModel):
    # ... 现有字段
    input_price_cents_per_million_tokens: int | None = None
    output_price_cents_per_million_tokens: int | None = None
    image_price_cents_per_image: int | None = None
```

在 service 创建/更新逻辑里，当 pricing 字段任一变化时同步写 `price_updated_at`：

```python
from utils import utcnow

def _apply_pricing_fields(model: ProviderModel, payload) -> None:
    changed = False
    for fname in ("input_price_cents_per_million_tokens", "output_price_cents_per_million_tokens", "image_price_cents_per_image"):
        new_val = getattr(payload, fname, None)
        if new_val != getattr(model, fname):
            setattr(model, fname, new_val)
            changed = True
    if changed:
        model.price_updated_at = utcnow()
```

在 create 和 update 路径都调用 `_apply_pricing_fields(model, payload)`。

- [ ] **Step 6: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_provider_models_pricing.py -v
```

预期：PASS。

- [ ] **Step 7: Checkpoint**

跑全套 backend 测试，确认没破坏：

```bash
cd backend && python -m pytest tests/ -x -q
```

预期：全 pass（除了已知失败 case，跟此次改动无关）。

---

### Task A2: token_usage 写入读 provider_model 单价

**Files:**
- Modify: `backend/engine/cost_guardrail.py`（`estimate_usage_cost_cents` 函数）
- Modify: `backend/services/game_service.py:573` 附近（`TokenUsage(...)` 写入处）
- Test: `backend/tests/test_cost_guardrail_pricing.py`

- [ ] **Step 1: 写 cost_guardrail 读 provider_model 的测试（failing）**

Create `backend/tests/test_cost_guardrail_pricing.py`:

```python
from engine.cost_guardrail import estimate_usage_cost_cents


def test_estimate_uses_provider_model_pricing_when_present():
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    pricing = {
        "input_price_cents_per_million_tokens": 200,
        "output_price_cents_per_million_tokens": 800,
    }
    cost = estimate_usage_cost_cents(usage, pricing=pricing)
    # 1M input * 200 + 0.5M output * 800 = 200 + 400 = 600 cents
    assert cost == 600


def test_estimate_falls_back_to_env_when_pricing_null():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    pricing = {"input_price_cents_per_million_tokens": None, "output_price_cents_per_million_tokens": None}
    cost = estimate_usage_cost_cents(usage, pricing=pricing, env_input_cents=300, env_output_cents=900)
    assert cost == 300


def test_estimate_zero_when_no_pricing_and_no_env():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    cost = estimate_usage_cost_cents(usage, pricing=None, env_input_cents=0, env_output_cents=0)
    assert cost == 0


def test_usage_cost_cents_field_overrides_estimate():
    usage = {"input_tokens": 1_000_000, "cost_cents": 999}
    pricing = {"input_price_cents_per_million_tokens": 200}
    # provider 自己给了 cost_cents，优先用它
    cost = estimate_usage_cost_cents(usage, pricing=pricing)
    assert cost == 999
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_cost_guardrail_pricing.py -v
```

预期：fail（函数签名不接受 `pricing`/`env_input_cents`/`env_output_cents`）。

- [ ] **Step 3: 修改 `estimate_usage_cost_cents` 签名**

打开 `backend/engine/cost_guardrail.py`。现有函数依赖 `settings.game_input_cost_cents_per_million_tokens`。重构为接受显式 pricing dict：

```python
def estimate_usage_cost_cents(
    usage: dict,
    *,
    pricing: dict | None = None,
    env_input_cents: int = 0,
    env_output_cents: int = 0,
    env_image_cents: int = 0,
) -> int:
    """Estimate cost in cents from usage dict.

    Priority:
      1. usage["cost_cents"] (provider 自己结算)
      2. pricing dict 中对应字段
      3. env fallback
    Returns 0 if nothing applicable.
    """
    if usage.get("cost_cents") is not None:
        return int(usage["cost_cents"])

    pricing = pricing or {}
    input_price = pricing.get("input_price_cents_per_million_tokens") or env_input_cents
    output_price = pricing.get("output_price_cents_per_million_tokens") or env_output_cents
    image_price = pricing.get("image_price_cents_per_image") or env_image_cents

    cents = 0
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    image_count = usage.get("image_count", 0) or 0

    cents += (input_tokens * input_price + 999_999) // 1_000_000 if input_price else 0
    cents += (output_tokens * output_price + 999_999) // 1_000_000 if output_price else 0
    cents += image_count * image_price if image_price else 0

    return cents
```

注意保留现有 `classify_session_cost` 等其他函数不变。

- [ ] **Step 4: 跑新测试确认 pass**

```bash
cd backend && python -m pytest tests/test_cost_guardrail_pricing.py -v
```

- [ ] **Step 5: 修改 game_service 的 TokenUsage 写入**

打开 `backend/services/game_service.py:573` 附近，定位 `TokenUsage(...)` 实例化代码。当前可能是：

```python
TokenUsage(
    session_id=session.id,
    provider="...",
    model="...",
    input_tokens=...,
    output_tokens=...,
    cost_cents=estimate_usage_cost_cents(usage),  # 旧
    ...
)
```

改为先 join `provider_models` 拿单价，然后传给 `estimate_usage_cost_cents`：

```python
from sqlalchemy import select
from models.model_management import ProviderModel, ModelProvider

async def _get_pricing_for(db, provider_name: str, model_id: str) -> dict | None:
    stmt = (
        select(
            ProviderModel.input_price_cents_per_million_tokens,
            ProviderModel.output_price_cents_per_million_tokens,
            ProviderModel.image_price_cents_per_image,
        )
        .join(ModelProvider, ModelProvider.id == ProviderModel.provider_id)
        .where(ModelProvider.name == provider_name, ProviderModel.model_id == model_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    return {
        "input_price_cents_per_million_tokens": row[0],
        "output_price_cents_per_million_tokens": row[1],
        "image_price_cents_per_image": row[2],
    }
```

在 TokenUsage 写入前先拿 pricing：

```python
pricing = await _get_pricing_for(db, provider_name, model_id)
cost = estimate_usage_cost_cents(
    usage,
    pricing=pricing,
    env_input_cents=settings.game_input_cost_cents_per_million_tokens,
    env_output_cents=settings.game_output_cost_cents_per_million_tokens,
)
db.add(TokenUsage(..., cost_cents=cost))
```

如果 game_service 当前没有获取 `provider_name` / `model_id`，需要从调用 LLM 的上下文传下来。检查 `_consume_turn` 函数签名，必要时把 LLM router 返回的 metadata 一起带回（slot 解析时已经知道实际用的 provider+model）。

- [ ] **Step 6: 同样改造创作工坊的 token usage 写入**

`grep -rn "TokenUsage(" backend/services/` 找其他写入点（创作工坊、moderation 等都可能写）。每处都改成走 `estimate_usage_cost_cents(..., pricing=await _get_pricing_for(...))`。

如果有多处复制，把 helper 提到 `backend/engine/cost_guardrail.py` 或 `backend/services/pricing_lookup.py` 复用。

- [ ] **Step 7: 跑回归测试**

```bash
cd backend && python -m pytest tests/test_cost_guardrail.py tests/test_cost_guardrail_pricing.py tests/test_game_action.py -v
```

预期：全 pass。`test_cost_guardrail.py` 现有的测试不应被破坏（pricing 参数都有 default value）。

- [ ] **Step 8: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

---

### Task A3: Cost Analytics 临时页（挂在 `/admin`）

**Files:**
- Create: `backend/api/admin_analytics.py`
- Modify: `backend/main.py`（注册新 router）
- Modify: `frontend/components/admin/workshop/WorkshopHeader.tsx`（加 "Analytics" tab）
- Create: `frontend/app/admin/analytics/page.tsx`（如果走子路径）或 `frontend/components/admin/AnalyticsPanel.tsx`（如果加 tab）
- Test: `backend/tests/test_admin_analytics.py`

> **决策**：先用子路径 `/admin/analytics` 实现，避免动 WorkshopHeader 的 tab 模型。后续迁到管理员站时一并搬。

- [ ] **Step 1: 写后端 analytics 聚合测试（failing）**

Create `backend/tests/test_admin_analytics.py`:

```python
import pytest
from datetime import datetime, timedelta

from models.game import TokenUsage, GameSession


@pytest.mark.asyncio
async def test_session_cost_summary(db_session, admin_user, sample_world):
    # 准备 3 局 session，cost 分别 100/300/500 cents
    sessions = [
        GameSession(user_id=admin_user.id, world_id=sample_world.id, mode="script", game_state={}),
        GameSession(user_id=admin_user.id, world_id=sample_world.id, mode="script", game_state={}),
        GameSession(user_id=admin_user.id, world_id=sample_world.id, mode="free",   game_state={}),
    ]
    db_session.add_all(sessions)
    await db_session.flush()

    for s, c in zip(sessions, [100, 300, 500]):
        db_session.add(TokenUsage(session_id=s.id, provider="x", model="y", input_tokens=0, output_tokens=0, cost_cents=c))
    await db_session.commit()

    from services.analytics_service import session_cost_summary
    summary = await session_cost_summary(db_session, days=7)
    assert summary["total_sessions"] == 3
    assert summary["total_cost_cents"] == 900
    assert summary["avg_cost_cents"] == 300
```

- [ ] **Step 2: 实现 analytics_service**

Create `backend/services/analytics_service.py`:

```python
from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.game import TokenUsage, GameSession
from models.generation_task import GenerationTask


async def session_cost_summary(db: AsyncSession, days: int = 7) -> dict:
    """单局游戏成本汇总，过去 N 天内的所有 session。"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    per_session_q = (
        select(GameSession.id, func.coalesce(func.sum(TokenUsage.cost_cents), 0).label("cost"))
        .join(TokenUsage, TokenUsage.session_id == GameSession.id, isouter=True)
        .where(GameSession.created_at >= cutoff)
        .group_by(GameSession.id)
    )
    rows = (await db.execute(per_session_q)).all()
    costs = [r.cost for r in rows]
    total = sum(costs)
    n = len(costs)
    return {
        "window_days": days,
        "total_sessions": n,
        "total_cost_cents": total,
        "avg_cost_cents": total // n if n else 0,
        "p50_cost_cents": sorted(costs)[n // 2] if n else 0,
        "p90_cost_cents": sorted(costs)[int(n * 0.9)] if n else 0,
    }


async def generation_cost_summary(db: AsyncSession, days: int = 7, kind: str | None = None) -> dict:
    """单次创世任务成本汇总。"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    # generation_tasks 没有直接的 cost 字段；按 token_usage（如果有 task_id 字段则 join）
    # 当前 token_usage 是 session-scoped，generation 走 LLM 调用时是否记账要确认。
    # 临时方案：返回任务计数 + 状态分布，cost 字段为 0（todo: 等创作工坊也写 token_usage）
    stmt = select(GenerationTask).where(GenerationTask.created_at >= cutoff)
    if kind:
        stmt = stmt.where(GenerationTask.kind == kind)
    tasks = (await db.execute(stmt)).scalars().all()
    return {
        "window_days": days,
        "kind": kind,
        "total_tasks": len(tasks),
        "by_status": {st: sum(1 for t in tasks if t.status == st) for st in {"pending", "running", "succeeded", "failed", "cancelled"}},
    }
```

- [ ] **Step 3: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_admin_analytics.py -v
```

- [ ] **Step 4: 建 analytics API endpoint**

Create `backend/api/admin_analytics.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_admin_user
from services import analytics_service

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])


@router.get("/sessions")
async def get_session_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    summary = await analytics_service.session_cost_summary(db, days=days)
    return {"code": 0, "data": summary, "message": "ok"}


@router.get("/generations")
async def get_generation_summary(
    days: int = Query(7, ge=1, le=90),
    kind: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    summary = await analytics_service.generation_cost_summary(db, days=days, kind=kind)
    return {"code": 0, "data": summary, "message": "ok"}
```

- [ ] **Step 5: 注册 router**

打开 `backend/main.py`，在其他 admin router 注册旁边加：

```python
from api import admin_analytics
app.include_router(admin_analytics.router)
```

- [ ] **Step 6: 起 backend，curl 验证**

```bash
cd backend && uvicorn main:app --reload --port 8000 &
# 登录拿 cookie 后:
curl http://localhost:8000/api/admin/analytics/sessions?days=7 -b cookies.txt
```

预期返回 `{"code":0,"data":{"window_days":7,...},"message":"ok"}`。

- [ ] **Step 7: 加前端 admin/analytics 页面**

Create `frontend/app/admin/analytics/page.tsx`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { adminFetch } from "@/lib/admin-api";

type SessionSummary = {
  window_days: number;
  total_sessions: number;
  total_cost_cents: number;
  avg_cost_cents: number;
  p50_cost_cents: number;
  p90_cost_cents: number;
};

type GenerationSummary = {
  window_days: number;
  kind: string | null;
  total_tasks: number;
  by_status: Record<string, number>;
};

export default function AnalyticsPage() {
  const sessions = useQuery({
    queryKey: ["admin", "analytics", "sessions", 7],
    queryFn: () =>
      adminFetch<{ code: number; data: SessionSummary }>(
        "/api/admin/analytics/sessions?days=7",
      ).then((r) => r.data),
  });

  const gens = useQuery({
    queryKey: ["admin", "analytics", "generations", 7],
    queryFn: () =>
      adminFetch<{ code: number; data: GenerationSummary }>(
        "/api/admin/analytics/generations?days=7",
      ).then((r) => r.data),
  });

  return (
    <div className="workshop-page">
      <main className="workshop-main">
        <div className="workshop-shell">
          <h1 className="lv-t-h1" style={{ marginBottom: "var(--lv-s-8)" }}>
            Cost Analytics (近 7 天)
          </h1>

          <section style={{ marginBottom: "var(--lv-s-10)" }}>
            <h2 className="lv-t-h2">游戏 session</h2>
            {sessions.isPending ? (
              <p className="lv-t-meta">loading…</p>
            ) : sessions.data ? (
              <ul className="lv-t-body" style={{ listStyle: "none", padding: 0 }}>
                <li>总 session 数: {sessions.data.total_sessions}</li>
                <li>累计成本: ¥{(sessions.data.total_cost_cents / 100).toFixed(2)}</li>
                <li>平均/局: ¥{(sessions.data.avg_cost_cents / 100).toFixed(2)}</li>
                <li>p50: ¥{(sessions.data.p50_cost_cents / 100).toFixed(2)}</li>
                <li>p90: ¥{(sessions.data.p90_cost_cents / 100).toFixed(2)}</li>
              </ul>
            ) : null}
          </section>

          <section>
            <h2 className="lv-t-h2">创世任务</h2>
            {gens.isPending ? (
              <p className="lv-t-meta">loading…</p>
            ) : gens.data ? (
              <ul className="lv-t-body" style={{ listStyle: "none", padding: 0 }}>
                <li>总任务数: {gens.data.total_tasks}</li>
                <li>状态分布:</li>
                {Object.entries(gens.data.by_status).map(([k, v]) => (
                  <li key={k} style={{ marginLeft: "var(--lv-s-4)" }}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 8: 浏览器验证**

启动前后端，访问 `http://localhost:3000/admin/analytics`（需 admin 登录态），确认数据显示。

- [ ] **Step 9: Checkpoint**

```bash
cd backend && python -m pytest tests/test_admin_analytics.py -v
cd frontend && npm run lint
```

预期：测试 pass，lint 不报错。

---

## Phase B — 数据模型扩展

### Task B1: 状态机 enum 正式化 + scripts.is_published 迁移

**Files:**
- Create: `backend/engine/content_status.py`（status 常量 + 转换函数）
- Modify: `backend/models/world.py`（status 字段加注释）
- Modify: `backend/models/script.py`（加 status 字段，废弃 is_published 但保留兼容）
- Create: `backend/migrations/versions/<timestamp>_add_status_to_scripts.py`
- Test: `backend/tests/test_content_status.py`

- [ ] **Step 1: 写状态机测试（failing）**

Create `backend/tests/test_content_status.py`:

```python
import pytest
from engine.content_status import (
    ContentStatus,
    can_transition,
    next_status_on_publish,
    next_status_on_withdraw,
)


def test_valid_transitions():
    assert can_transition(ContentStatus.DRAFT, ContentStatus.PUBLISHED)
    assert can_transition(ContentStatus.PUBLISHED, ContentStatus.DRAFT)  # 用户自己下架
    assert can_transition(ContentStatus.PUBLISHED, ContentStatus.WITHDRAWN)  # admin 下架


def test_invalid_transitions():
    assert not can_transition(ContentStatus.WITHDRAWN, ContentStatus.DRAFT)
    assert not can_transition(ContentStatus.DRAFT, ContentStatus.WITHDRAWN)


def test_publish_path_audit_off():
    # 全局审核关闭：直接 published
    assert next_status_on_publish(audit_enabled=False) == ContentStatus.PUBLISHED


def test_publish_path_audit_on():
    # 审核开启：进 submitted（未来用）
    assert next_status_on_publish(audit_enabled=True) == ContentStatus.SUBMITTED


def test_withdraw_actor():
    assert next_status_on_withdraw(by_admin=False) == ContentStatus.DRAFT
    assert next_status_on_withdraw(by_admin=True) == ContentStatus.WITHDRAWN
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_content_status.py -v
```

- [ ] **Step 3: 实现 content_status 模块**

Create `backend/engine/content_status.py`:

```python
"""Content publish/withdraw state machine for worlds and scripts.

States:
  draft       — only creator visible, editable
  submitted   — under audit (reserved; not used Phase 1)
  published   — visible to all users, immutable until withdrawn
  withdrawn   — admin force-removed; cannot self-recover
"""
from enum import StrEnum


class ContentStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


_VALID_TRANSITIONS = {
    (ContentStatus.DRAFT, ContentStatus.SUBMITTED),
    (ContentStatus.DRAFT, ContentStatus.PUBLISHED),
    (ContentStatus.SUBMITTED, ContentStatus.PUBLISHED),
    (ContentStatus.SUBMITTED, ContentStatus.DRAFT),
    (ContentStatus.PUBLISHED, ContentStatus.DRAFT),
    (ContentStatus.PUBLISHED, ContentStatus.WITHDRAWN),
    (ContentStatus.WITHDRAWN, ContentStatus.PUBLISHED),
}


def can_transition(src: ContentStatus, dst: ContentStatus) -> bool:
    return (src, dst) in _VALID_TRANSITIONS


def next_status_on_publish(*, audit_enabled: bool) -> ContentStatus:
    return ContentStatus.SUBMITTED if audit_enabled else ContentStatus.PUBLISHED


def next_status_on_withdraw(*, by_admin: bool) -> ContentStatus:
    return ContentStatus.WITHDRAWN if by_admin else ContentStatus.DRAFT
```

- [ ] **Step 4: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_content_status.py -v
```

- [ ] **Step 5: 给 Script 加 status 字段（保留 is_published）**

Modify `backend/models/script.py` Script class，在 `is_published` 后增加：

```python
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
```

- [ ] **Step 6: 写 Alembic 迁移：加 scripts.status 并从 is_published backfill**

```bash
cd backend && alembic revision -m "add status to scripts backfilled from is_published"
```

修改新迁移：

```python
def upgrade():
    op.add_column('scripts', sa.Column('status', sa.String(20), nullable=False, server_default='draft'))
    op.execute("UPDATE scripts SET status = 'published' WHERE is_published = TRUE")
    op.execute("UPDATE scripts SET status = 'draft' WHERE is_published = FALSE")
    op.create_index('idx_scripts_status', 'scripts', ['status'])
    # is_published 保留作为兼容字段，本期不删，后续 spec 单独清理


def downgrade():
    op.drop_index('idx_scripts_status', table_name='scripts')
    op.drop_column('scripts', 'status')
```

跑迁移：

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 7: 同样把 worlds.status default 改为 'draft'，并加 index（如尚未有）**

打开 `backend/models/world.py` line 31：

```python
    status: Mapped[str] = mapped_column(String(20), default="published")
```

现状 default 是 'published'（适合 seed 数据全部公开）。新建数据从 workshop 走时应该 default 'draft'。但这是写入逻辑问题，不动 default（避免破坏现有 seed 流程）。在 service 层创建 world 时显式传 `status=ContentStatus.DRAFT`。

检查是否有 index：grep 当前 schema：

```bash
grep -n "Index.*status\|status.*Index" backend/models/world.py
```

如无 index 且查询频繁需要，加迁移：

```bash
cd backend && alembic revision -m "index worlds.status"
```

```python
def upgrade():
    op.create_index('idx_worlds_status', 'worlds', ['status'])

def downgrade():
    op.drop_index('idx_worlds_status', table_name='worlds')
```

- [ ] **Step 8: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_content_status.py -v
cd backend && python -m pytest tests/ -x -q
```

预期：所有现有测试不被破坏。

---

### Task B2: created_by_user_id 字段全量加

**Files:**
- Modify: `backend/models/draft.py`
- Modify: `backend/models/generation_task.py`
- Modify: `backend/models/world.py`
- Modify: `backend/models/script.py`
- Create: `backend/migrations/versions/<timestamp>_add_created_by_user_id.py`
- Test: `backend/tests/test_ownership_fields.py`

- [ ] **Step 1: 写 ownership 测试（failing）**

Create `backend/tests/test_ownership_fields.py`:

```python
import pytest
from sqlalchemy import select
from models.draft import WorldDraft, ScriptDraft
from models.generation_task import GenerationTask
from models.world import World
from models.script import Script


@pytest.mark.asyncio
async def test_world_draft_requires_creator(db_session, sample_user):
    draft = WorldDraft(payload={}, created_by_user_id=sample_user.id)
    db_session.add(draft)
    await db_session.commit()

    row = (await db_session.execute(select(WorldDraft).where(WorldDraft.id == draft.id))).scalar_one()
    assert row.created_by_user_id == sample_user.id


@pytest.mark.asyncio
async def test_generation_task_has_creator_field(db_session, sample_user):
    task = GenerationTask(
        kind="world",
        draft_type="world",
        draft_id="00000000-0000-0000-0000-000000000000",
        request_payload={},
        created_by_user_id=sample_user.id,
    )
    db_session.add(task)
    await db_session.commit()

    row = (await db_session.execute(select(GenerationTask).where(GenerationTask.id == task.id))).scalar_one()
    assert row.created_by_user_id == sample_user.id


@pytest.mark.asyncio
async def test_world_creator_nullable(db_session):
    # 官方/seed 内容允许 null
    world = World(
        name="Official",
        description="seed",
        genre="mystery",
        era="modern",
        difficulty=3,
        estimated_time="30",
        base_setting="seed",
        # 没传 created_by_user_id
    )
    db_session.add(world)
    await db_session.commit()
    assert world.created_by_user_id is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_ownership_fields.py -v
```

- [ ] **Step 3: 修改 draft.py 加 created_by_user_id（NOT NULL）**

Modify `backend/models/draft.py`：

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class WorldDraft(Base):
    __tablename__ = "world_drafts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"), nullable=True, unique=True)
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ScriptDraft(Base):
    __tablename__ = "script_drafts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    script_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("scripts.id"), nullable=True, unique=True)
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
```

- [ ] **Step 4: generation_task.py 加 created_by_user_id**

Modify `backend/models/generation_task.py` GenerationTask class，加：

```python
    created_by_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
```

- [ ] **Step 5: worlds / scripts 加 created_by_user_id（nullable）**

Modify `backend/models/world.py` World class（在 `status` 后插入）：

```python
    created_by_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
```

Modify `backend/models/script.py` Script class，类似插入：

```python
    created_by_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
```

- [ ] **Step 6: 写迁移：加字段 + backfill**

```bash
cd backend && alembic revision -m "add created_by_user_id to drafts tasks worlds scripts"
```

```python
def upgrade():
    # 先验证存在至少 1 个 admin user，否则迁移失败
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM users WHERE is_admin = TRUE LIMIT 1"))
    admin_row = result.first()
    if not admin_row:
        raise Exception("Migration requires at least 1 admin user. Create one first.")
    admin_id = admin_row[0]

    # drafts / tasks: NOT NULL，backfill 用首个 admin
    op.add_column('world_drafts', sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
    op.add_column('script_drafts', sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
    op.add_column('generation_tasks', sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))

    conn.execute(sa.text(f"UPDATE world_drafts SET created_by_user_id = '{admin_id}' WHERE created_by_user_id IS NULL"))
    conn.execute(sa.text(f"UPDATE script_drafts SET created_by_user_id = '{admin_id}' WHERE created_by_user_id IS NULL"))
    conn.execute(sa.text(f"UPDATE generation_tasks SET created_by_user_id = '{admin_id}' WHERE created_by_user_id IS NULL"))

    op.alter_column('world_drafts', 'created_by_user_id', nullable=False)
    op.alter_column('script_drafts', 'created_by_user_id', nullable=False)
    op.alter_column('generation_tasks', 'created_by_user_id', nullable=False)

    op.create_foreign_key('fk_world_drafts_user', 'world_drafts', 'users', ['created_by_user_id'], ['id'])
    op.create_foreign_key('fk_script_drafts_user', 'script_drafts', 'users', ['created_by_user_id'], ['id'])
    op.create_foreign_key('fk_generation_tasks_user', 'generation_tasks', 'users', ['created_by_user_id'], ['id'])
    op.create_index('idx_world_drafts_user', 'world_drafts', ['created_by_user_id'])
    op.create_index('idx_script_drafts_user', 'script_drafts', ['created_by_user_id'])
    op.create_index('idx_generation_tasks_user', 'generation_tasks', ['created_by_user_id'])

    # worlds / scripts: nullable（官方/seed 不强制）
    op.add_column('worlds', sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
    op.add_column('scripts', sa.Column('created_by_user_id', sa.Uuid(as_uuid=False), nullable=True))
    op.create_foreign_key('fk_worlds_user', 'worlds', 'users', ['created_by_user_id'], ['id'])
    op.create_foreign_key('fk_scripts_user', 'scripts', 'users', ['created_by_user_id'], ['id'])
    op.create_index('idx_worlds_user', 'worlds', ['created_by_user_id'])
    op.create_index('idx_scripts_user', 'scripts', ['created_by_user_id'])


def downgrade():
    for tbl in ['scripts', 'worlds', 'generation_tasks', 'script_drafts', 'world_drafts']:
        op.drop_index(f'idx_{tbl}_user', table_name=tbl)
        op.drop_constraint(f'fk_{tbl}_user', tbl, type_='foreignkey')
        op.drop_column(tbl, 'created_by_user_id')
```

跑迁移：

```bash
cd backend && alembic upgrade head
```

如果失败说"no admin user"，先：

```bash
cd backend && python -c "
import asyncio
from database import async_session_maker
from models.user import User
from utils import utcnow

async def make_admin():
    async with async_session_maker() as s:
        u = User(is_admin=True, nickname='bootstrap admin')
        s.add(u)
        await s.commit()
        print('Created admin user:', u.id)

asyncio.run(make_admin())
"
```

然后重试 `alembic upgrade head`。

- [ ] **Step 7: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_ownership_fields.py -v
```

- [ ] **Step 8: 修改 GenerationTaskService 用 user_id 替代 admin_user_id**

打开 `backend/services/generation_task_service.py`。当前 `start_world_generation` / `start_script_generation` 等函数有 `admin_user_id: str | None = None` 参数。把参数全部重命名为 `user_id`，request_payload 里 `"admin_user_id"` 改 `"user_id"`，并把新建的 task 设 `created_by_user_id=user_id`。

```python
# 旧
async def start_world_generation(self, ..., admin_user_id: str | None = None):
    ...
    if admin_user_id:
        await self._acquire_generation_task_limit_lock(session, admin_user_id)
        await self._enforce_generation_task_limit(session, admin_user_id)
    ...
    request_payload = {
        ...
        "admin_user_id": admin_user_id,
    }

# 新
async def start_world_generation(self, ..., user_id: str):
    ...
    await self._acquire_generation_task_limit_lock(session, user_id)
    await self._enforce_generation_task_limit(session, user_id)
    ...
    task = GenerationTask(
        ...
        created_by_user_id=user_id,
        request_payload={..., "user_id": user_id},
    )
```

把 `MAX_ACTIVE_TASKS_PER_ADMIN` 改名 `MAX_ACTIVE_TASKS_PER_USER`，值仍 2（实际配额由 §4.2 在更上一层 API 层做基于 `is_admin` 的 differentiation）。

- [ ] **Step 9: 修改 admin.py 调用点**

`grep -n "admin_user_id" backend/api/admin.py` 找所有调用，改成传 `user_id=current_admin_user.id`（admin 也是 user，user_id 就是 admin 的 user.id）。

- [ ] **Step 10: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

预期：全 pass，含老的 `test_generation_task_limit.py`。

---

### Task B3: UserCreationQuota + users.can_create

**Files:**
- Modify: `backend/models/user.py`（加 `can_create` 字段）
- Create: `backend/models/quota.py`
- Create: `backend/services/quota_service.py`
- Modify: `backend/config.py` 或 `backend/settings.py`（加 daily quota 配置）
- Create: `backend/migrations/versions/<timestamp>_add_quota_and_can_create.py`
- Test: `backend/tests/test_quota_service.py`

- [ ] **Step 1: 写 quota 测试（failing）**

Create `backend/tests/test_quota_service.py`:

```python
import pytest
from datetime import date

from services.quota_service import (
    consume_world_generation_quota,
    consume_script_generation_quota,
    QuotaExceeded,
)


@pytest.mark.asyncio
async def test_consume_world_quota_first_time(db_session, sample_user):
    # 第一次扣减
    remaining = await consume_world_generation_quota(db_session, sample_user.id, daily_limit=2)
    assert remaining == 1


@pytest.mark.asyncio
async def test_consume_world_quota_exhausts(db_session, sample_user):
    await consume_world_generation_quota(db_session, sample_user.id, daily_limit=2)
    await consume_world_generation_quota(db_session, sample_user.id, daily_limit=2)
    with pytest.raises(QuotaExceeded):
        await consume_world_generation_quota(db_session, sample_user.id, daily_limit=2)


@pytest.mark.asyncio
async def test_admin_bypass_via_unlimited_flag(db_session, sample_user):
    # daily_limit=None 表示无限（admin）
    for _ in range(50):
        await consume_world_generation_quota(db_session, sample_user.id, daily_limit=None)


@pytest.mark.asyncio
async def test_quota_separates_by_date(db_session, sample_user):
    # 这个测试隐含约定：quota 按 date 隔离。如果想测跨日期需要 freezegun，先跳过。
    pass
```

- [ ] **Step 2: 实现 UserCreationQuota model**

Create `backend/models/quota.py`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class UserCreationQuota(Base):
    __tablename__ = "user_creation_quotas"
    __table_args__ = (
        UniqueConstraint("user_id", "quota_date", name="uq_user_quota_per_day"),
        Index("idx_user_quota_user_date", "user_id", "quota_date"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    quota_date: Mapped[date] = mapped_column(Date)
    world_generations: Mapped[int] = mapped_column(Integer, default=0)
    script_generations: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
```

- [ ] **Step 3: 给 users 加 can_create**

Modify `backend/models/user.py` User class（在 `is_admin` 后）：

```python
    can_create: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 4: 写迁移**

```bash
cd backend && alembic revision -m "add user creation quota and can_create"
```

```python
def upgrade():
    op.add_column('users', sa.Column('can_create', sa.Boolean(), nullable=False, server_default=sa.false()))
    # admin 默认 can_create=True
    op.execute("UPDATE users SET can_create = TRUE WHERE is_admin = TRUE")

    op.create_table(
        'user_creation_quotas',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('quota_date', sa.Date(), nullable=False),
        sa.Column('world_generations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('script_generations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'quota_date', name='uq_user_quota_per_day'),
    )
    op.create_index('idx_user_quota_user_date', 'user_creation_quotas', ['user_id', 'quota_date'])


def downgrade():
    op.drop_index('idx_user_quota_user_date', table_name='user_creation_quotas')
    op.drop_table('user_creation_quotas')
    op.drop_column('users', 'can_create')
```

跑：

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 5: 实现 quota_service**

Create `backend/services/quota_service.py`:

```python
from datetime import date
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.quota import UserCreationQuota


class QuotaExceeded(Exception):
    def __init__(self, kind: str, used: int, limit: int):
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"{kind} quota exceeded: {used}/{limit}")


async def _consume(db: AsyncSession, user_id: str, field: str, daily_limit: int | None) -> int:
    """Consume 1 quota for the given field. Returns remaining. Raises QuotaExceeded if over."""
    today = date.today()

    # Postgres ON CONFLICT 原子 upsert
    stmt = pg_insert(UserCreationQuota).values(
        user_id=user_id,
        quota_date=today,
        **{field: 1},
    ).on_conflict_do_update(
        index_elements=["user_id", "quota_date"],
        set_={field: getattr(UserCreationQuota, field) + 1},
    ).returning(getattr(UserCreationQuota, field))

    result = await db.execute(stmt)
    new_count = result.scalar_one()
    await db.commit()

    if daily_limit is None:  # 无限
        return -1

    if new_count > daily_limit:
        # 回滚此次计数
        # 简化：因为是单调递增，超额仅意味着拒绝下一次请求。
        # 真正干净的做法是事务内 SELECT FOR UPDATE 再判断后 INSERT；当前为简洁版。
        raise QuotaExceeded(field, new_count, daily_limit)

    return daily_limit - new_count


async def consume_world_generation_quota(db: AsyncSession, user_id: str, daily_limit: int | None) -> int:
    return await _consume(db, user_id, "world_generations", daily_limit)


async def consume_script_generation_quota(db: AsyncSession, user_id: str, daily_limit: int | None) -> int:
    return await _consume(db, user_id, "script_generations", daily_limit)
```

- [ ] **Step 6: 加 settings 配置项**

打开 `backend/config.py`（或定义 settings 的地方），加：

```python
    workshop_world_generations_per_day: int = 2
    workshop_script_generations_per_day: int = 3
```

- [ ] **Step 7: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_quota_service.py -v
```

- [ ] **Step 8: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

---

### Task B4: 发布 / 下架 service

**Files:**
- Create: `backend/services/publish_service.py`
- Test: `backend/tests/test_publish_service.py`

- [ ] **Step 1: 写测试（failing）**

Create `backend/tests/test_publish_service.py`:

```python
import pytest
from engine.content_status import ContentStatus
from services.publish_service import publish_world_draft, withdraw_world


@pytest.mark.asyncio
async def test_publish_draft_to_published(db_session, sample_user, sample_world_draft):
    sample_world_draft.created_by_user_id = sample_user.id
    await db_session.commit()

    world = await publish_world_draft(db_session, draft_id=sample_world_draft.id, actor_user_id=sample_user.id, audit_enabled=False)
    assert world.status == ContentStatus.PUBLISHED
    assert world.created_by_user_id == sample_user.id


@pytest.mark.asyncio
async def test_publish_rejects_non_owner(db_session, sample_user, other_user, sample_world_draft):
    sample_world_draft.created_by_user_id = sample_user.id
    await db_session.commit()

    with pytest.raises(PermissionError):
        await publish_world_draft(db_session, draft_id=sample_world_draft.id, actor_user_id=other_user.id, audit_enabled=False)


@pytest.mark.asyncio
async def test_withdraw_by_owner_returns_to_draft(db_session, sample_user, sample_published_world):
    sample_published_world.created_by_user_id = sample_user.id
    await db_session.commit()

    await withdraw_world(db_session, world_id=sample_published_world.id, actor_user_id=sample_user.id, by_admin=False)
    await db_session.refresh(sample_published_world)
    assert sample_published_world.status == ContentStatus.DRAFT
```

- [ ] **Step 2: 实现 publish_service**

Create `backend/services/publish_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.content_status import ContentStatus, can_transition, next_status_on_publish, next_status_on_withdraw
from models.draft import WorldDraft, ScriptDraft
from models.world import World
from models.script import Script


async def publish_world_draft(
    db: AsyncSession,
    *,
    draft_id: str,
    actor_user_id: str,
    audit_enabled: bool = False,
) -> World:
    """Publish a world draft. Single transaction.

    1. Load draft, verify ownership
    2. Compute target status (published or submitted depending on audit)
    3. Create or update worlds row
    4. (Phase 1) keep draft row; future cleanup separate
    """
    draft = (await db.execute(select(WorldDraft).where(WorldDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if draft.created_by_user_id != actor_user_id:
        raise PermissionError("Not owner")

    target_status = next_status_on_publish(audit_enabled=audit_enabled)

    if draft.world_id:
        world = (await db.execute(select(World).where(World.id == draft.world_id))).scalar_one()
        # 校验状态转换
        if not can_transition(ContentStatus(world.status), target_status):
            raise ValueError(f"Invalid transition: {world.status} → {target_status}")
        # 把 draft.payload 内容刷回 world（字段映射在创作工坊 service 里）
        _apply_payload_to_world(world, draft.payload)
        world.status = target_status
    else:
        world = _new_world_from_payload(draft.payload, owner_user_id=actor_user_id, status=target_status)
        db.add(world)
        await db.flush()
        draft.world_id = world.id

    await db.commit()
    return world


async def withdraw_world(
    db: AsyncSession,
    *,
    world_id: str,
    actor_user_id: str,
    by_admin: bool = False,
) -> World:
    world = (await db.execute(select(World).where(World.id == world_id))).scalar_one_or_none()
    if not world:
        raise ValueError(f"World {world_id} not found")
    if not by_admin and world.created_by_user_id != actor_user_id:
        raise PermissionError("Not owner")

    target = next_status_on_withdraw(by_admin=by_admin)
    if not can_transition(ContentStatus(world.status), target):
        raise ValueError(f"Invalid withdraw: {world.status} → {target}")

    world.status = target
    await db.commit()
    return world


def _apply_payload_to_world(world: World, payload: dict) -> None:
    """Map draft.payload structure onto World ORM fields.

    复用现有 admin publish 逻辑里的字段映射。
    打开 backend/api/admin.py::publish_world_draft 函数找现有的 mapping，
    搬到这里。
    """
    for key in ("name", "description", "genre", "era", "base_setting", "free_setting", "script_setting"):
        if key in payload:
            setattr(world, key, payload[key])
    if "difficulty" in payload:
        world.difficulty = int(payload["difficulty"])
    if "estimated_time" in payload:
        world.estimated_time = payload["estimated_time"]
    if "locations" in payload:
        world.locations_data = payload["locations"]
    if "cover_image" in payload:
        world.cover_image = payload["cover_image"]
    if "hero_image" in payload:
        world.hero_image = payload["hero_image"]
    # 其他字段按现有 admin.py 的映射补全


def _new_world_from_payload(payload: dict, *, owner_user_id: str, status: str) -> World:
    return World(
        name=payload.get("name", "Untitled"),
        description=payload.get("description", ""),
        genre=payload.get("genre", "mystery"),
        era=payload.get("era", "modern"),
        difficulty=int(payload.get("difficulty", 3)),
        estimated_time=payload.get("estimated_time", "30-60 min"),
        base_setting=payload.get("base_setting", ""),
        locations_data=payload.get("locations", []),
        free_setting=payload.get("free_setting"),
        script_setting=payload.get("script_setting"),
        cover_image=payload.get("cover_image", ""),
        hero_image=payload.get("hero_image", ""),
        status=status,
        created_by_user_id=owner_user_id,
    )
```

> **⚠️ Mapping 复用**：`_apply_payload_to_world` 和 `_new_world_from_payload` 应该尽量复用现有 `backend/api/admin.py:publish_world_draft` 里的字段映射代码。先 grep 找到，再搬过来：
>
> ```bash
> grep -n "publish_world_draft\|locations_data\|base_setting" backend/api/admin.py | head -30
> ```

- [ ] **Step 3: 实现 script 版本（同样的 pattern）**

在 `publish_service.py` 加：

```python
async def publish_script_draft(db: AsyncSession, *, draft_id: str, actor_user_id: str, audit_enabled: bool = False) -> Script:
    ...  # 类似 world 版本，操作 ScriptDraft + Script

async def withdraw_script(db: AsyncSession, *, script_id: str, actor_user_id: str, by_admin: bool = False) -> Script:
    ...
```

代码结构镜像 world 版。

- [ ] **Step 4: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_publish_service.py -v
```

- [ ] **Step 5: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

---

## Phase C — 路由与权限

### Task C1: Backend `/workshop/*` 路由

**Files:**
- Create: `backend/api/workshop.py`
- Modify: `backend/main.py`（注册 workshop router）
- Modify: `backend/api/admin.py`（保持现有功能，**不删**）
- Test: `backend/tests/test_workshop_api.py`

- [ ] **Step 1: 写 API 测试（failing）**

Create `backend/tests/test_workshop_api.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workshop_world_drafts_returns_only_my_drafts(client: AsyncClient, user_a, user_b, draft_of_a, draft_of_b, login_as):
    await login_as(user_a)
    r = await client.get("/api/workshop/world-drafts")
    assert r.status_code == 200
    data = r.json()["data"]
    ids = [d["id"] for d in data]
    assert draft_of_a.id in ids
    assert draft_of_b.id not in ids


@pytest.mark.asyncio
async def test_workshop_create_blocked_without_can_create(client, user_no_quota, login_as):
    await login_as(user_no_quota)
    r = await client.post("/api/workshop/world-generation-tasks", json={"prompt": "test", "genre": "mystery", "era": "modern"})
    assert r.status_code == 403  # not on whitelist


@pytest.mark.asyncio
async def test_workshop_create_consumes_quota(client, user_with_quota, login_as):
    await login_as(user_with_quota)
    # 默认 daily_limit=2，发起 3 次第 3 次应 429
    for i in range(2):
        r = await client.post("/api/workshop/world-generation-tasks", json={"prompt": "test", "genre": "mystery", "era": "modern"})
        assert r.status_code in (200, 201)
    r = await client.post("/api/workshop/world-generation-tasks", json={"prompt": "test", "genre": "mystery", "era": "modern"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_admin_can_see_all_workshop_drafts(client, admin_user, draft_of_a, draft_of_b, login_as):
    await login_as(admin_user)
    r = await client.get("/api/admin/world-drafts")  # admin 路由保留
    data = r.json()["data"]
    ids = [d["id"] for d in data]
    assert draft_of_a.id in ids
    assert draft_of_b.id in ids
```

- [ ] **Step 2: 实现 workshop router**

Create `backend/api/workshop.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import get_current_user
from models.draft import ScriptDraft, WorldDraft
from models.user import User
from services import publish_service, quota_service
from services.generation_task_service import GenerationTaskService
from services.quota_service import QuotaExceeded

router = APIRouter(prefix="/api/workshop", tags=["workshop"])


def _require_can_create(user: User) -> None:
    if not (user.can_create or user.is_admin):
        raise HTTPException(status_code=403, detail={"code": 40300, "message": "Not in creator whitelist"})


@router.get("/world-drafts")
async def list_my_world_drafts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    drafts = (
        await db.execute(
            select(WorldDraft)
            .where(WorldDraft.created_by_user_id == user.id)
            .order_by(WorldDraft.updated_at.desc())
        )
    ).scalars().all()
    return {"code": 0, "data": [_serialize_world_draft(d) for d in drafts], "message": "ok"}


@router.get("/script-drafts")
async def list_my_script_drafts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    drafts = (
        await db.execute(
            select(ScriptDraft)
            .where(ScriptDraft.created_by_user_id == user.id)
            .order_by(ScriptDraft.updated_at.desc())
        )
    ).scalars().all()
    return {"code": 0, "data": [_serialize_script_draft(d) for d in drafts], "message": "ok"}


@router.post("/world-generation-tasks", status_code=201)
async def start_world_generation(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_can_create(user)
    try:
        daily_limit = None if user.is_admin else settings.workshop_world_generations_per_day
        await quota_service.consume_world_generation_quota(db, user.id, daily_limit)
    except QuotaExceeded as e:
        raise HTTPException(status_code=429, detail={"code": 42901, "message": f"Daily quota exceeded ({e.used}/{e.limit})"})

    svc = GenerationTaskService(...)  # 实际构造按 api/admin.py 已有 pattern
    task = await svc.start_world_generation(
        prompt=body["prompt"],
        genre=body.get("genre", "mystery"),
        era=body.get("era", "modern"),
        user_id=user.id,
    )
    return {"code": 0, "data": {"task_id": task.id, "draft_id": task.draft_id}, "message": "ok"}


# 类似地实现 /script-generation-tasks
# 类似地实现 GET /generation-tasks/{id}/stream（复用 admin.py 的 SSE helper，加 ownership 校验：admin 可看所有，普通 user 只能看自己的）
# 类似地实现 POST /world-drafts/{id}/publish
# 类似地实现 POST /worlds/{id}/withdraw
# 类似地实现 DELETE /world-drafts/{id}


def _serialize_world_draft(d: WorldDraft) -> dict:
    return {
        "id": d.id,
        "world_id": d.world_id,
        "payload": d.payload,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


def _serialize_script_draft(d: ScriptDraft) -> dict:
    return {
        "id": d.id,
        "world_id": d.world_id,
        "script_id": d.script_id,
        "payload": d.payload,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
```

> **⚠️ 实际实现注意**：上面是骨架，具体 endpoint 列表请参照 `backend/api/admin.py` 现有的所有 workshop 相关路由（grep `/api/admin/world` / `/api/admin/script` / `/api/admin/generation-tasks`），逐个加 user 版本。**核心区别**：
> 1. 用 `get_current_user` 替代 `get_current_admin_user`
> 2. 列表 query `.where(... == user.id)` 加 ownership 过滤
> 3. 单条操作（publish/withdraw/delete）做 ownership 校验，失败 raise 403
> 4. 创建型操作前加 quota 检查 + can_create 检查

- [ ] **Step 3: 注册 router**

Modify `backend/main.py`：

```python
from api import workshop
app.include_router(workshop.router)
```

- [ ] **Step 4: 跑测试确认 pass**

```bash
cd backend && python -m pytest tests/test_workshop_api.py -v
```

- [ ] **Step 5: 验证 /admin/* 端点仍然工作**

```bash
cd backend && python -m pytest tests/test_admin_generation_tasks_api.py tests/test_admin_drafts_api.py -v
```

预期：全 pass（admin 路由没动）。

- [ ] **Step 6: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

---

### Task C2: 前端 `/workshop/*` 路由（UI 复用）

**Files:**
- Create: `frontend/app/workshop/page.tsx`（复制 `app/admin/page.tsx`，删 models tab）
- Create: `frontend/app/workshop/generate/world/...`（复制 `app/admin/generate/world/...`）
- Create: `frontend/app/workshop/generate/script/...`
- Create: `frontend/app/workshop/worlds/drafts/[id]/...`
- Create: `frontend/app/workshop/scripts/drafts/[id]/...`
- Create: `frontend/lib/workshop-api.ts`
- Modify: `frontend/components/admin/workshop/WorkshopHeader.tsx`（参数化是否显示 models tab）

- [ ] **Step 1: 复制 workshop-api.ts**

Create `frontend/lib/workshop-api.ts`，复制 `frontend/lib/admin-api.ts` 内容：

```bash
cp frontend/lib/admin-api.ts frontend/lib/workshop-api.ts
```

然后打开 `workshop-api.ts`，把 export 名 `adminFetch` 改为 `workshopFetch`（如果有 admin 专属 header 一并去掉，通常没有，因为用 cookie）。同时把所有 `/api/admin/` URL 替换为 `/api/workshop/`：

```typescript
// 在 workshopFetch 函数内或调用处统一把路径 prefix 调整为 /api/workshop
```

- [ ] **Step 2: 复制并修改 WorkshopHeader 接受 showModels prop**

Modify `frontend/components/admin/workshop/WorkshopHeader.tsx`：

```typescript
type WorkshopTab = "worlds" | "scripts" | "models";

interface WorkshopHeaderProps {
  activeTab: WorkshopTab;
  onTabChange: (tab: WorkshopTab) => void;
  onCtaClick?: () => void;
  showModels?: boolean; // 新增，默认 true（admin 用）
}

export function WorkshopHeader({ ..., showModels = true }: WorkshopHeaderProps) {
  // 渲染 tabs 时根据 showModels 决定是否渲染 "models" tab
  const tabs: WorkshopTab[] = showModels ? ["worlds", "scripts", "models"] : ["worlds", "scripts"];
  // ... rest
}
```

- [ ] **Step 3: 复制 admin/page.tsx 到 workshop/page.tsx，去 models tab**

```bash
mkdir -p frontend/app/workshop
cp frontend/app/admin/page.tsx frontend/app/workshop/page.tsx
```

打开 `frontend/app/workshop/page.tsx`：

1. 把 `import { adminFetch } from "@/lib/admin-api";` 改为 `import { workshopFetch } from "@/lib/workshop-api";`
2. 全文 `adminFetch` 替换为 `workshopFetch`
3. URL 全文 `/api/admin/` 替换为 `/api/workshop/`
4. `router.push("/admin/...` 全文替换为 `router.push("/workshop/...`
5. 在 `<WorkshopHeader ... />` 调用处加 `showModels={false}`
6. 删除整段 `{tab === "models" && (...)}` 块
7. `parseTabParam` 函数把 `"models"` 分支删掉，只保留 `"scripts"`，其他 → `"worlds"`

- [ ] **Step 4: 复制其他子路由**

```bash
cp -r frontend/app/admin/generate frontend/app/workshop/generate
cp -r frontend/app/admin/worlds frontend/app/workshop/worlds
cp -r frontend/app/admin/scripts frontend/app/workshop/scripts
```

在每个复制过去的 `.tsx`：
- `adminFetch` → `workshopFetch`
- import 路径同步
- 所有 `/admin/` 路径替换 `/workshop/`
- 移除任何 admin-only 的 UI 条件（如果有的话，比如检查 `is_admin` 才渲染的按钮）

可以用脚本批量处理：

```bash
find frontend/app/workshop -type f \( -name "*.tsx" -o -name "*.ts" \) -exec sed -i '' \
  -e 's|adminFetch|workshopFetch|g' \
  -e 's|@/lib/admin-api|@/lib/workshop-api|g' \
  -e 's|/api/admin/|/api/workshop/|g' \
  -e 's|"/admin/|"/workshop/|g' \
  -e "s|'/admin/|'/workshop/|g" \
  {} \;
```

- [ ] **Step 5: 启 dev server，浏览器验证**

```bash
cd frontend && npm run dev
```

浏览器开 `http://localhost:3000/workshop` —— 应该看到 worlds/scripts tabs（无 models），列表为空（除非该用户 admin 已有草稿）。

测试场景：
- 普通用户登录 → 进 `/workshop` → 看到 tabs，列表数据 = 自己的草稿
- Admin 登录 → 既能进 `/workshop`（看自己）也能进 `/admin`（看全部）
- 普通用户敲 `/admin` URL → 后端 401/403（已有 `get_current_admin_user`）

- [ ] **Step 6: 修改 navbar 移除 /admin 入口（如有）**

`grep -rn "/admin" frontend/components/ | grep -v node_modules | grep -iE "(navbar|header|menu|nav)"` 找主 navbar。如果导航里有 admin 链接，去掉（保留 `/workshop` 链接给普通用户）。

如果没找到 navbar 暴露 admin，跳过此步。

- [ ] **Step 7: Lint**

```bash
cd frontend && npm run lint
```

预期：无新增 ESLint 错误。

- [ ] **Step 8: Checkpoint**

手动验证：
- [ ] 普通用户能进 `/workshop`
- [ ] 普通用户敲 `/admin` 被拒（后端 403）
- [ ] Admin 进 `/workshop` 看到自己的；进 `/admin` 看到全部
- [ ] `/workshop` 没有 models tab
- [ ] Navbar 不显示 admin 链接

---

### Task C3: Cookie 跨子域准备（**仅修配置，不立即生效**）

**Files:**
- Modify: `backend/services/auth_service.py` 或 `backend/api/auth.py`（cookie 设置处）
- Modify: `backend/config.py`

> **背景**：未来 `admin.xxx.com` 上线时需要 session cookie 跨子域共享。本期先把 cookie domain 改成可配置，preprod 默认空（localhost 不需要 domain），prod 设 `.xxx.com`。

- [ ] **Step 1: 找 cookie 设置代码**

```bash
grep -rn "set_cookie\|response.set_cookie" backend/api/ backend/services/
```

定位到 `set_cookie(...)` 调用处（通常在 login handler 里）。

- [ ] **Step 2: 加配置项**

Modify `backend/config.py`：

```python
    session_cookie_domain: str | None = None  # prod 设 ".xxx.com"
```

- [ ] **Step 3: 改 set_cookie 用配置项**

修改 cookie 设置调用，加 `domain` 参数：

```python
response.set_cookie(
    key="session_id",
    value=session_id,
    httponly=True,
    secure=True,
    samesite="lax",
    max_age=...,
    domain=settings.session_cookie_domain,  # 新增
)
```

- [ ] **Step 4: 验证现有行为不变**

```bash
cd backend && python -m pytest tests/test_auth.py -v
```

预期：测试中 `session_cookie_domain=None`，cookie 行为跟之前一样。

- [ ] **Step 5: 文档化部署变更**

在 `docs/operations/deploy-and-config.md` 或 `MIGRATION_NOTES.md` 加一行：

```markdown
- 2026-05-14：`session_cookie_domain` 配置项加入。**仅在新管理员站（admin.xxx.com）上线时设为 `.xxx.com`**，本期可不设。
```

- [ ] **Step 6: Checkpoint**

```bash
cd backend && python -m pytest tests/ -x -q
```

---

## Phase D — 验证

### Task D1: 端到端手动 smoke test

> 没有自动化 E2E 测试基础设施，本步骤是人工 checklist。

- [ ] **Step 1: 启动栈**

```bash
docker compose up -d db redis
cd backend && alembic upgrade head
cd backend && uvicorn main:app --reload --port 8000 &
cd frontend && npm run dev &
```

- [ ] **Step 2: 准备测试数据**

```bash
cd backend && python -c "
import asyncio
from database import async_session_maker
from models.user import User

async def setup():
    async with async_session_maker() as s:
        # 普通用户 with quota
        u1 = User(is_admin=False, can_create=True, nickname='alice')
        # 普通用户 without quota
        u2 = User(is_admin=False, can_create=False, nickname='bob')
        s.add_all([u1, u2])
        await s.commit()
        print('alice:', u1.id, 'bob:', u2.id)

asyncio.run(setup())
"
```

- [ ] **Step 3: 验证 - alice 能创作**

- 登录 alice
- 访问 `/workshop`
- 点"新建世界"
- 走完生成流程
- 看到草稿在列表
- 编辑草稿
- 发布
- 切去 `/discover` 看到 alice 发的世界

- [ ] **Step 4: 验证 - bob 不能创作**

- 登录 bob
- 访问 `/workshop`
- 点"新建世界" → 应被 403 拦

- [ ] **Step 5: 验证 - alice 看不到 bob 的内容**

- alice 在 `/workshop` 只看到自己的草稿
- admin 在 `/admin` 能看到所有人的草稿

- [ ] **Step 6: 验证 - 配额生效**

- alice 连续发起 3 次世界生成
- 第 3 次应被 429 拒绝

- [ ] **Step 7: 验证 - 成本数据沉淀**

- admin 在 `/admin/models` 给现有 provider_model 填入测试单价
- 让 alice 玩一局游戏（至少 1 个 turn）
- admin 访问 `/admin/analytics`，确认 `total_cost_cents > 0`

- [ ] **Step 8: 验证 - 下架重发**

- alice 把已发布的世界下架
- 草稿态可见，可编辑
- 修改后再次发布
- 在 `/discover` 看到更新

- [ ] **Step 9: 写验证报告**

Create `docs/superpowers/plans/2026-05-14-execution-report.md`，列每个步骤结果（pass / fail + 备注）。

---

## 完成定义（Definition of Done）

本 plan 完成的标志：

1. [ ] Phase A 全部任务 pass，`provider_models` 有单价字段，token_usage 写入开始非零 cost
2. [ ] Phase B 全部任务 pass，状态机正式化，ownership 字段全部就位
3. [ ] Phase C.1-C.2 pass，用户能在 `/workshop` 创作、发布、下架；admin 在 `/admin` 可见全部
4. [ ] Phase C.3 cookie 配置项就位（值仍空 / 本期无需 admin.xxx.com）
5. [ ] Phase D 手动 smoke test 全 pass
6. [ ] 至少 5 次成功的端到端世界生成 + 5 局游戏完成（让 cost 数据开始沉淀）

---

## 不在本 plan 内的事

| 项 | 何时做 |
|---|---|
| 新管理员站脚手架 + UI | 等用户提供 HTML 后单独立 plan |
| 删除主站 `/admin/*` | 新管理员站上线后 |
| 积分系统 | 等 2-4 周 cost 数据沉淀后立 spec → plan |
| 用户内容审核 UI | 审核需求明确后 |
| Model tier 抽象 | 跟积分系统配套 |
| UX 简化（用户视角的创作向导）| Phase 2 单独 spec |
