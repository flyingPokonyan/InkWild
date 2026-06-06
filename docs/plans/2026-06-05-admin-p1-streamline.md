# Admin P1：精简 + 内容事后治理 Implementation Plan

> **For agentic workers:** 用 superpowers:subagent-driven-development 或 executing-plans 逐任务执行。步骤用 `- [ ]` 勾选跟踪。
>
> **测试策略**：遵循 CLAUDE.md「轻量测试」——后端强制下架是关键路径，写 API 测试；前端改动与精简清理走 `npm run build` + 浏览器手动验证，不强制 TDD。

**Goal:** 把 admin 从「9 个平铺模块（含 1 个 mock 空壳 + 一堆该删的旧端点）」收敛成「4 分组、全部真数据」，并补上唯一的功能缺口——已发布内容的列表 + admin 强制下架。

**Architecture:** 三块。① 精简：nav 改 4 分组、砍 experiments/settings、删 `admin.py` 旧工坊端点（0 前端引用，保留 generation-tasks 三个 GET）。② 内容治理：新建 `admin_content.py` 路由，复用**已就绪**的 `publish_service.withdraw_world/script(by_admin=True)`（跳过 ownership，→ WITHDRAWN 终态）。③ 仪表盘补一张「待审内容」卡（后端已很完整，只缺这个字段）。

**Tech Stack:** FastAPI + SQLAlchemy async（后端）、Next.js 16 + TanStack Query（admin-frontend）。

---

## 核对结论（写本 plan 前已逐页验证，避免做无用功）

| 模块 | 真实状态 | 本轮动作 |
|---|---|---|
| experiments 实验评测 | **纯 mock 空壳**（`use-experiment.ts` 写死 mock，等的后端没来） | 砍导航，页面+mock 归档 |
| 用户管理 | 已扎实（封号/权限/积分/session/审计都有，含"不能封自己") | 不动 |
| 内容审核 | **只做了准入**（审草稿→发布），无"已发布内容列表 + 强制下架" | **P1-b 补齐** |
| 模型/成本/积分/生成记录/审计 | 真数据，后端完整，前端接好 | 不动 |
| 仪表盘 | 已很完整（6 KPI 卡 + 成本图表 + 高成本 session + 缺价告警 + 最近事件 + 自动刷新） | 只补「待审内容」卡 |
| `admin.py` 旧工坊端点 | 800+ 行 generate/drafts/worlds/scripts CRUD，**前端 0 引用**（按 D4 早该删） | **P1-a 删** |

## ⚠ 待用户拍板的产品决策

**admin 强制下架的语义**：现有 `publish_service` 里 admin 下架 = `WITHDRAWN` **终态**（作者无法自助恢复，只有 owner 自己下架才回 PRIVATE 可改）。本 plan 默认沿用「终态」语义，前端确认框文案据此写。若想改成「打回让作者修改后重新提审」，需改 `content_status.py` 的转移表 + `next_status_on_withdraw`，属额外范围，本轮不做。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `backend/api/admin_content.py` | 已发布内容列表 + admin 强制下架 | 新建 |
| `backend/main.py` | 注册 `admin_content_router` | 改 1 行 |
| `backend/tests/test_admin_content.py` | 下架终态 + 404 + 非 admin 403 | 新建 |
| `backend/api/admin.py` | 删旧工坊端点（保留 generation-tasks GET） | 删函数 |
| `backend/services/dashboard_service.py` | `dashboard_kpis` 加 `pending_reviews` | 改 |
| `admin-frontend/app/content/page.tsx` | 加「待审 / 已发布」两视图 | 改 |
| `admin-frontend/lib/nav.ts` | 4 分组、砍 experiments/settings | 重写 NAV |
| `admin-frontend/app/page.tsx` | 加「待审内容」KPI 卡 | 改 |
| `admin-frontend/lib/types.ts` | `DashboardKpis.pending_reviews` + 已发布内容类型 | 改 |

---

## Task 1：后端 admin_content 路由 + 测试（P1-b 核心）

**Files:**
- Create: `backend/api/admin_content.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_admin_content.py`

- [ ] **Step 1：写 `admin_content.py`**

