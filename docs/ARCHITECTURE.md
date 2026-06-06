# InkWild 架构总览

> 状态截至 2026-05-08。本文是系统的**顶层导航**——读完后应该知道整个系统能做什么、哪些 gap、每个子系统的边界、数据怎么流。然后跳到 `modules/<name>.md` 看具体能力清单。
>
> 文档与代码冲突时以代码为准。每篇模块文档顶部都标了"状态截至"日期；过期的内容**不要**当成"现在仍然如此"来读，去对应文件 grep 一下。

## 1. 系统是什么

AI 驱动的互动叙事引擎。玩家用自然语言行动，**多 Agent 编排**（Director / NPC / Narrator）演绎出一段段戏剧化场景。两种玩法模式：

- **剧本模式**：预设谜题/真相/结局，玩家在世界里探案
- **自由模式**：纯开放世界，无硬结局条件

两种模式共享同一套世界引擎，差异只在初始化和结局判定。

附带：**创作工坊**（admin 端 AI 生成世界 + 剧本）、**多 LLM Provider 管理后台**（slot/provider/model 三层动态绑定）。

## 2. 系统级能力清单

把整个系统的能力按子域铺开。一眼能看到：现在能做什么、哪些挂着、哪些可以补。模块级细矩阵在各 `modules/<name>.md`。

状态符号：✅ 已落地 / 🟡 部分落地 / 🔵 设计未做 / ❌ 未实现待评估。

### A. 用户与权限

| 能力 | 状态 | 模块 |
|---|---|---|
| 邮箱密码注册/登录 | ✅ | auth-and-admin |
| 多登录方式映射（auth_identities） | ✅ | auth-and-admin |
| 浏览器 cookie 长 session（90 天） | ✅ | auth-and-admin |
| OAuth / 第三方登录 | ❌ | — |
| 找回密码 / 重置密码 | ❌ | — |
| 邮箱验证 | ❌ | — |
| Admin 角色（is_admin 布尔） | ✅ | auth-and-admin |
| Admin 动态权限（role/permission 分离） | ❌ | 已砍（一人 admin 不需要） |
| Admin 写操作审计（admin_audit_logs） | ✅ | auth-and-admin |
| 首位 admin CLI 引导 | ✅ | `cli/create_admin.py` |
| 用户限流（30 actions/min/user） | ✅ | cost-rate-moderation |
| Dev 自动登录（DEV_AUTH） | ✅ | `api/auth.py:dev_router` |

### B. 游戏游玩 — 主流程

| 能力 | 状态 | 模块 |
|---|---|---|
| 开新局（剧本模式） | ✅ | orchestrator / game-service |
| 开新局（自由模式，无 hard ending） | ✅ | orchestrator |
| 单 session 行动循环 | ✅ | orchestrator |
| 行动重试（last_action_text 重放） | ✅ | game-service |
| 暂停 / 恢复（resume） | ✅ | game-service |
| 历史会话浏览 | ✅ | `api/worlds.py` + `app/history` |
| 单 session 跨设备恢复 | 🟡 | resume 可用，未做 SSE auto-reconnect |
| 暂停后跨小时回来续 | 🟡 | 同上 |
| 多人同局 | ❌ | 一对一玩法，schema 不支持 |
| 玩家可分支 / 存档点 | ❌ | 单线性 session |

### C. 多 Agent 编排（核心创新）

| 能力 | 状态 | 模块 |
|---|---|---|
| Director 决策（涉及 NPC / 场景 / 状态更新） | ✅ | director |
| Director native JSON mode | ✅ | director |
| Director recall_memory 工具（关键词调早期记忆） | ✅ | director |
| Director inform_npc 工具（显式植入 NPC 私有记忆） | ✅ | director |
| Director player_action 结构化（玩家行动分类） | ✅ | director |
| Director parse 失败 1 次 agent 重试 | ✅ | director |
| Director × NPC 并行 speculative | 🔵 | 已被 NPC-1 顺序对话替代 |
| NPC 顺序对话（NPC-1） | ✅ | npc |
| NPC 持久关系（NPC-2，静态） | ✅ | npc |
| NPC 后台模拟（NPC-3，玩家不在场时跑） | ❌ | spec 已成 |
| Director 关系编辑（NPC-4） | ❌ | spec 已成 |
| NPC 长期反思（reflection） | ✅ | memory |
| NPC 语气锚点（voice anchor，最近 3 句） | ✅ | npc |
| NPC 廉价 slot（独立模型档） | ✅ | llm-router |
| NPC 信号量并发上限（默认 6） | ✅ | orchestrator |
| 单 NPC 失败不崩 turn（fallback 空 dialogue） | ✅ | orchestrator |
| Narrator 早流式（跟 NPC 并行，TTFB ↓） | ✅ | narrator |
| Narrator 织合 Director scene_direction + NPC dialogues | ✅ | narrator |
| NPC 主动行动（脱离 Director instruction） | ❌ | 产品决策待定 |

