# InkWild

AI 驱动的互动叙事引擎。剧本模式（预设谜题/真相/结局）+ 自由模式（纯开放世界），共享同一套世界引擎。

当前已上线：双模式游玩、多 Agent 编排、创作工坊（AI 生成世界 + 剧本，含联网检索、AI 配图、草稿/发布流程）、多 LLM Provider 管理后台。

**已正式上线**（2026-06-06）：主站 https://inkwild.app · 后台 https://admin.inkwild.app。生产运维 runbook 见 [`docs/operations/deploy-and-config.md` §0](docs/operations/deploy-and-config.md)（改代码/改密钥/改数据三类流程 + 服务器拓扑）。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, asyncpg, Redis, structlog, sse-starlette |
| 前端 | Next.js 16, React 19, TypeScript, Zustand, Tailwind CSS v4 |
| 数据库 | PostgreSQL 16 + Redis 7 |
| LLM | 文本：DeepSeek / Claude / Gemini / Grok / OpenAI 兼容（通过 Provider + Slot 后台动态绑定，见 `services/model_management.py`）；图像：Seedream；联网检索：Tavily |
| 部署 | Docker Compose |

## 项目结构

```
backend/
  api/          auth, game, worlds, workshop（创作工坊）,
                admin / admin_analytics / admin_audit / admin_dashboard / admin_models / admin_users 路由
  engine/       orchestrator → director/npc/narrator agents、world_simulator、world_clock、
                narrative_arc、intent_system、info_propagation、memory_manager、state_manager、
                event/ending、content_filter/moderation、compressor、case_board
  llm/          provider 抽象层 (base, deepseek, claude, gemini, grok, openai_compatible, seedream, router)
  models/       SQLAlchemy 模型 (user, game, world, script, draft, memory, generation_task, model_management)
  schemas/      Pydantic 请求/响应
  services/     game / auth / session_lock /
                world_creator_agent、generation_task_service、generation_strategy_service、
                generation_prompt_builder、generation_feedback、
                model_management、image_storage、research_broker、tavily_search
  seeds/        世界种子数据（JSON，目前主要是 wuyinzhen；其余世界由创作工坊产出后落库）
  migrations/   Alembic 迁移
  tests/        pytest 异步测试

frontend/                          主站（用户端，端口 3000）
  app/          页面路由: landing (/), discover, worlds/[id], play/[id], history, login,
                workshop（创作工坊：workshop/generate/{world,script}、workshop/worlds、workshop/scripts），
                dev/* (设计走查 sandbox: type、theme-sandbox、play-redesign-preview 等)
  components/   UI 组件：ProductNav、BottomTabBar、QueryProvider、ConfirmDialog、
                admin/ (workshop 子组件 + GenerationLoadingScreen)、case-hologram、ending、play 系列、ui/* 原子组件
  stores/       Zustand: auth.ts, game.ts
  lib/          API 封装、SSE 解析 (sse.ts / admin-sse-events.ts 给 workshop 用)、
                motion.ts (Framer 预设)、query-client、类型定义、若干 *.test.ts (vitest)
  i18n/         next-intl 文案：zh.json / en.json
  app/sw.ts     serwist PWA service worker 源

admin-frontend/                    管理后台（独立 Next 项目，端口 3001，不复用主站视觉系统）
  设计基线：InkWild Admin.html 原型 + docs/plans/admin-console-2026-05.md
```

## 常用命令

```bash
# 后端
cd backend && pip install -e ".[dev]"
cd backend && uvicorn main:app --reload --port 8000
cd backend && python -m pytest tests/ -v
cd backend && alembic upgrade head
cd backend && python -m seeds.seed

# 前端
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run build

# 基础设施
docker compose up -d db redis
```

## 核心数据模型

