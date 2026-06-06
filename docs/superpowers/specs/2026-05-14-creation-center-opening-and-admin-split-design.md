# 创作中心开放给用户 + 管理站拆分 设计文档

> 日期：2026-05-14
> 状态：Draft — 待 review
> 作者：jie + Claude（brainstorm 结果）

## 1. 背景与目标

### 1.1 当前痛点

- 创作工坊（生成世界 / 生成剧本）目前是 admin 专属，普通用户无法创作
- 内容生产瓶颈在 admin 一人，世界/剧本扩量难
- LLM 实际成本未统计：`provider_models` 表没有单价字段，`token_usage.cost_cents` 实际写入是 0
- 当前 `/admin/*` 路由跟用户站混在一起，视觉与权限边界不清

### 1.2 本次要解决的事

1. **创作工坊开放给所有登录用户**，内容按 `user_id` 隔离，admin 能看全部
2. **拆出独立管理员站**（新 Next.js 项目，独立子域名，用户不可发现），将 provider/model/slot 等系统配置迁过去
3. **`provider_models` 加单价字段**，让真实成本数据开始沉淀
4. **正式化"草稿 ↔ 发布"状态机**，为未来审核流程预留扩展点

### 1.3 不在本次范围（hang 住）

- ❌ 积分系统 / 充值消费明细 — 等成本数据沉淀 2-4 周后单独立 spec
- ❌ Tier 抽象（模型档位） — 同上
- ❌ 用户创世内容审核工作流 — 状态机预留 `submitted` 值，实际审核 UI 后续做
- ❌ 管理员站的视觉/UI 设计 — 用户自己用 Claude design 设计后给 HTML，本 spec 只给设计 brief（见 §6）

---

## 2. 架构总览

```
┌────────────────────┐    ┌──────────────────────┐
│ 主站（用户）         │    │ 管理员站（新建）       │
│ xxx.com            │    │ admin.xxx.com         │
│ Next.js（现有）     │    │ Next.js（新建）       │
└──────────┬─────────┘    └──────────┬───────────┘
           │                         │
           └──────────┬──────────────┘
                      ↓
              ┌──────────────────┐
              │ FastAPI Backend  │
              │（同一个）          │
              └──────────────────┘
                      ↓
              ┌──────────────────┐
              │ PostgreSQL/Redis │
              └──────────────────┘
```

- **共享同一 backend**：admin 站不另开服务，只调 `get_current_admin_user` 鉴权过的路由
- **Cookie 跨子域**：把 web_session cookie domain 设为 `.xxx.com`，admin 站登录后用户站也认（admin 也是用户）
- **路由分离**：admin 站不暴露在用户站的任何链接里；用户站不能渲染任何 admin 路由

---

## 3. 数据模型变更

### 3.1 provider_models — 加单价字段（最优先）

```python
class ProviderModel(Base):
    # ... 现有字段不变
    input_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_price_cents_per_image: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 仅图像模型
    price_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- 文本模型：填 `input_price` + `output_price`
- 图像模型：填 `image_price_cents_per_image`
- nullable：迁移期先允许空；admin 站 UI 上对空值给红色警告
- 旧 env 单价（`GAME_INPUT_COST_CENTS_PER_MILLION_TOKENS`）保留为兜底 fallback

### 3.2 创作所有权字段

| 表 | 新增字段 | 含义 |
|---|---|---|
| `world_drafts` | `created_by_user_id` (FK users.id, NOT NULL) | 创作者 |
| `script_drafts` | `created_by_user_id` (FK users.id, NOT NULL) | 创作者 |
| `generation_tasks` | `created_by_user_id` (FK users.id, NOT NULL) | 任务发起人；替代当前埋在 `request_payload.admin_user_id` 的弱字段 |
| `worlds` | `created_by_user_id` (FK users.id, nullable) | 创作者；null = 官方/seed 内容 |
| `scripts` | `created_by_user_id` (FK users.id, nullable) | 同上 |

迁移：现有数据全部用「首个 admin user」填充（或保持 nullable），后续新建的强制 NOT NULL。

### 3.3 状态机正式化

**worlds**（已有 `status` 字段，确认 enum 值）：

```
状态机：
  draft ──发布──→ published
   ↑                 │
   └──── 下架 ───────┘