### D. 世界引擎（状态 / 时间 / 事件）

| 能力 | 状态 | 模块 |
|---|---|---|
| GameState（位置/线索/关系/库存等结构化状态） | ✅ | state-and-persistence |
| 时间推进（5 时段 × N 天） | ✅ | world-simulator |
| NPC schedule（按时段定位地点） | ✅ | world-simulator |
| World events 触发与 effects 应用 | ✅ | world-simulator |
| 环境变化（environment_changes） | ✅ | world-simulator |
| 信息传播（info_propagation 给相关 NPC 写记忆） | ✅ | memory |
| Intent system（NPC 内驱目标 + urgency） | ✅ | intent-system |
| Intent → action effect 链（urgency≥8 真落地） | ✅ | intent-system |
| 三幕检测（intro/middle/climax） | ✅ | orchestrator (narrative_arc) |
| Story beat sheet（张力图） | ❌ | Phase 3 |
| 案件板 ops（typed enum：ADD_CLUE / ADD_SUSPECT 等） | ✅ | case-board |
| 案件板严格 clue_id 锚点 | ✅ | case-board |
| 案件板 history append-only | ✅ | case-board |
| 玩家行动结构化追踪（player_actions 历史） | ✅ | director / state-and-persistence |
| 关键决定追踪（key_decisions） | 🟡 | ArcData 字段在，未自动填 |
| World data 进程内缓存 | ❌ | 100 用户内不需要 |

### E. 记忆系统

| 能力 | 状态 | 模块 |
|---|---|---|
| memory_entries 全局表 | ✅ | memory |
| 按 NPC 隔离（related_npc 锚点） | ✅ | memory |
| 信息传播 last-mile 写各 NPC 记忆 | ✅ | memory |
| 双视角记忆写入（NPC↔玩家互动） | ✅ | memory |
| 关键词搜索 | ✅ | `memory_manager.search_messages` |
| 语义召回（embedding + cosine 重排） | ✅ | memory |
| Batch query NPC memories（修 N+1） | ✅ | memory |
| Embedding 异步写入（不阻塞） | ❌ | P2 加固 |
| NPC 长期反思 summary | ✅ | memory |
| 上下文压缩（≥20 轮触发） | ✅ | compressor |
| 压缩失败重试 + structured metric | ✅ | compressor |
| 压缩 v2（token-based + 结构化）| 🔵 | 等观察数据 |

### F. LLM 编排基础

| 能力 | 状态 | 模块 |
|---|---|---|
| Provider 抽象（DeepSeek/Claude/Gemini/Grok/OpenAI 兼容） | ✅ | llm-router |
| Image provider（Seedream） | ✅ | llm-router |
| Web search provider（Tavily / Grok） | ✅ | world-creator |
| Slot/Provider/Model 三层动态绑定 | ✅ | llm-router |
| Admin 后台 slot 管理 UI | ✅ | `app/admin` |
| Cache-friendly prompt（稳定前缀 + prefix_hash 日志） | ✅ | llm-router |
| Anthropic cache_control 显式标记 | ❌ | 切 Claude 主力时再做 |
| First-token timeout（默认 60s） | ✅ | llm-router |
| 1 retry on transient（5xx / timeout / connection） | ✅ | llm-router |
| Provider auto-downgrade（健康检查） | ❌ | 已砍 |
| Active session model swap notice | ❌ | 已砍 |
| Token usage 记录（model/provider/in/out） | ✅ | llm-router / data-schema |
| 单局成本上限（¥5 warn / ¥6 cap） | ✅ | cost-rate-moderation |
| Cost-per-million 配置（默认 0） | ✅ | `.env` |