| 表 | 说明 |
|---|------|
| users / auth_identities / web_sessions | 用户体系，session cookie 认证，多登录方式映射 |
| worlds | 世界 = 舞台（base_setting, free_setting，封面图字段） |
| scripts | 剧本 = 剧情线，绑定世界（events_data, endings_data） |
| npcs / events / characters / endings | 世界内容实体 |
| world_drafts / script_drafts | 创作工坊草稿，发布后落到 worlds / scripts |
| generation_tasks / generation_task_events | 创作工坊 AI 生成任务 + SSE 事件流 |
| model_providers / provider_models / model_slot_bindings | LLM provider / 模型 / 槽位（动态绑定，admin 后台管） |
| game_sessions | 游戏会话（user_id, world_id, script_id, mode=script/free, game_state） |
| messages / memory_entries | 对话记录 + 结构化记忆 |
| case_board_history | 案件板增量操作历史，current 快照在 `game_state.case_board` |
| admin_audit_logs | Admin 写操作审计日志 |
| token_usage | LLM token / cost 记录，供单局成本 guardrail 使用 |

## 开发原则

### 总体

- **注重开发效率，注重用户体验。** 功能做出来、体验做到位是第一优先级。
- **生产变更必须走标准链路。** InkWild 项目以后所有代码 / schema / 配置类变更都先在本地仓库修改并验证，再提交并上传 GitHub，最后由服务器拉取/部署；不要直接把线上手改当成最终状态。紧急线上止血可以先做，但必须立即补回本地代码、提交和部署链路。
- **生产操作必须先获明确同意。** 对生产服务器执行 `git pull`、镜像重建、容器重建或服务重启前，必须先得到用户在当前对话中的明确授权；“修复”“解决”“排查”等请求本身不等于授权部署或重启。未经授权只允许完成本地修改与验证。
- **轻量测试。** 核心逻辑和关键路径写测试，不追求覆盖率，不为边角 case 补大量测试。新功能优先跑通再补测试。
- **遵循现有技术栈。** 前后端技术选型已经稳定，不是不能改，但不能随意引入新框架/新库。要引入时先说明理由。前端已就位的基础设施：TanStack Query、React Hook Form + Zod、Framer Motion (`motion/react`)、next-intl、Radix Dialog/Popover/Toast、vaul (Drawer)、cmdk (Command Menu)、serwist (PWA)、Sentry (`@sentry/nextjs`)、vitest 单测。
- **文档与代码冲突时以代码为准。** 旧 spec/plan 中的描述可能已过时，以当前实现和最新 spec 为准。

### 后端

- 全链路 async，不允许同步阻塞
- 类型标注必写，用 `str | None` 不用 `Optional[str]`
- 请求/响应 schema 放 `schemas/`，统一 `{"code": 0, "data": ..., "message": "ok"}` 包裹
- 认证用 `dependencies.py` 的 `get_current_user`，已废弃的 `X-Player-Id` 不要用
- Admin 认证用 `get_current_admin_user`，写操作调用 `record_admin_action`；不要重新引入 `X-Admin-Key`
- 游戏流式接口用 SSE（`sse-starlette`）
- SSE payload 必须带 `version: 1`；内部 `state_ready` 事件不能发给前端
- 修改 session 状态的接口（action/resume/retry）必须加 `SessionLock`
- 日志用 `structlog`，禁止 `print()`
- 世界/剧本内容放 seeds 或数据库，不硬编码在 Python 中
- LLM 调用走 `LLMRouter` + 模型后台的 slot 绑定，不要在业务代码里硬编码 provider/model 名
- Sentry 后端用 `BACKEND_SENTRY_DSN` / `SENTRY_DSN`，前端用 `NEXT_PUBLIC_SENTRY_DSN`
- 创作工坊任务流是 SSE，事件 schema 见 `frontend/lib/admin-sse-events.ts`，前后端要同步改

### 前端

**当前状态 v2.3 cinematic gold 已落地**（2026-05-23）：主入口页面 landing / discover / history / workshop / login / worlds[id] / play[id] 全部按 v2.3 上线。
重构日志归档在 [`docs/_archive/frontend-refactor-2026-05.md`](docs/_archive/frontend-refactor-2026-05.md)。