```python
"""Admin 内容事后治理：跨用户列已发布世界/剧本 + 强制下架。

与 admin_review.py（准入：审草稿→发布）互补。强制下架复用
publish_service.withdraw_*(by_admin=True)：跳过 ownership，→ WITHDRAWN 终态。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_admin_user
from engine.content_status import ContentStatus
from models.script import Script
from models.user import User
from models.world import World
from services import publish_service
from services.audit_service import record_admin_action

router = APIRouter(
    prefix="/api/admin/content",
    tags=["admin-content"],
    dependencies=[Depends(get_current_admin_user)],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _author_names(db: AsyncSession, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    return {str(u.id): (u.nickname or "") for u in rows}


def _item(obj) -> dict:
    return {
        "id": str(obj.id),
        "name": obj.name,
        "author_id": str(obj.created_by_user_id) if obj.created_by_user_id else None,
        "status": obj.status,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }


@router.get("/worlds")
async def list_published_worlds(
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        select(World)
        .where(World.status == ContentStatus.PUBLISHED.value)
        .order_by(World.created_at.desc())
    )
    if q:
        stmt = stmt.where(World.name.ilike(f"%{q}%"))
    worlds = (await db.execute(stmt)).scalars().all()
    names = await _author_names(
        db, {str(w.created_by_user_id) for w in worlds if w.created_by_user_id}
    )
    items = [{**_item(w), "author": names.get(str(w.created_by_user_id), "")} for w in worlds]
    return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.get("/scripts")
async def list_published_scripts(
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        select(Script)
        .where(Script.status == ContentStatus.PUBLISHED.value)
        .order_by(Script.created_at.desc())
    )
    if q:
        stmt = stmt.where(Script.name.ilike(f"%{q}%"))
    scripts = (await db.execute(stmt)).scalars().all()
    names = await _author_names(
        db, {str(s.created_by_user_id) for s in scripts if s.created_by_user_id}
    )
    items = [{**_item(s), "author": names.get(str(s.created_by_user_id), "")} for s in scripts]
    return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.post("/worlds/{world_id}/withdraw")
async def admin_withdraw_world(
    world_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        world = await publish_service.withdraw_world(
            db, world_id=world_id, actor_user_id=admin.id, by_admin=True
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.world.withdraw",
        resource_type="world",
        resource_id=world_id,
        payload={"name": world.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {"code": 0, "data": {"id": world_id, "status": world.status}, "message": "ok"}


@router.post("/scripts/{script_id}/withdraw")
async def admin_withdraw_script(
    script_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        script = await publish_service.withdraw_script(
            db, script_id=script_id, actor_user_id=admin.id, by_admin=True
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.script.withdraw",
        resource_type="script",
        resource_id=script_id,
        payload={"name": script.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {"code": 0, "data": {"id": script_id, "status": script.status}, "message": "ok"}
```

- [ ] **Step 2：在 `main.py` 注册**

import 段加 `from api.admin_content import router as admin_content_router`，`include_router` 段加 `app.include_router(admin_content_router)`（放在 `admin_review_router` 之后）。

- [ ] **Step 3：写测试 `test_admin_content.py`**

> 注：`World` 还有别的 NOT NULL 字段，按 `backend/tests/` 现有 World 构造补齐（至少 `base_setting`）；下面只列本测试相关字段。`admin_client` / `auth_client` / `db` 夹具来自 `conftest.py`。

```python
import pytest
from httpx import AsyncClient

from models.user import User
from models.world import World


@pytest.mark.asyncio
async def test_admin_withdraw_world_terminal(admin_client: AsyncClient, db):
    owner = User(nickname="creator", is_admin=False)
    db.add(owner)
    await db.flush()
    world = World(name="违规世界", status="published", base_setting="x", created_by_user_id=owner.id)
    db.add(world)
    await db.commit()

    # 出现在已发布列表
    r = await admin_client.get("/api/admin/content/worlds")
    assert r.status_code == 200
    assert str(world.id) in [w["id"] for w in r.json()["data"]["items"]]

    # 强制下架 → 终态 withdrawn
    r = await admin_client.post(f"/api/admin/content/worlds/{world.id}/withdraw")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "withdrawn"

    # 从已发布列表消失
    r = await admin_client.get("/api/admin/content/worlds")
    assert str(world.id) not in [w["id"] for w in r.json()["data"]["items"]]


@pytest.mark.asyncio
async def test_withdraw_missing_world_404(admin_client: AsyncClient):
    r = await admin_client.post("/api/admin/content/worlds/00000000-0000-0000-0000-000000000000/withdraw")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_blocked(auth_client: AsyncClient):
    r = await auth_client.get("/api/admin/content/worlds")
    assert r.status_code == 403
```

- [ ] **Step 4：跑测试**

Run: `cd backend && python -m pytest tests/test_admin_content.py -v`
Expected: 3 passed（若 World 缺必填字段报错，按报错补字段重跑）

- [ ] **Step 5：commit**

```bash
git add backend/api/admin_content.py backend/main.py backend/tests/test_admin_content.py
git commit -m "feat(admin): 新增内容事后治理路由（已发布列表 + 强制下架）"
```

---

## Task 2：前端 content 页加「已发布内容」视图（P1-b 前端）

**Files:**
- Modify: `admin-frontend/app/content/page.tsx`
- Modify: `admin-frontend/lib/types.ts`（加 `PublishedContentItem`）