### G. SSE / 网络协议

| 能力 | 状态 | 模块 |
|---|---|---|
| SSE 流式输出（narrative tokens） | ✅ | sse-protocol |
| SSE schema 版本号（version: 1） | ✅ | sse-protocol |
| SSE 心跳（30s `: ping`） | ✅ | sse-protocol |
| 90s connection_lost 看门狗 | ✅ | `frontend/lib/sse.ts` |
| 错误码分类（rate_limit/cost_cap/llm_timeout/...） | ✅ | sse-protocol |
| 自动重连 + `/resume` 拉缺失事件 | ❌ | 等真痛点出现再做 |
| State commit 先于 narrative tokens（state_ready 内部事件） | ✅ | orchestrator |
| 阶段进度（processing 事件 + phase 字段） | ✅ | sse-protocol |
| Stage timing 结构化日志 | ✅ | observability-backup |

### H. 内容安全

| 能力 | 状态 | 模块 |
|---|---|---|
| Prompt injection 防护（`<player_input>` 包裹 + 转义） | ✅ | input-sanitizer |
| 输入长度限制（max 2000 字） | ✅ | `schemas/game.py` |
| 控制字符剥除 | ✅ | 同上 |
| LLM 内容审核（5 分类：暴力/性/仇恨/自伤/违法） | ✅ | cost-rate-moderation |
| 审核失败本地 fallback（关键词） | ✅ | 同上 |
| 输入审核 + 输出审核双向 | ✅ | 同上 |
| 审核 strictness 可调 | 🟡 | 配置项有，没 UI |

### I. 创作工坊（admin）

| 能力 | 状态 | 模块 |
|---|---|---|
| AI 生成世界（多步 SSE 任务） | ✅ | world-creator |
| AI 生成剧本 | ✅ | world-creator |
| 联网检索（Tavily） | ✅ | world-creator |
| 联网检索 fallback 链（Grok） | ❌ | 已砍 |
| AI 配图（Seedream） | ✅ | world-creator |
| 图片生成 retry（2 次 + placeholder） | ✅ | world-creator |
| 草稿管理（world_drafts / script_drafts） | ✅ | world-creator |
| 草稿 → 发布原子事务 | ✅ | world-creator |
| 单 admin 并发限制（2 active 任务，advisory lock） | ✅ | world-creator |
| SSE 客户端 30min 超时 + abort | ✅ | `lib/admin-api.ts` |
| Generation event 写入事务（last_event_seq 严格单调） | ✅ | world-creator |
| 反馈 / 修改/再生成已发布世界 | 🟡 | 草稿流程支持，UX 还粗糙 |
| Critic gate v2 | ❌ | Phase 3，等 V1 跑数据 |

### J. 数据持久化

| 能力 | 状态 | 模块 |
|---|---|---|
| Postgres 16 + asyncpg + SQLAlchemy 2 async | ✅ | — |
| Alembic 单 head 迁移 | ✅ | `migrations/` |
| 关键迁移 verify 脚本 | ✅ | 同上 |
| game_sessions 乐观锁（version 列） | ✅ | state-and-persistence |
| Redis SessionLock（单 session 串行） | ✅ | state-and-persistence |
| 索引：`idx_game_sessions_world_id` / `idx_messages_session_role` | ✅ | data-schema |
| Daily pg_dump + 7 天滚动备份 | ✅ | observability-backup |
| Token usage 滚动累加（按 session） | ✅ | data-schema |

### K. 可观测 / 运维

| 能力 | 状态 | 模块 |
|---|---|---|
| Sentry 后端集成 | ✅ | observability-backup |
| Sentry 前端集成 | ✅ | observability-backup |
| 真实 Sentry DSN smoke 测试 | 🟡 | 代码就绪，等 DSN 验证 |
| `/health` 真实检查 DB + Redis | ✅ | `main.py` |
| DB 连接池配置可调 | ✅ | `database.py` |
| 日志脱敏（email/api_key/password/cookie） | ✅ | `middleware/logging.py` |
| Stage timing 结构化埋点 | ✅ | orchestrator |
| Compressor metric（trigger/tokens/duration/outcome） | ✅ | compressor |
| LLM retry / timeout 日志 | ✅ | llm-router |
| Runbook（DB down / LLM 不可用 / 成本失控） | ❌ | 已砍 |
| GitHub Actions CI | ❌ | 已砍（一人开发） |
| Coverage uplift（≥60%） | ❌ | 已砍 |