**前端唯一参考文档是 [`frontend/AGENTS.md`](frontend/AGENTS.md)**（参考，不是律法；原 `docs/design/` 的 visual-principles / frontend-spec / play-mode-spec / audit 几份规范已合并精简进它并归档）。改前端先读那一份。

视觉与令牌（详见 `frontend/AGENTS.md`）：
- **真相源是代码**：设计令牌在 `frontend/app/globals.css` 的 `.lv-theme` 块（`--lv-*` 唯一定义，禁止 per-page override）；字号实物看 `/dev/type`；组件写法看现成组件。文档与代码冲突以代码为准
- 主色 `--lv-accent: #dfc290` 香槟金；底色 `--lv-bg: #08080a`；主文本 `--lv-ink: #f5f2eb` 暖象牙；字号用 `.lv-t-*` 工具类
- 导航：桌面 `<ProductNav variant="transparent|solid" active="..." />`，移动 `<BottomTabBar />`（layout.tsx 挂载）；全局 Navbar 已移除
- **唯一会卡 CI 的硬规则**：禁引用旧 token `--color-accent` / `--font-size-*` / `--ta-*`，统一 `var(--lv-*)`（见 `frontend/eslint.config.mjs`）。其余全是约定，由 PR 走查 + 设计师眼睛把关
- PR 自检表见 `.github/pull_request_template.md`，前端 PR 必填

基础设施层（已就位，新页面必须用）：
- **TanStack Query** (`@tanstack/react-query`)：数据获取（替掉 `useEffect + apiFetch + active flag` 模板）；Provider 见 `components/QueryProvider.tsx`
- **React Hook Form + Zod + `@hookform/resolvers`**：表单 + schema 校验
- **Framer Motion** (`motion/react`)：动效；统一预设见 `frontend/lib/motion.ts`（`lvStaggerContainer` / `lvStaggerItem` / `lvFadeUp` 等）
- **next-intl**：i18n，挂载在 `app/layout.tsx`；文案 `t('xxx')`，文件 `i18n/zh.json` + `i18n/en.json`
- **Radix + vaul + cmdk**：复杂交互组件（Dialog/Popover/Toast/Drawer/Command Menu）—— 不引入 shadcn 整套，simple 组件继续手写
- **serwist** (`@serwist/next`)：PWA service worker（源 `app/sw.ts`，配 `manifest.webmanifest`）
- **Sentry** (`@sentry/nextjs`)：前端错误上报，DSN 用 `NEXT_PUBLIC_SENTRY_DSN`
- **vitest**：lib 层单元测试；`npm run test`

工程约定：
- 谨慎 `"use client"`，只在需要交互或浏览器 API 时使用
- 客户端状态管理用 Zustand，不引入 React Context；服务端状态用 TanStack Query
- 流式处理走 `fetch + ReadableStream`，不用 `EventSource`（cookie 认证约束）
- 只用 Tailwind CSS，不引入 CSS Modules / styled-components
- **真正移动端优先**：先 375px 设计，桌面是放大版；用 `100dvh` + `safe-area-inset`，触摸目标 ≥ 44px
- 认证拦截用现有 auth store + redirect helper
- 遵循 `frontend/AGENTS.md` 中的 Next.js 版本注意事项

### API 与数据边界

- 改接口前同时检查后端路由和前端消费方（`frontend/lib/` + `frontend/stores/`）
- Script 是独立数据实体（`scripts` 表），不只是 world 上的字段
- Admin 内容流程保留草稿 → 发布生命周期
- 认证、游戏 session 所有权、admin 授权三条边界必须显式清晰

## 禁止事项

- 不要重新引入匿名 `player_id` / `X-Player-Id`
- 不要重新引入 `X-Admin-Key` 或绕过 admin cookie 权限
- 不要引入 LangChain 或第二套编排框架
- 不要绕过 auth / ownership / admin 检查
- 不要在没有 spec 或 plan 的情况下擅自扩大产品面