- [ ] **Step 1：types.ts 加类型**

```ts
export interface PublishedContentItem {
  id: string;
  name: string;
  author: string;
  author_id: string | null;
  status: string;
  created_at: string | null;
}
```

- [ ] **Step 2：content 页顶部加视图切换**

用现有 `Segmented` 组件（页面已 import 风格统一），在 `PageHeader` 下加 `view: "pending" | "published"` 状态。`pending` 视图 = 现有审草稿表格原样保留；`published` 视图 = 新表格。

- [ ] **Step 3：published 视图（世界 + 剧本各一张表，或 Segmented 切 kind）**

```tsx
const worldsQuery = useQuery({
  queryKey: ["admin-content-worlds"],
  queryFn: () => apiFetch<{ items: PublishedContentItem[] }>("/api/admin/content/worlds"),
  enabled: view === "published",
});
const scriptsQuery = useQuery({
  queryKey: ["admin-content-scripts"],
  queryFn: () => apiFetch<{ items: PublishedContentItem[] }>("/api/admin/content/scripts"),
  enabled: view === "published",
});

const withdraw = useMutation({
  mutationFn: ({ kind, id }: { kind: "worlds" | "scripts"; id: string }) =>
    apiFetch(`/api/admin/content/${kind}/${id}/withdraw`, { method: "POST" }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["admin-content-worlds"] });
    qc.invalidateQueries({ queryKey: ["admin-content-scripts"] });
  },
});
```

表格列：名称 / 作者 / 创建时间 / 操作（「强制下架」danger Btn）。

- [ ] **Step 4：下架二次确认（终态文案）**

用现有 `Modal` 组件包确认，文案明确终态：

> 强制下架《{name}》？此操作会让内容对全网不可见，**作者无法自助恢复**（区别于作者自己下架回私有库）。操作会记入审计日志。

确认后调 `withdraw.mutate({ kind, id })`。

- [ ] **Step 5：验证**

Run: `cd admin-frontend && npm run build`
Expected: 构建通过。再 `npm run dev` 开 3001，进 /content 切「已发布」→ 列表出现 → 点下架确认 → 该项消失（后端 status→withdrawn）。

- [ ] **Step 6：commit**

```bash
git add admin-frontend/app/content/page.tsx admin-frontend/lib/types.ts
git commit -m "feat(admin): 内容审核页加「已发布内容」视图 + 强制下架"
```

---

## Task 3：nav 改 4 分组 + 砍 experiments/settings（P1-a 前端）

**Files:**
- Modify: `admin-frontend/lib/nav.ts`

- [ ] **Step 1：重写 NAV 常量**

```ts
export const NAV: NavSection[] = [
  {
    label: "运营与支持",
    items: [
      { id: "dashboard", label: "仪表盘", href: "/", icon: LayoutDashboard },
      { id: "users", label: "用户管理", href: "/users", icon: Users },
      { id: "content", label: "内容审核", href: "/content", icon: FileText },
    ],
  },
  {
    label: "内容 & 模型",
    items: [
      { id: "generations", label: "生成记录", href: "/generations", icon: Sparkles },
      { id: "models", label: "模型管理", href: "/models", icon: Database },
    ],
  },
  {
    label: "分析与治理",
    items: [
      { id: "cost", label: "成本分析", href: "/cost", icon: Coins },
      { id: "credits", label: "积分经济", href: "/credits", icon: Wallet },
      { id: "audit", label: "审计日志", href: "/audit", icon: ClipboardList },
    ],
  },
];
```

删掉 `experiments` 与 `settings` 两项及其未再使用的 icon import（`Zap` / `Settings`）。

- [ ] **Step 2：归档 experiments 页面（不删，挪出路由）**

```bash
mkdir -p admin-frontend/_archive
git mv admin-frontend/app/experiments admin-frontend/_archive/experiments
git mv admin-frontend/lib/data/use-experiment.ts admin-frontend/_archive/use-experiment.ts
git mv admin-frontend/lib/mock admin-frontend/_archive/mock
git mv admin-frontend/components/experiments admin-frontend/_archive/components-experiments
```

> 若 build 报「找不到 experiments 引用」，grep `experiments|use-experiment|lib/mock` 清掉残留 import（应只剩归档内部互相引用）。

- [ ] **Step 3：验证**

Run: `cd admin-frontend && npm run build`
Expected: 通过。侧边栏 3 分组、无 experiments/settings。

- [ ] **Step 4：commit**

```bash
git add -A admin-frontend
git commit -m "refactor(admin): 侧边栏改分组，归档 mock 实验评测页"
```

---

## Task 4：删 admin.py 旧工坊端点（P1-a 后端，有风险，独立 commit）