## 3. 服务编排（docker-compose）

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  frontend   │────▶│   backend    │────▶│  Postgres 16 │
│ Next.js 16  │     │  FastAPI     │     │  (asyncpg)   │
│ React 19    │ SSE │  Python 3.12 │     └──────────────┘
└─────────────┘     │              │     ┌──────────────┐
                    │              │────▶│   Redis 7    │
                    └──────┬───────┘     │ (lock+rate)  │
                           │             └──────────────┘
                           ▼
                  ┌─────────────────┐
                  │  LLM providers  │  DeepSeek / Claude /
                  │  (via Router)   │  Gemini / Grok / OpenAI 兼容
                  └─────────────────┘     Seedream（图）/ Tavily（联网）

定时任务：
  backup（每日 03:00 pg_dump，7 天滚动，独立 service）
```

## 4. 后端分层

```
api/              路由层（FastAPI router）
  ├ auth.py / game.py / worlds.py
  ├ admin.py            创作工坊 + 内容管理
  └ admin_models.py     LLM provider/slot/model 后台

services/         业务编排层
  ├ game_service.py        SSE 消费 + state commit + memory write + reflection 触发
  ├ session_lock.py        Redis 分布式锁
  ├ auth_service.py / audit_service.py
  ├ embedding_service.py / image_storage.py
  ├ generation_*.py        创作工坊任务/事件流/反馈
  ├ world_creator_agent.py 创作工坊核心 LLM 编排
  ├ model_management.py    slot/provider/model 动态绑定
  ├ npc_reflection_service.py
  ├ research_broker.py / tavily_search.py
  └ ...

engine/           世界引擎（无副作用核心）
  ├ orchestrator.py        主流水线（process_action）
  ├ director_agent.py / npc_agent.py / narrator_agent.py
  ├ memory_manager.py / state_manager.py
  ├ case_board.py / intent_system.py / narrative_arc.py
  ├ world_simulator.py / world_clock.py / event_system.py / ending_system.py
  ├ moderation.py / content_filter.py / input_sanitizer.py
  ├ context_builder.py / prompts.py
  ├ compressor.py / processing_hint.py / cost_guardrail.py
  └ world_engine.py        WorldEngine 包装

llm/              Provider 抽象层
  ├ base.py / router.py
  ├ deepseek.py / claude.py / gemini.py / grok.py / openai_compatible.py
  └ seedream.py

models/           SQLAlchemy ORM（user / world / script / draft / game / memory /
                  generation_task / model_management / audit_log /
                  npc_reflection / npc_relation / case_board_history）

middleware/       error_handler / logging / rate_limit
migrations/       Alembic（单 head + verify_*.py）
```

## 5. 前端分层

```
app/              Next.js App Router
  ├ /                  landing
  ├ /login
  ├ /discover          世界发现
  ├ /worlds/[id]       世界详情
  ├ /play/[id]         游玩主页（SSE 消费）
  ├ /history           历史会话
  └ /admin/            创作工坊 + 模型后台

components/       UI（admin/workshop / case-hologram / play 系列）

stores/           Zustand
  ├ auth.ts            用户/admin 状态
  └ game.ts            游戏会话 / SSE 状态机

lib/              纯逻辑工具 + API 封装
  ├ api.ts             fetch 封装
  ├ sse.ts             游戏 SSE 流（心跳 / 错误码 / connection_lost）
  ├ sse-parser.ts      低级 SSE 块解析
  ├ admin-api.ts       admin SSE（30min 超时 + abort）
  ├ admin-sse-events.ts admin 事件 schema
  ├ auth-redirect.ts   adminFetch 403 → /login
  └ ...                各 UI 子状态机