## 参考文档

按需阅读，不要全部读完再开始工作。技术文档统一以**能力矩阵**风格组织——读哪一篇就先扫矩阵，关注 ✅/🟡/🔵/❌ 状态符号定位 gap，再深入实现要点。

### 入口

| 场景 | 文档 |
|------|------|
| **顶层架构 + 系统级能力清单**（必读，新人入项第一份）| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 模块文档索引 | [`docs/modules/README.md`](docs/modules/README.md) |
| 模块文档模板（写新文档遵循） | [`docs/modules/_template.md`](docs/modules/_template.md) |
| Breaking change 备查 | [`docs/MIGRATION_NOTES.md`](docs/MIGRATION_NOTES.md) |

### 引擎核心模块

| 子系统 | 文档 |
|------|------|
| 主流水线 / 早流式 / 三幕检测 | `docs/modules/orchestrator.md` |
| Director Agent + DIRECTOR_TOOL schema | `docs/modules/director.md` |
| NPC Agent + 群像 + 信息隔离（样板） | `docs/modules/npc.md` |
| Narrator Agent + 早流式 prelude | `docs/modules/narrator.md` |
| 记忆系统（隔离/语义召回/反思/info_propagation） | `docs/modules/memory.md` |
| 案件板（ops 序列 + history） | `docs/modules/case-board.md` |
| Intent system（NPC 内驱目标） | `docs/modules/intent-system.md` |
| World simulator（时钟/事件/环境） | `docs/modules/world-simulator.md` |
| GameState + 乐观锁 + SessionLock | `docs/modules/state-and-persistence.md` |

### 横切关注

| 子系统 | 文档 |
|------|------|
| LLM router（provider 抽象 / slot 绑定 / timeout） | `docs/modules/llm-router.md` |
| SSE 协议（事件清单 / 错误码 / 心跳） | `docs/modules/sse-protocol.md` |
| 成本 / 限流 / 内容审核 | `docs/modules/cost-rate-moderation.md` |
| 用户 / Admin / Audit | `docs/modules/auth-and-admin.md` |

### 创作工坊

| 子系统 | 文档 |
|------|------|
| 创作工坊（五层模型 / SSE 任务流 / 草稿发布） | `docs/modules/world-creator.md` |

### 数据 / 运维 / 设计 / 产品

| 类别 | 文档 |
|------|------|
| 数据库 schema（所有表 + Alembic 演进） | `docs/data/schema.md` |
| 部署 + env 配置 | `docs/operations/deploy-and-config.md` |
| 可观测 + 备份 | `docs/operations/observability-backup.md` |
| 延迟 / TTFT 优化（缓存进展 + decode 地板 + 杠杆清单） | `docs/operations/latency-ttft.md` |
| **前端说明（视觉/令牌/play/基础设施，唯一参考，必读）** | `frontend/AGENTS.md` |
| 封面图规范 v1.1（AI 生图产物，属创作工坊） | `docs/design/cover-art-spec.md` |
| 旧前端规范（已合并进 AGENTS.md，备查） | `docs/_archive/`（visual-principles / frontend-spec / play-mode-spec / audit-2026-05） |
| Admin 控制台计划 | `docs/plans/admin-console-2026-05.md` |
| 产品方向 | `docs/product/product-spec.md` |

### 已归档（备查，不再维护）

- `docs/_archive/decisions-2026-04-30.md` —— Phase 0/1/2/3 演进 + 范围调整决策日志（"为什么砍 X / 为什么没做 Y" 来这里查）
- `docs/_archive/frontend-refactor-2026-05.md` —— 前端重构计划（v2.2 → v2.3 cinematic gold，2026-05 全程），主体已完成，保留决策追溯

其他被新文档替代的旧内容已删除，详见 `docs/_archive/README.md`。