未来加审核时插入 submitted 状态：
  draft ──提交审核──→ submitted ──admin 通过──→ published
                              ──admin 驳回──→ draft (附驳回原因)
```

`status` enum 值定义：`draft` / `submitted` / `published` / `withdrawn`

`withdrawn` 用于"被 admin 强制下架"，跟用户自己回退的 `draft` 区分（影响是否能再次提交）。

**scripts**：当前是 `is_published: bool`，要改成 `status: str` 跟 worlds 对齐。Migration：`is_published=True` → `status='published'`，否则 `status='draft'`。

### 3.4 创作配额表（新增）

```python
class UserCreationQuota(Base):
    __tablename__ = "user_creation_quotas"

    id: Mapped[str] = ...
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quota_date: Mapped[date] = mapped_column(Date, index=True)
    world_generations: Mapped[int] = mapped_column(Integer, default=0)
    script_generations: Mapped[int] = mapped_column(Integer, default=0)
    # 唯一约束: (user_id, quota_date)
```

用于「每用户每天最多 N 次创作」的限额（防止积分系统未上线前被刷爆）。

### 3.5 Beta 白名单（轻量实现）

`users` 表加 `can_create: bool`，默认 `False`。Admin 手动开权限。

后续接入积分系统后，`can_create` 改为「有积分余额 || can_create=True」的复合判断，平滑过渡。

---

## 4. Backend 改造

### 4.1 创作权限放开

| 路由 | 当前 | 改后 |
|---|---|---|
| `POST /admin/world-generation-tasks` | `get_current_admin_user` | `get_current_user` + `can_create=True` 检查 + 配额检查 |
| `POST /admin/script-generation-tasks` | 同上 | 同上 |
| `GET /admin/generation-tasks/{id}/stream` | admin | 任意 user，但只能看自己的（admin 例外） |
| `GET /admin/world-drafts` | admin（看全部） | user 看自己；加 `?admin=true` admin 看全部 |
| `POST /admin/world-drafts/{id}/publish` | admin 直接 publish | 改名 `/world-drafts/{id}/submit-or-publish`：用户提交后**直接** `status=published`（前期无审核） |

路由层面建议把创作相关的从 `/admin/*` 迁到 `/workshop/*`：

```
POST /workshop/world-generation-tasks
POST /workshop/script-generation-tasks
GET  /workshop/generation-tasks/{id}/stream
GET  /workshop/world-drafts
GET  /workshop/script-drafts
POST /workshop/world-drafts/{id}/publish
POST /workshop/worlds/{id}/withdraw  # 已发布的下架回 draft
DELETE /workshop/world-drafts/{id}    # 用户删自己的草稿
```

`/admin/*` 保留给真正的管理路由（providers / models / slots / audit / 跨用户管理）。

### 4.2 并发与配额

- `MAX_ACTIVE_TASKS_PER_USER = 1`（admin 维持 2，加 `if user.is_admin` 判断）
- 每日配额：默认 `world_generations_per_day = 2`、`script_generations_per_day = 3`，admin 无限制
- 超过 → HTTP 429 + 提示「今日配额已用完」
- 配额配置项放 `settings.py`，便于调整

### 4.3 成本数据沉淀

修改 `services/game_service.py::_consume_turn` 写入 `TokenUsage` 时的 `cost_cents` 计算逻辑：

```python
# 旧：从 settings.game_input_cost_cents_per_million_tokens 读
# 新：先 join provider_models 拿单价，单价 null 时 fallback env
input_price = (
    provider_model.input_price_cents_per_million_tokens
    or settings.game_input_cost_cents_per_million_tokens
)
```

同样改造创作工坊各阶段的 LLM 调用记账。

### 4.4 状态机 endpoints

```
POST /workshop/world-drafts/{id}/publish
  → 校验 ownership → status 'draft' → 'published' → 在 worlds 表创建/更新对应行 → 单事务

POST /workshop/worlds/{id}/withdraw
  → 校验 ownership → worlds.status='published' → 'draft' → 同步把内容回写到 world_drafts (or 软删 worlds 行?)

DELETE /workshop/world-drafts/{id}
  → 校验 ownership → 删 draft 行（如果 worlds 表有对应 published 内容拒绝删除，必须先下架）
```

「下架」的实现选项：

- **方案 A**（推荐）：worlds 表保留行，`status='draft'`，前端 discover 页过滤 `status='published'`；同时写一行回 `world_drafts` 给用户编辑
- **方案 B**：worlds 行删除，把内容回填到 `world_drafts`

推荐 **方案 A**，因为 worlds 上挂着 `play_count` / `created_at` 等数据，删行丢历史。

---

## 5. Frontend（用户站）改造

### 5.1 迁移策略：UI 不动，路径替换 + 隔离数据

**核心原则**：现有 `/admin/page.tsx`（tabs: worlds/scripts/models）+ `/admin/generate/*` + `/admin/worlds/drafts/*` 等 UI 组件**全部直接复用，不做 UX 改造**。Phase 1 只做三件事：

1. 复制 `/admin/*` 的页面到 `/workshop/*`（UI 一字不改）
2. 用户站的 `/workshop` 去掉 `models` tab
3. 后端数据按 user_id 过滤；前端 `adminFetch` 换成 `userFetch`

UX 简化（隐藏档位参数、去掉 retry 按钮等）作为 **Phase 2** 后续 spec，本期不做。

### 5.2 路由映射

| 现有路径（admin 专属）| 新路径（用户）| 说明 |
|---|---|---|
| `/admin`（worlds/scripts/models tabs） | `/workshop`（worlds/scripts tabs，**去掉 models**） | tab UI 复用，过滤数据按 user_id |
| `/admin/generate/world` | `/workshop/generate/world` | 创作向导 + SSE 进度，UI 不变 |
| `/admin/generate/script` | `/workshop/generate/script` | 同上 |
| `/admin/worlds/drafts/[id]` | `/workshop/worlds/drafts/[id]` | 草稿编辑器，UI 不变 |
| `/admin/scripts/drafts/[id]` | `/workshop/scripts/drafts/[id]` | 同上 |

### 5.3 现有 `/admin/*` 保留作 admin 过渡入口

**`/admin/*` 不删**，作为新管理员站（`admin.xxx.com`）建好之前的 admin 临时入口：

- `/admin`（worlds/scripts/models tabs）保留全部功能，**admin 能看到所有用户的数据**
- 普通用户访问 `/admin` 被后端拒（已有 `get_current_admin_user` 鉴权）
- 主站 navbar **不显示 `/admin` 入口**，admin 手动敲 URL 进
- 新管理员站完成后（roadmap #11），整个 `/admin/*` 删除

### 5.4 API helper 与鉴权

- 新增 `frontend/lib/workshop-api.ts`（复制 `admin-api.ts`，去掉 admin 专属头如有）
- 创作工坊 SSE 流复用同一套 helper，文案保留 admin 版本即可（Phase 2 再改用户友好版）

### 5.5 工作量

| 工作 | 估时 |
|---|---|
| 复制 `/admin/page.tsx` 到 `/workshop/page.tsx`，删 models tab | 0.5d |
| 复制 generate / drafts 子路由 | 0.5d |
| `workshop-api.ts` + 数据按 user 过滤 | 0.5d |

合计 **~1.5 天**。比原方案（含 UX 简化）的 3 天显著减少。

---

## 6. 【设计 Brief】管理员站 — 给设计 AI 看的输入

> 本节是写给 Claude design / 其他 AI 设计工具的 brief，让设计 AI 看完能直接出 HTML/Figma。**Skip 本节如果你是开发者**。

### 6.1 这是什么站

InkWild 是一个 AI 互动叙事引擎产品（详见根目录 `CLAUDE.md` 和 `docs/product/product-spec.md`）。

本站是 **InkWild 的内部管理员控制台**（admin console），**不对用户开放**，部署在独立子域名（如 `admin.inkwild.app`），普通用户不知道其存在。

用户：InkWild 团队内部成员，约 1-5 个 admin。日常使用场景是配置 LLM 模型、查看运营数据、管理用户产出的内容。

### 6.2 这个站要解决的事

1. **管 LLM 模型供给**：增删 Provider（DeepSeek / Claude / Gemini 等）、增删每家 Provider 下的具体 Model、配置每个 Model 的单价、把功能槽位（slot）绑定到具体 Model
2. **看运营数据**：单局游戏成本分布、单次创世成本、token 消耗、模型调用明细、用户活跃度等
3. **管用户内容**：跨用户查看世界/剧本/草稿；强制下架违规内容；查看任意用户的游戏 session
4. **管用户**：用户列表、Beta 创作白名单、封禁、调权限
5. **审计**：查看 admin 操作日志

### 6.3 第一批必须有的功能（MVP）

**导航结构建议：**

```
左侧 sidebar：
  ├─ 📊 Dashboard（首页：关键指标 + 最近事件）
  ├─ 🤖 Models（LLM 模型管理）
  │   ├─ Providers 列表
  │   ├─ Models 列表
  │   └─ Slot Bindings 槽位绑定
  ├─ 💰 Cost Analytics（成本分析）
  │   ├─ 近 7/30 天游戏单局平均成本
  │   ├─ 近 7/30 天创世单次平均成本
  │   └─ 按 Provider/Model 拆分的消耗
  └─ 📋 Audit Log（操作日志）
```

**详细功能：**

#### A. Models 模块

**A1. Providers 列表页**
- 表格：名称、类型（deepseek/claude/...）、状态（active/disabled）、最近健康检查时间、操作
- 新建 Provider：名称、类型、base_url、api_key_env_name、备注
- 编辑/禁用/删除（删除需二次确认）

**A2. Models 列表页**
- 按 Provider 分组的表格
- 字段：display_name、model_id、kind（text/image/embedding）、`input_price_cents_per_million_tokens`、`output_price_cents_per_million_tokens`、`image_price_cents_per_image`、最后更新时间、状态
- **单价未填的行**要明显红色高亮（影响成本统计）
- 新建/编辑 Model：含单价编辑器，单价以"分/百万 token"为单位，UI 上同时显示美元换算预览
- 单价更新时自动写入 `price_updated_at`

**A3. Slot Bindings 页**
- 列表：slot 名称、当前绑定 Model、状态、最后验证时间、操作
- 已知 slot 列表（写死在前端）：`narrator`, `director`, `npc`, `moderation_slot`, `world_creator`, `world_creator_planner`, `world_creator_critic`, `research_summarizer`, `compressor`, `image_generator` 等
- 改绑：弹窗选择「Provider + Model」
- "验证"按钮：触发后端 capability probe（已有）

#### B. Cost Analytics 模块

**B1. 总览页**
- 大数字 KPI：今日 LLM 消耗（¥）、近 7 天累计、近 30 天累计
- 图表 1：近 30 天每日消耗柱状图
- 图表 2：按 Provider 饼图
- 图表 3：按 slot 饼图（哪个功能花得最多）

**B2. 游戏成本明细**
- 表格：单局成本分布、平均值、p50/p90/p99
- 按世界/剧本拆分
- 异常单局（>¥10）列表

**B3. 创世成本明细**
- 单次创世任务平均消耗
- 按"世界生成 vs 剧本生成"拆分
- 异常任务列表

#### C. Audit Log 模块

- 现有 `admin_audit_logs` 表的查询界面
- 字段：时间、admin 用户、操作类型、目标、详情
- 筛选：时间范围、操作类型、admin 用户
- 一行一条，点击展开看完整 payload

#### D. Dashboard

- 顶部 KPI 卡片：今日消耗 / 在线 session 数 / 待审核内容数（先 placeholder）/ 异常告警数
- 最近事件 feed：最新的 audit log、最新的高成本 session、最新的失败任务

### 6.4 未来要加但本期不做（设计上需要预留扩展位）

- **Users 模块**（用户管理、Beta 白名单、封禁、权限）
- **Content 模块**（跨用户查/管所有 worlds / scripts / drafts，强制下架）
- **Sessions 模块**（看任意用户的游戏 session，调试用）
- **Audit Queue**（用户提交的创作待审核队列）
- **Tier Config**（模型档位配置）
- **Credit System**（积分定价配置、用户钱包、流水）

**设计上要求：** sidebar 留 6+ 个待加项的位置，整体导航结构能容纳 10+ 个一级模块。

### 6.5 风格 / 视觉要求

- **不是给用户的**：可以工具感强、信息密度高、不需要营销腔
- **数据为中心**：表格、图表是主要元素，不要花哨
- **要清爽**：当前 `/admin/*` 风格"一般"，希望明显更精致——但不要走极简，要"专业控制台"的感觉
- **响应式**：桌面优先（admin 都在电脑用），平板能看就行，不需要手机适配
- **参考产品**：Vercel Dashboard、Linear Admin、Stripe Dashboard、PostHog 这种产品级别

### 6.6 技术约束

- Next.js 16 + React 19 + TypeScript（跟主站一致，方便复用类型）
- Tailwind CSS v4
- 可选引入 shadcn/ui（之前已批准，见 `docs/plans/frontend-refactor-2026-05.md`）
- 数据获取：TanStack Query（v2.2 已批准）
- 图表：Recharts 或 Tremor（待选）
- 表单：React Hook Form + Zod
- **共享主站 cookie**：登录走 `xxx.com` 主站登录页（admin 站不实现独立登录，进入时若未登录 redirect 到主站 login，登录后回跳）

---

## 7. 实施路线图

按依赖关系排序，**前 3 步是上线前本来就要做的，立刻执行；后续步骤等数据**：

| # | 任务 | 工作量 | 依赖 | 状态 |
|---|---|---|---|---|
| 1 | provider_models 加单价字段 + admin UI 改造（**现有 admin 站先做，新管理站后接**） | 0.5d | 无 | 待做 |
| 2 | token_usage 写入改读 provider_models 单价 | 0.5d | #1 | 待做 |
| 3 | 现有 admin 站加 Cost Analytics 临时页（让数据沉淀） | 0.5d | #2 | 待做 |
| 4 | 草稿/发布状态机改造（worlds.status enum 正式化 + scripts.is_published 迁移到 status） | 1d | 无 | 待做 |
| 5 | 创作所有权字段迁移（drafts/tasks/worlds/scripts 加 created_by_user_id） | 1d | 无 | 待做 |
| 6 | 创作配额表 + Beta 白名单字段 | 0.5d | #5 | 待做 |
| 7 | Backend `/workshop/*` 路由新增 + admin 路由权限改造 | 2d | #4-6 | 待做 |
| 8 | 前端 `/workshop/*` 路由实现（UI 复用 + 去 models tab + 数据按 user 过滤）；**`/admin/*` 保留作 admin 过渡入口** | 1.5d | #7 | 待做 |
| 9 | 新管理员站脚手架（独立 Next.js 项目 + cookie 跨子域 + auth redirect） | 1d | 无 | 待做 |
| 10 | Claude design 出 HTML → 落地新管理员站 UI | 待估 | #9 + 设计输出 | 待做 |
| 11 | 把主站 `/admin/*` 的全部功能（Models 配置 + 跨用户管理）迁到新管理员站，然后**整个删除主站 `/admin/*`** | 1d | #10 | 待做 |
| 12 | ⏸️ 跑 2-4 周数据 | - | #2 之后 | hang |
| 13 | 积分系统 / Tier 抽象 / 审核工作流 | - | #12 之后 | hang，单独立 spec |

**两条并行轨：**

- **轨 A（成本数据轨）**：#1 → #2 → #3 → 跑数据 → 后续设计积分系统
- **轨 B（创作开放轨）**：#4 → #5 → #6 → #7 → #8（用户能创作）
- **轨 C（管理站轨）**：#9 → 用户出 HTML → #10 → #11

#1-3 优先级最高，可以立即开始。#4-8 可以跟 #1-3 并行。#9-11 等设计输出再上。

---

## 8. 风险与开放问题

### 风险

1. **Cookie 跨子域配置错** → admin 站登录态丢失。需要充分测试 `cookie domain=.xxx.com`、`SameSite=Lax`、HTTPS 配置
2. **用户创世质量良莠不齐** → discover 页被低质内容刷屏。前期 Beta 白名单卡死，等审核 ready 再放开
3. **配额 race condition** → 用户狂点同时发起多个生成任务，配额检查有 race。需要 advisory lock（参考现有 `MAX_ACTIVE_TASKS_PER_ADMIN` 的实现）
4. **单价填错导致成本统计跑偏** → admin 改单价时强制要求填写原因 + 记 audit log
5. **现有 admin 用户的 user_id 反查** → admin 也是 user，但当前 `is_admin=True` 的用户怎么映射？需要确认 admin user 在 users 表里都有对应 row

### 开放问题（写代码前要定）

- **Q1**：用户删除自己的草稿，是软删还是硬删？建议软删（加 `deleted_at`）以便审计回溯，但 90 天后清理
- **Q2**：用户发布的世界被其他用户玩出 case_board 历史/session 数据，作者下架/删除时这些数据怎么处理？建议：下架不删 session，删除 worlds 行会级联（暂不允许真删 worlds，只能下架）
- **Q3**：admin 站 sidebar 默认折叠还是展开？建议展开（admin 都在桌面用，屏幕够大）
- **Q4**：成本统计的「美元换算预览」用静态汇率还是实时？建议静态（admin 后台改），实时引入外部 API 不值
- **Q5**：现有 `world_drafts.world_id` 字段（已有的 unique 外键）跟新加的 `created_by_user_id` 怎么协调？现有逻辑是 publish 时 draft.world_id 指向 worlds 行；新方案下需要把这套保留

---

## 9. 验收标准

完成本 spec 描述的工作后，下列条件全部成立：

- [ ] 任意已通过 Beta 白名单的普通用户能登录主站、进入 `/workshop`、生成世界/剧本、发布
- [ ] 发布的世界出现在 discover 页，可被其他用户游玩
- [ ] 用户能下架自己的世界（回到草稿态），能再次编辑后重新发布
- [ ] `admin.xxx.com` 独立可访问，普通用户被拒绝进入
- [ ] 管理员能在管理站配置 Provider/Model/Slot，包含单价
- [ ] `token_usage.cost_cents` 字段在新数据上非零
- [ ] Cost Analytics 页能看到游戏单局/创世单次的真实平均成本
- [ ] Phase 1：主站 navbar 不显示 `/admin/*` 入口；`/admin/*` 路由本身保留作为 admin 临时入口
- [ ] Phase 2（#11 完成后）：主站 `/admin/*` 整个删除
- [ ] 现有 admin 操作日志保留可查

---

## 10. 后续 spec 预告

本 spec 不包含但 hang 在后续：

- `2026-XX-XX-credit-system-design.md` — 积分系统（充值、消费、明细、定价、免费额度）
- `2026-XX-XX-model-tier-design.md` — Tier 抽象（用户选档位）
- `2026-XX-XX-content-moderation-workflow-design.md` — UGC 审核工作流（机审 + 人审 + Audit Queue UI）