```

## 6. 关键数据流：玩家 action → SSE done

跨 8 个模块的最热路径。

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 前端 lib/sse.ts streamAction()                                   │
│    POST /api/game/{sid}/action  +  fetch ReadableStream             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. middleware/rate_limit.py                                         │
│    Redis token bucket（30/min/user） — 失败 429 + Retry-After       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. api/game.py /action                                              │
│    SessionLock(session_id) — Redis 分布式锁，保证单 session 串行     │
│    SSE EventSourceResponse（ping=30s 心跳）                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. services/game_service.process_action                             │
│    → orchestrator.process_action（生成器）+ _consume_turn（消费器）  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. engine/orchestrator.process_action 主流水线                       │
│                                                                     │
│    moderation_input    LLM 五分类 + 本地 fallback                   │
│         │              拒绝 → SSE error{code:moderation}, return    │
│         ▼                                                           │
│    world_tick          WorldSimulator: 时钟推进 + world events      │
│         │                                                           │
│         ▼                                                           │
│    cost_guardrail      ¥5 → cost_warning  / ¥6 → cap_reached return │
│         │                                                           │
│         ▼                                                           │
│    SSE: processing{phase:directing}                                 │
│         │                                                           │
│         ▼                                                           │
│    director            DirectorAgent.run（含 1 次 agent retry）     │
│                        失败 → SSE error{code:llm_parse}, return     │
│         │                                                           │
│         ▼                                                           │
│    append player_action 到 game_state.player_actions（cap 20）      │
│    update narrative_arc（三幕标签）                                 │
│    info_propagation：写各 NPC 私有 memory                           │
│         │                                                           │
│         ▼                                                           │
│    npc_parallel / npc_sequential（NPC-1）                           │
│      • Director 决定 npc_speech_order（≤3）                         │
│      • 顺序模式：每个后发言者看见 peer_dialogues_so_far              │
│      • 并行 fallback：asyncio.gather + 信号量(6)                    │
│      • 单个 NPC 抛错 fallback 空 dialogue（2.A.3）                  │
│         │                                                           │
│         ▼                                                           │
│    narrator                                                         │
│      • 早流式：跟 NPC 并行跑一段 prelude（atmospheric）             │
│      • weave：织合 director scene_direction + npc dialogues         │
│         │                                                           │
│         ▼                                                           │
│    case_board_ops 应用（仅 script 模式）                            │
│      • apply_case_board_ops 纯函数                                  │
│      • 写 case_board_history（append-only）                         │
│      • 严格 clue_id 锚点；无效 op 拒绝但不致命                      │
│         │                                                           │
│         ▼                                                           │
│    内部事件 state_ready{new_state, history_entries}                 │
│      • orchestrator yield 给 game_service（不外泄给前端）            │
│         │                                                           │
│         ▼                                                           │
│ 6. game_service._consume_turn 收到 state_ready：                    │
│    save_session_state（乐观锁 — version mismatch → 40901）          │
│    commit case_board_history                                        │
│    然后才开始往前端 yield narrative tokens                          │
│         │                                                           │
│         ▼                                                           │
│    SSE: narrative{text}（流式 tokens）                              │
│         │                                                           │
│         ▼                                                           │
│ 7. ending_system.check                                              │
│    script: hard endings + AI judgment                               │
│    free:   仅 AI judgment（hard 跳过）                              │
│    触发 → SSE ending{ending_type, title, summary}                   │
│         │                                                           │
│         ▼                                                           │
│ 8. SSE: state_update{game_state, quick_actions, triggered_events}   │
│    SSE: usage（token + cost）                                        │
│    SSE: done                                                        │
│         │                                                           │
│         ▼                                                           │
│ 9. 后置（异步 task，不阻塞 SSE done）：                             │
│    • memory_entries 写入（director extract / inform_npc / dual）    │
│    • npc_reflection_service.maybe_reflect（≥阈值新记忆）            │
│    • compressor._maybe_compress（≥20 轮未压缩）                     │
└─────────────────────────────────────────────────────────────────────┘
```

**关键时序**：state commit 先于 narrative tokens 外泄（`state_ready` 内部事件机制）——避免中途断连导致 game_state 跟玩家看见的内容不一致。

> ⚠️ **上图是 v1 流程**。当前默认 `_process_action_v2`：L1 narrator 提前起跑（不等 director 全量）、NPC 早绑、director 瘦身。**整轮加载生命周期**于 2026-05-30 重设（**play-turn-loading**）——首包前用蹭 director 流式真实里程碑的进度反馈（`processing{kind:progress}` received/reasoning/npcs_entering/writing，取代 `phase:directing` 模板 + 已删的 IntermissionAgent）；`done` 在正文流完 + core 就绪即发（消除 ~10s done-gap），`case_board` 作为 `case_board_update` follow-up 晚一拍补发。详见 [`modules/orchestrator.md §2.7`](./modules/orchestrator.md) + [`plans/play-turn-loading-2026-05.md`](./plans/play-turn-loading-2026-05.md)。