**Files:**
- Modify: `backend/api/admin.py`

**删除清单**（这些端点前端 0 引用，已 grep 确认）：
`generate-world` · `generate-script` · `world-generation-tasks` · `script-generation-tasks` · `world-drafts`（含 continue-generation / GET / PUT / DELETE / publish）· `script-drafts`（含 GET / PUT / DELETE / publish）· `worlds`（GET / POST / publish）· `scripts`（GET / POST / publish）

**保留清单**（generations 页在用，**不要删**）：
`GET /generation-tasks` · `GET /generation-tasks/{task_id}` · `GET /generation-tasks/{task_id}/stream`

- [ ] **Step 1：删上述端点函数**，保留 generation-tasks 三个 GET + 文件顶部 router 定义 + 共享 helper/import。

- [ ] **Step 2：清理 admin.py 因删函数而未使用的 import**（IDE / `ruff check backend/api/admin.py` 提示）。

- [ ] **Step 3：再次确认无遗留引用**

Run: `grep -rn --include='*.ts' --include='*.tsx' -E "admin/(world-drafts|script-drafts|generate-world|generate-script)" admin-frontend frontend`
Expected: 无输出。

- [ ] **Step 4：后端启动 + 测试**

Run: `cd backend && python -c "import main" && python -m pytest tests/test_admin_api.py tests/test_admin_content.py -v`
Expected: import 无错；测试通过。

- [ ] **Step 5：commit**

```bash
git add backend/api/admin.py
git commit -m "refactor(admin): 删除 admin.py 旧工坊端点（D4，保留 generation-tasks 查询）"
```

---

## Task 5：仪表盘补「待审内容」卡（P1-c）

**Files:**
- Modify: `backend/services/dashboard_service.py`
- Modify: `admin-frontend/app/page.tsx`
- Modify: `admin-frontend/lib/types.ts`

- [ ] **Step 1：`dashboard_kpis` 加 pending_reviews**

在 `dashboard_kpis` 内（参照现有 `_scalar` 用法）加：

```python
from models.world import WorldDraft   # 若未 import
from models.script import ScriptDraft

pending_worlds = await _scalar(
    db,
    select(func.count()).select_from(WorldDraft).where(WorldDraft.review_status == "submitted"),
)
pending_scripts = await _scalar(
    db,
    select(func.count()).select_from(ScriptDraft).where(ScriptDraft.review_status == "submitted"),
)
```

返回 dict 加 `"pending_reviews": pending_worlds + pending_scripts`。

- [ ] **Step 2：types.ts `DashboardKpis` 加字段**

```ts
pending_reviews: number;
```

- [ ] **Step 3：page.tsx 加 KPI 卡**（放 kpi-grid 内，FileText/ClipboardList icon）

```tsx
<KpiCard
  icon={ClipboardList}
  label="待审内容"
  value={kpis?.pending_reviews ?? "—"}
  unit="项"
  deltaLabel={kpis?.pending_reviews ? "前往内容审核" : "暂无待审"}
/>
```

可包 `<Link href="/content">` 让卡片可点。

- [ ] **Step 4：验证**

Run: `cd backend && python -m pytest tests/ -k dashboard -v` + `cd admin-frontend && npm run build`
Expected: 通过；仪表盘出现「待审内容」卡。

- [ ] **Step 5：commit**

```bash
git add backend/services/dashboard_service.py admin-frontend/app/page.tsx admin-frontend/lib/types.ts
git commit -m "feat(admin): 仪表盘加「待审内容」KPI 卡"
```

---

## Self-Review 检查

- **Spec 覆盖**：P1-a（nav 分组 Task3 + 删端点 Task4）✓、P1-b（后端 Task1 + 前端 Task2）✓、P1-c（Task5）✓。
- **类型一致**：后端 `pending_reviews` ↔ 前端 `DashboardKpis.pending_reviews` ✓；`PublishedContentItem` 字段 ↔ 后端 `_item()` 返回 ✓（`author` 在列表端点合并注入）。
- **依赖就绪**：`withdraw_world/script(by_admin=True)`、`ContentStatus.PUBLISHED`、`record_admin_action`、`admin_client` 夹具均已存在并验证。

## 验收口径

- /content 能切「待审 / 已发布」，已发布列表跨用户，强制下架后该内容全网不可见且写审计（`content.world.withdraw`）。
- 侧边栏 3 分组、无 experiments/settings；`admin.py` 旧工坊端点删除、generations 页仍正常。
- 仪表盘有「待审内容」卡。
- `python -m pytest tests/test_admin_content.py` 通过；`admin-frontend npm run build` 通过。

## 不在本轮（P2 另起 plan）

玩家会话排查 · 产品/留存数据分析 · 运营位/推荐管理 · 角色与权限分级。