## 7. 模块文档索引

每篇模块文档遵循 `modules/_template.md` 的章节结构，**核心是能力矩阵**（按子领域分组，状态符号统一，密度 ≥ 20 个能力点）。

### 7.1 引擎核心

| 模块 | 内容 |
|---|---|
| [orchestrator](./modules/orchestrator.md) | `process_action` 主流水线 / 早流式 / 阶段 timing / narrative_arc 三幕 |
| [director](./modules/director.md) | DirectorAgent / DIRECTOR_TOOL schema / parse retry / player_action |
| [npc](./modules/npc.md) | NPC 演绎、记忆隔离、群像、关系、信息边界 |
| [narrator](./modules/narrator.md) | 叙事 weave + 早流式 prelude |
| [memory](./modules/memory.md) | 隔离记忆、语义召回、reflection、info_propagation |
| [case-board](./modules/case-board.md) | ops 序列、history、严格锚点 |
| [intent-system](./modules/intent-system.md) | NPC 内驱目标、urgency → effect |
| [world-simulator](./modules/world-simulator.md) | 时钟、世界事件、environment 变化 |
| [state-and-persistence](./modules/state-and-persistence.md) | GameState、乐观锁、SessionLock |

### 7.2 横切关注

| 模块 | 内容 |
|---|---|
| [llm-router](./modules/llm-router.md) | provider 抽象 + slot 绑定 + timeout/retry/identity |
| [sse-protocol](./modules/sse-protocol.md) | 完整 SSE 事件清单 + 错误码 + 心跳约定 |
| [cost-rate-moderation](./modules/cost-rate-moderation.md) | 成本 / 限流 / 内容审核三件横切 |
| [auth-and-admin](./modules/auth-and-admin.md) | 用户、admin、audit |

### 7.3 创作工坊

| 模块 | 内容 |
|---|---|
| [world-creator](./modules/world-creator.md) | 五层模型、SSE 任务流、并发限制、草稿/发布原子性 |

### 7.4 运维

| 模块 | 内容 |
|---|---|
| [deploy-and-config](./operations/deploy-and-config.md) | docker-compose、env 全清单、Alembic 流程 |
| [observability-backup](./operations/observability-backup.md) | Sentry、/health、structlog 关键事件、备份 |

### 7.5 数据

| 模块 | 内容 |
|---|---|
| [data/schema](./data/schema.md) | 所有表 + 字段说明 + Alembic head 演进 |

### 7.6 设计规范（保留原位）

| 文档 | 内容 |
|---|---|
| [design/visual-principles.md](./design/visual-principles.md) | UI 视觉原则 v2.1 |
| [design/frontend-spec.md](./design/frontend-spec.md) | 设计令牌 |
| [design/cover-art-spec.md](./design/cover-art-spec.md) | 封面规范 v1.1 |

### 7.7 产品

| 文档 | 内容 |
|---|---|
| [product/product-spec.md](./product/product-spec.md) | 产品方向（不是技术文档，做之前先读） |

### 7.8 历史归档

`_archive/decisions-2026-04-30.md` —— Phase 0/1/2/3 演进记录 + 2026-05-08 范围调整决策（哪些砍 / 为什么）。被新文档完全替代的旧内容（tech-design / 世界引擎 / 世界生成Agent / generation-agent-*）已删除，详见 [`_archive/README.md`](./_archive/README.md)。

变更类备查：根目录 `MIGRATION_NOTES.md`。

## 8. 怎么用这份文档

- **新加入项目**：本文 §2 系统级能力清单 → 按感兴趣的子域跳到对应模块矩阵 → 想看具体怎么实现的就看模块文档"实现要点"章节
- **找 gap / 优化点**：本文 §2 扫一遍 ❌ 和 🟡 行 → 跳模块文档"已知短板"看为什么没做 / 啥时候做
- **改某个具体功能**：直接跳对应模块文档 → 能力矩阵定位 → 关键代码位置 → 测试覆盖
- **怀疑代码跟文档冲突**：以代码为准，更新文档（顺便把"状态截至"日期改一下）
