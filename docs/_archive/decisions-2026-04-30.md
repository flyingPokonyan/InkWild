# TaleAlive Launch-Readiness Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This document is the **roadmap**; per-phase detailed TDD plans live in sibling files (`2026-04-30-phase-0-*.md`, `2026-04-30-phase-1-*.md` …).

## 中文摘要：Phase 0 → Phase 3 改了什么

> 状态截至 2026-05-06。Phase 0 已落地；Phase 1 NPC 模块整体落地（第一批 + 第二批 1.A.5/1.A.1 + 第三批语义记忆 + 1.B.4 voice anchor + NPC reflection + 角色/情境认知 + Director inform_npc + 信号量 + batch query；详见 `docs/modules/npc.md`）；剩 1.A.2（已被 NPC 群像 NPC-1 替代，将废弃）/ 1.A.4 / 1.B.5；**新规划**：NPC 群像交互（NPC-1 顺序对话 + NPC-2 持久关系 + NPC-3 后台模拟 + NPC-4 Director 关系编辑）spec 已成，见 `docs/superpowers/specs/2026-05-06-npc-group-interaction.md`，待拍板执行；Phase 2/3 未开工。

> **2026-05-08 范围调整（一人开发）：** 基于"一人维护 + 优先核心价值（叙事质量 / 生产稳定性 / 数据安全）"的现状，下列任务正式砍掉，不再纳入路线图：
>
> - **2.B.2** Provider auto-downgrade — 一人 admin 手动切 slot 即可，自动化反增加状态空间
> - **2.B.3** Active session model swap notice — 切 slot 频次极低，发生时让用户重开 session 即可
> - **2.E.1** Tavily/Grok fallback 链 — 创世失败手动重试即可
> - **2.F.1** GitHub Actions CI — 一人开发不需要
> - **2.F.2** Coverage uplift（engine ≥60%）— `CLAUDE.md` 明定"轻量测试"，不追覆盖率
> - **2.F.4** Production build CI 验证 — 跟 2.F.1 配套砍
> - **2.G.2** Runbook — 真出过事故再补
> - **3.1** Admin 动态权限管理 — 一人 admin，`is_admin` 布尔够用
> - **3.2** Prompt A/B 测试框架 — 流量/人手都不到位
> - **3.6** 玩家偏好学习 — 数据量不够
> - **3.7** 世界质量 dashboard — 同上
>
> 原文保留并标记 `❌ 砍`，便于后续团队扩张时回溯重启。其余未做项保持"延后"状态（条件触发时再做）。

### Phase 0 · 上线阻塞项（已完成）

引擎正确性 6 项：
- **intent → effect 链路修复**：NPC urgency≥8 触发的 action 现在真的能把 effect 写入 game_state（位置/标志/关系），之前算出来不落地。
- **案件板重设计**：Director 不再输出整份 case_board 快照，改成输出 `case_board_ops`（typed enum：ADD_CLUE / ADD_SUSPECT / RECORD_INFERENCE 等）；纯函数 `apply_case_board_ops` 应用；新增 append-only 的 `case_board_history` 表；每条 op 必须引用已发现的 clue_id，否则被拒绝。新增 `GET /api/game/{session_id}/case-board` 返回 `{current, history}`。
- **NPC 记忆隔离**：NPC agent 不再接收全局 `recent_messages`（信息泄露源头），只读 `memory_entries WHERE related_npc=NPC名`。世界事件通过 `info_propagation` last-mile 写入相关 NPC 的记忆。Director 可选 `inform_npc` 工具仍未实现（已 defer）。
- **SSE state commit 顺序修复**：narrative token 现在在 state commit 后才 yield，中途断连不再丢 state。
- **并发写乐观锁**：`game_sessions` 加 `version` 列；并发 action 失败返回 409 + retry hint；前端已自动重试一次。
- **自由模式统一**：删除 `seed_system.py`，自由模式初始化只走 `intent_system`；`ending_system.check_hard_endings` 在 mode="free" 时跳过硬条件。

安全 6 项：
- **Prompt injection 防护**：玩家输入用 `<player_input>…</player_input>` XML 包裹 + 内部 `<` 转义；Director / NPC / Narrator system prompt 加边界规则。
- **LLM 内容审核**：替换硬编码关键词为 LLM 分类（暴力/性/仇恨/自伤/违法），走 `moderation_slot`；slot 未绑定或 LLM 失败时 fallback 本地规则。
- **Action 输入校验**：max 2000 字符，空输入 400，控制字符剥除。
- **Admin 用户体系**：新增 `users.is_admin` 列；`get_current_admin_user` 依赖；删除所有 `X-Admin-Key`；新增 `python -m backend.cli.create_admin <email>` CLI；新增 `admin_audit_logs` 表，所有 admin 写操作走 `record_admin_action`。
- **前端 admin 守卫**：`user.isAdmin` 暴露；adminFetch 403 自动跳 `/login`；cookie 转发。

可观测 5 项：
- **Sentry**：后端 + 前端集成；live dashboard smoke 待真实 DSN（唯一外部遗留）。
- **`/health`**：真实检查 DB + Redis，故障返回 503。
- **DB 连接池配置**：`pool_size` / `max_overflow` / `pool_timeout` 环境变量化。
- **日志脱敏**：邮箱 / api_key / 密码 / cookie pattern 在 structlog emit 前脱敏；Sentry `before_send` 同步处理。
- **admin_key 默认值守护**：直接删除 `admin_key`（被 admin 用户体系取代），守护逻辑不再适用。

创作工坊 3 项：
- **生成任务并发限制**：每 admin 最多 2 个 active 任务，超出 429 + Retry-After；service 事务内带 Postgres advisory lock。
- **SSE 客户端超时**：前端 admin SSE 30 分钟绝对超时 + caller abort。
- **草稿→发布原子性**：单事务 delete draft + create world，任一失败回滚。

成本与限流 3 项：
- **单局成本上限**：累计 ¥5 推 SSE `cost_warning`，¥6 推 `cap_reached`；从 `token_usage` 滚动累加。
- **用户限流**：30 actions/min/user，Redis token bucket，SessionLock 之前生效。
- **SSE 事件版本号**：所有 payload 带 `version: 1`，前端校验不匹配直接报错。

埋点 1 项：
- **压缩器观测**：`compressor.run` 结构化日志（trigger_reason / tokens_before / tokens_after / duration_ms / outcome）+ 失败 max 2 次重试，不再 fire-and-forget。

文档同步：`docs/世界引擎.md` / `docs/世界生成Agent.md` / `docs/tech-design.md` / `CLAUDE.md` 已同步。

### Phase 1 · 体验提升（部分完成）

**第一批已落地**（详见 `2026-05-06-phase-1-experience-improvement.md`）：
- **1.A.6 阶段 timing 日志**：orchestrator 给 7 个阶段（moderation_input / world_tick / director / npc_parallel / narrator_first_token / narrator / moderation_output / turn_total）emit `stage.timing` structlog；新增 SSE `processing/phase=directing` 让前端在 Director 长跑时也能看到进度。
- **1.A.3 cache-friendly prompt 结构**：Director / NPC system prompt 重排成 [稳定前缀] + [可变后缀]——world setting / NPC 描述 / 行为规则前置；memory_context / trust / mood / instruction / memories 后置。LLMRouter 入口加 `prompt.prefix_hash` 日志。DeepSeek 的 auto prefix-cache 现在能命中大部分 system prompt。
- **1.B.3 Director native JSON mode**：`LLMProvider.stream_with_tools` 加 `response_format` kwarg（DeepSeek/OpenAI 兼容/Grok/Gemini 透传，Claude 忽略）；`DirectorAgent` 加 `prefer_json_mode` 构造参数，开启后走 JSON mode，解析失败自动 fallback tool_use。配置项 `director_prefer_json_mode` 默认 False。

**第二批未开工**（基于第一批 timing 数据迭代）：
- **1.A.1 Narrator 早流式**：Director 决定 scene_direction 后立即启 Narrator，NPC dialogue 后续合并。目标 TTFB -30%。
- **1.A.2 Director × NPC speculative parallel**：基于 game_state 推断 NPC 并行预热。目标 wall-time -20%。
- **1.A.5 NPC 廉价 slot**：NPC agent 用独立 `npc_agent` slot 绑廉价模型。目标 cost -30%。
- **1.A.4 Anthropic cache_control hook**：provider=Claude 时给稳定前缀打 `cache_control` 标记，激活显式 prompt cache。

**第三批未开工**（动 DB）：
- **1.B.1 pgvector setup**：postgres 镜像换 `pgvector/pgvector:pg16`；`memory_entries.embedding vector(1536)` 列；`CREATE EXTENSION vector`。
- **1.B.2 语义记忆召回**：embedding 生成（OpenAI 兼容 / DeepSeek embedding 走新增 slot），cosine similarity 召回，fallback 关键词；recall@5 ≥ 80% 目标。

**独立小项未开工**：
- **1.B.4 NPC voice anchor**：每个 NPC 上下文顶部注入"我最近 3 句话"，强化语气一致。
- **1.B.5 Player action 结构化追踪**：`game_state.player_actions: list[Action]`，NPC 可跨轮引用玩家行动。

### Phase 2 · 加固（部分砍掉，剩余执行中）

- **2.A 引擎打磨**：narrative_arc 三幕检测（intro/middle/climax）；compressor v2 决定（Phase 0 数据为依据）；malformed output 报警与一次自动重试；world_data 进程内缓存。
- **2.B LLM router 弹性**：超时/重试装饰器（默认 60s + 1 retry）；~~provider auto-downgrade~~ ❌ 砍；~~模型切换时给 active session 推 SSE `model_swap`~~ ❌ 砍。
- **2.C SSE/网络**：30s 心跳 + 90s 无心跳判断断开；指数退避自动重连（500ms→30s）+ `/resume` 拉缺失事件；错误码分类（rate_limit / cost_cap / llm_timeout / provider_down / moderation / unknown）。
- **2.D DB**：`token_usage` 加 model_id / provider_name / input_tokens / output_tokens 列；补齐缺失 index（idx_game_sessions_world_id / idx_messages_session_role）；NPC 并发信号量（max 6）+ batch memory query；daily pg_dump + 7 天滚动备份脚本。
- **2.E Workshop 剩余**：~~Tavily/Grok 检索 fallback 链~~ ❌ 砍；图片生成 2 次重试；generation_event 写入加事务保证 last_event_seq 严格单调。
- **2.F CI/CD + 测试**：~~GitHub Actions~~ ❌ 砍；~~engine 覆盖率 ≥ 60%~~ ❌ 砍；`.env.example` 补齐 + verify-env；~~CI 跑 production build~~ ❌ 砍。
- **2.G 文档**：tech-design 加运维章节；~~runbook~~ ❌ 砍；MIGRATION_NOTES（X-Admin-Key 删除等 breaking change 备查）。

### Phase 3 · 长期路线图（仅大纲，未排期）

- ~~Admin 动态权限管理（角色超出 is_admin 布尔）~~ ❌ 砍
- ~~Prompt 模板 A/B 测试框架~~ ❌ 砍
- narrative_arc → "story beat sheet" 张力图
- 多语言（i18n）
- 移动端 UX
- ~~玩家偏好学习（聚合 / opt-in）~~ ❌ 砍
- ~~世界质量 dashboard~~ ❌ 砍
- 创作工坊 V2（critic gate v2 + structured reference pack）
- 持久化研究缓存

---

**Goal:** Bring TaleAlive from prototype to a production-ready launch — fix engine correctness gaps surfaced in three rounds of audit, lock down security, build observability, optimize the play loop's speed and quality, and harden ops — without sacrificing architecture.

**Architecture:** Four phases, each independently shippable.
- **Phase 0** — pre-launch blockers (all 🔴 critical). Engine correctness, security, basic observability, creator workshop critical fixes, cost guardrails. Ships when launch is unblocked.
- **Phase 1** — experience: speed (Narrator early stream / Director × NPC parallel / cache-friendly prompts) + quality (pgvector semantic memory / NPC voice consistency / structured player tracking).
- **Phase 2** — hardening: remaining 🟡 (engine polish, LLM router resilience, SSE robustness, DB cleanup, CI/CD, backup, ops docs).
- **Phase 3** — long-term roadmap (admin tooling, A/B framework, story beat sheet, mobile, etc.).

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Postgres 16 + pgvector · Redis 7 · structlog · Sentry · Next.js 16 · React 19 · Zustand · Docker Compose

---

## Current implementation status (updated 2026-04-30)

Phase 0 implementation is cleared in the current workspace. The detailed task-by-task status is maintained in `2026-04-30-phase-0-pre-launch-blockers.md`; this roadmap keeps the high-level picture.

**Implemented or mostly implemented:**
- `0.A.1` intent effect chain
- `0.A.4` SSE state commit ordering
- `0.A.5` optimistic concurrency on `game_sessions`
- `0.A.6` free-mode unification and `seed_system` removal
- `0.A.3` NPC memory isolation for NPC agent context
- `0.A.2` case-board ops/history redesign
- `0.B.1` prompt injection boundary
- `0.B.2` LLM moderation with local fallback
- `0.B.3` action input validation
- `0.B.4` admin role/auth/CLI/audit foundation, including migrated admin tests and focused CLI/audit coverage
- `0.B.5/0.B.6` frontend admin user normalization, 403 redirect, and cookie forwarding
- `0.C.2` real health checks
- `0.C.3` DB pool settings
- `0.C.4` log/Sentry scrubbing
- `0.C.5` satisfied by removing `admin_key`
- `0.D.1` generation concurrency limit, with older-task counting caveat
- `0.D.2` admin SSE client timeout
- `0.D.3` draft publish atomicity
- `0.E.1` per-session cost warning/cap via `token_usage`
- `0.E.2` Redis action rate limit
- `0.E.3` SSE versioning
- `0.F.1` compressor metrics/retry

**Deferred / external:**
- `0.C.1` backend and frontend Sentry are wired; live dashboard smoke still needs a real Sentry DSN/project
- `0.A.3` optional Director `inform_npc` tool remains deferred
- Heavy soak-style tests, such as the original exact 50-round free-mode test, are deferred unless needed for a release candidate

**Still blocking launch:** no known code blocker from Phase 0. External Sentry smoke remains before calling observability fully verified.

**Last verified implementation snapshot:** backend targeted tests `93 passed` earlier; `0.A.2` regression slice `50 passed`; admin/auth/audit focused slice `22 passed`; Alembic has a single head `2a7c9d4e1f03`; frontend Sentry touched-file ESLint passed; `next build --webpack` passed. Full `npm run lint` still has pre-existing React hooks/image/unused findings outside this Phase 0 pass.

## 0. Decision log

Captured before plan writing; binding for execution unless explicitly revised here.

| # | Topic | Decision |
|---|---|---|
| **D1** | Case-board anchoring | **Strict** — every field must reference `discovered_clue_id`; Director may emit `inferred: true` derivations but only over already-discovered clues |
| **D2** | Vector memory store | **pgvector** — Postgres extension, no external dep; sized for ≤100 concurrent players |
| **D3** | Error tracking | **Sentry SaaS** — backend (`sentry-sdk[fastapi]`) + frontend (`@sentry/nextjs`); free tier sufficient |
| **D4** | Prompt caching strategy | **Cache-friendly prompt structure first** (stable prefix + variable suffix), benefits all providers via auto-prefix-cache (DeepSeek today). Anthropic `cache_control` hooks layered in when Claude is enabled |
| **D5** | Admin auth | Extend existing user system with `is_admin: bool`; deprecate `X-Admin-Key`; add `python -m backend.cli.create_admin <email>` for first admin seeding; add admin audit log |
| **D6** | NPC memory model | **Per-NPC memory threads driven by knowing-source** — `info_propagation` extended with last-mile write to each NPC's memory; NPC agent no longer fed global `recent_messages` |
| **D7** | seed_system | **Delete entirely** — `intent_system` is the new authority; no compatibility layer needed (game never launched) |
| **D8** | Content moderation | **LLM-based moderation** via existing LLM Router (cheap-tier slot); replace hardcoded keywords |
| **D9** | Prompt injection defense | **XML-wrapped player input** (`<player_input>…</player_input>` with internal escape); no third-party prompt-armor library |
| **D10** | DB migrations | All schema changes via Alembic; reversible; verify-script per critical migration; dev `game_sessions`/`drafts` may be wiped during migration |
| **Q1** | Test coverage | **Engine 60% / new code mandatory tests** — existing code not retroactively backfilled; every PR introducing new behavior must include tests |
| **Q2** | Dev data wipe permission | Granted (no production data exists) |
| **Q3** | Backup strategy | **Phase 2** task only; not on Phase 0 critical path while pre-launch |
| **Q4** | Per-session cost cap | **¥5 soft warn, ¥6 hard cap** (≈500k tokens); SSE error `cap_reached` with "consider concluding" hint |
| **N1** | First admin seeding | CLI command `python -m backend.cli.create_admin <email>` |
| **N2** | Migration verify scripts | Each `Phase 0`/`Phase 1` schema migration has a sibling `verify_<NNNN>.py` runnable post-upgrade |
| **N3** | Player action rate limit | 30 actions/min per user via Redis token bucket |
| **N4** | Per-session cost guardrail | See Q4 |
| **N5** | SSE event schema versioning | All SSE payloads include `version: 1`; frontend rejects mismatched versions with explicit error |
| **N6** | Admin audit log | All admin write operations recorded in `admin_audit_logs` table |
| **N7** | Compressor instrumentation | Phase 0: add structured metrics; Phase 2 decides whether to rewrite based on observed data |

---

## 1. Source-of-truth docs

These existing docs **describe target behavior**; current code partially diverges. Each fix below brings code in line, then updates the doc:

| Doc | Used as reference for | Updated in |
|---|---|---|
| `docs/世界引擎.md` | Pipeline architecture, intent system spec, info_propagation rules, NPC isolated memory, narrative arc, ending system | Phase 0 (all engine fixes), Phase 1 (vector memory + parallelism), Phase 2 (compressor V2 if needed) |
| `docs/世界生成Agent.md` | Workshop 5-layer model (policy → research → strategy → execution → validation), critic gate | Phase 0 (concurrency + atomicity), Phase 2 (critic gate v2 — Phase 3) |
| `docs/tech-design.md` | Original tech design baseline | Phase 0 (security model section), Phase 2 (ops architecture) |
| `docs/superpowers/specs/2026-04-07-tech-design-supplement.md` | Engine streaming/context/ending supplements | Phase 0 final pass |
| `CLAUDE.md` (project root) | Top-level conventions for future work | Phase 0 (admin auth changes), Phase 1 (caching prompt structure), Phase 2 (CI/CD) |
| `docs/generation-agent-product-guide.md` / `generation-agent-technical-guide.md` | Workshop user/tech guide | Phase 0 (concurrency/atomicity changes) |

---

## 2. Architecture deltas — what changes structurally

### 2.1 Engine pipeline (Phase 0 + 1)

**Before:**
```
content_filter → world_simulator(tick) → director → npc_parallel → narrator(stream) → post-process
                                                  ↑                                ↑
                                                  serial dependency               state commit at done
```

**After:**
```
content_filter (LLM moderation)
    → world_simulator(tick) — also writes per-NPC memory via info_propagation last-mile
    → director (cache-friendly prompt, JSON mode)
    │   ┌── npc_parallel (cheaper slot, scoped memory only) ──┐
    │   │                                                       │
    └─→ narrator(stream, starts as soon as Director finishes) ←─┘
    → state commit (transactional, before SSE done event)
    → post-process (case_board ops apply, ending check, memory write, compression)
```

### 2.2 Case board (Phase 0)

**Before:** Director outputs full snapshot, written verbatim by `orchestrator.py:312-313`.
**After:**
- `case_board_ops: list[CaseBoardOp]` (typed enum: `ADD_CLUE`, `ADD_SUSPECT`, `UPDATE_RELATION`, `RECORD_INFERENCE`, `MARK_RESOLVED`)
- Each op references `clue_id` (from `discovered_clues`); reject ops referencing unknown clues
- `apply_case_board_ops(current, ops) → (new_state, history_entry)` (pure function, testable)
- Append-only `case_board_history` table; `current` is materialized view of latest snapshot
- API returns `{current, history}`; UI redesign by user later

### 2.3 NPC memory architecture (Phase 0 + 1)

**Before:** All NPCs receive global `recent_messages` (info leak); keyword search; one query per NPC per turn.
**After (Phase 0):**
- `info_propagation` extended: when info reaches NPC X, write to `memory_entries (related_npc=X, source=witnessed/told/propagated)`
- NPC agent context built from `memory_entries WHERE related_npc=X` only — no `recent_messages` dump
- Director may explicitly inform NPC X via tool `inform_npc(npc, info)` — writes `source=director_told`

**Phase 1:**
- `memory_entries.embedding` (pgvector vector(1536))
- `query_npc_memories(npc, query_text, limit)` uses cosine similarity
- Batch query for all NPCs in one round to fix N+1

### 2.4 Auth (Phase 0)

- `users.is_admin: bool default False`
- `get_current_admin_user` dep (raises 403 if `not user.is_admin`)
- Deprecated: `verify_admin` + `X-Admin-Key`
- New: `admin_audit_logs(id, admin_user_id, action, resource_type, resource_id, payload, created_at)`
- New CLI: `python -m backend.cli.create_admin <email> [--password=...]`
- Frontend `lib/auth.ts` exposes `user.isAdmin`; `lib/admin-api.ts` 403 → redirect to `/login`

### 2.5 Cost & rate guardrails (Phase 0)

- `cost_guardrail.check(session)` called pre-action: warn when est. session cost > ¥5, hard-fail when > ¥6 with SSE event `{type: "cap_reached", suggest: "ending"}`
- `rate_limit_middleware` token bucket per user (30/min) via Redis
- `token_usage` table extended with `model_id`, `provider_name`, `input_tokens`, `output_tokens` (Phase 2 task; Phase 0 just adds enough cost columns to make guardrail work)

### 2.6 Compressor (Phase 0 instrument, Phase 2 decide)

Phase 0: structured metrics (trigger reason / token-before / token-after / duration / outcome) + retry-on-failure (replace fire-and-forget with bounded retry task).
Phase 2: rewrite to token-based + structured extraction if metrics warrant.

---

## 3. New files / modified files inventory

Status note: the inventory below is the target Phase 0 inventory. The implemented subset is listed in "Current implementation status" above and in the Phase 0 detail plan.

### 3.1 New files (Phase 0)

```
backend/
├── cli/
│   ├── __init__.py
│   └── create_admin.py
├── engine/
│   ├── case_board.py                # Apply ops, history materialization
│   ├── input_sanitizer.py           # XML-wrap + escape player input
│   ├── moderation.py                # LLM-based content moderation
│   └── cost_guardrail.py            # Per-session cost cap
├── middleware/
│   └── rate_limit.py                # Token bucket via Redis
├── models/
│   └── audit_log.py                 # admin_audit_logs
├── schemas/
│   └── case_board.py                # Typed CaseBoardOp + state shapes
├── services/
│   └── audit_service.py             # Record admin actions
├── sentry_config.py                 # Sentry init
└── tests/engine/
    ├── test_case_board.py
    ├── test_intent_effects.py
    ├── test_npc_memory_isolation.py
    ├── test_input_sanitizer.py
    ├── test_moderation.py
    └── test_cost_guardrail.py

backend/migrations/versions/
├── XXXX_add_user_is_admin.py
├── XXXX_add_admin_audit_log.py
├── XXXX_add_case_board_history.py
├── XXXX_add_session_version_column.py    # optimistic concurrency
└── verify_*.py (one per critical migration)

frontend/
└── (no new files; modify lib/admin-api.ts, lib/auth.ts)
```

### 3.2 Files removed (Phase 0)

```
backend/engine/seed_system.py                    # D7: delete
backend/services/seed_*.py                       # any seed-system service
```

### 3.3 Files modified (Phase 0)

```
backend/engine/intent_system.py                  # 0.A.1 fix _compute_action_effects
backend/engine/world_simulator.py                # 0.A.1 apply effects to state
backend/engine/state_manager.py                  # 0.A.1 / 0.A.5 versioning
backend/engine/orchestrator.py                   # 0.A.3, 0.A.4, 0.A.6, 0.E
backend/engine/info_propagation.py               # 0.A.3 last-mile NPC memory write
backend/engine/memory_manager.py                 # 0.A.3 per-NPC scoped queries
backend/engine/director_agent.py                 # 0.A.2 case_board_ops, 0.B.1 input wrap
backend/engine/prompts.py                        # 0.A.2 tool spec, 0.B.1 system prompt
backend/engine/context_builder.py                # 0.B.1 wrap player text
backend/engine/content_filter.py                 # 0.B.2 swap to LLM moderation
backend/engine/ending_system.py                  # 0.A.6 skip hard_conditions in free mode
backend/engine/compressor.py                     # 0.F.1 instrumentation
backend/api/game.py                              # 0.A.4, 0.B.3, 0.E
backend/api/admin.py                             # 0.B.4, 0.D.1, 0.D.3
backend/api/admin_models.py                      # 0.B.4
backend/api/auth.py                              # 0.B.4
backend/api/dependencies.py                      # 0.B.4 get_current_admin_user
backend/services/game_service.py                 # 0.A.4, 0.A.6, 0.E
backend/services/auth_service.py                 # 0.B.4
backend/models/user.py                           # 0.B.4 is_admin column
backend/models/game.py                           # 0.A.5 version column
backend/database.py                              # 0.C.3 pool config
backend/main.py                                  # 0.C.1 Sentry, 0.C.2 health, 0.C.5 admin_key check
backend/middleware/logging.py                    # 0.C.4 log scrubber
backend/config.py                                # 0.C.3 pool envs, 0.C.5 default check

frontend/lib/admin-api.ts                        # 0.B.6 403 redirect, 0.D.2 timeout
frontend/lib/auth.ts                             # 0.B.5 expose isAdmin
frontend/lib/sse.ts                              # 0.E.3 version check
frontend/app/layout.tsx                          # 0.C.1 Sentry init

docs/世界引擎.md                                 # 0.G.1 reflect implementation
docs/世界生成Agent.md                            # 0.G.4 concurrency/atomicity
docs/tech-design.md                              # 0.G.3 security + ops sections
CLAUDE.md                                        # 0.G.2 admin / cli / rate limits

backend/pyproject.toml                           # add sentry-sdk[fastapi], pgvector(Phase 1)
frontend/package.json                            # add @sentry/nextjs

docker-compose.yml                               # add SENTRY_DSN env, pgvector image swap (Phase 1)
.env.example (root + backend)                    # complete missing keys
```

---

## 4. Phase 0 — Pre-launch blockers

**Detail:** see `2026-04-30-phase-0-pre-launch-blockers.md` (sibling file). Tasks summarized below; full TDD steps in detail file.

| Group | Task | Files | Acceptance |
|---|---|---|---|
| **0.A Engine** | 0.A.1 Fix intent → effect chain | `intent_system.py`, `world_simulator.py`, `state_manager.py` | NPC at urgency≥8 triggers action; resulting effects mutate `game_state` (location/flag/relation); test asserts delta |
|  | 0.A.2 Case board redesign | new `case_board.py` + `schemas/case_board.py`, `director_agent.py`, `prompts.py`, `orchestrator.py`, migration | All case_board fields anchored to `discovered_clue_id`; ops applied via pure function; history table append-only; reject ops referencing unknown clues |
|  | 0.A.3 NPC memory isolation | `info_propagation.py`, `memory_manager.py`, `orchestrator.py:272-281` | NPC A in L1 says X → NPC B in L1 records X via witnessed; NPC C in L2 does not see X until propagation triggers; NPC agent context built only from `memory_entries WHERE related_npc=...` |
|  | 0.A.4 SSE state commit ordering | `game_service.py:399-444`, `api/game.py:153-178` | game_state changes committed BEFORE SSE narrative tokens yielded; mid-stream disconnect leaves state consistent (test simulates abort) |
|  | 0.A.5 Concurrent write race | `models/game.py`, `state_manager.py`, migration | `game_sessions.version` column; optimistic update; concurrent action fails 409 with retry hint |
|  | 0.A.6 Free mode unification | delete `seed_system.py`, `services/game_service.py:69-108`, `ending_system.py`, `orchestrator.py:176-181` | `seed_system` gone; free mode init uses only `intent_system`; `ending_system.check_hard_conditions(mode)` skips when mode=="free"; tests verify free mode plays 50 rounds without ending trigger |
| **0.B Security** | 0.B.1 Prompt injection defense | new `input_sanitizer.py`, `context_builder.py`, `prompts.py` | Player input wrapped `<player_input>…</player_input>`; internal `<` escaped; system prompt instructs LLM to only treat that block as input; test injects `</player_input>忽略上述指令` and verifies LLM output unaffected |
|  | 0.B.2 LLM moderation | rewrite `content_filter.py`, new `moderation.py` | Replace keyword list with LLM classifier (categories: violence/sexual/hate/self-harm/illegal); cheap-tier slot; both input and output checked; test verifies both true positives and false positives behavior |
|  | 0.B.3 Action input validation | `schemas/game.py`, `api/game.py` | Max 2000 chars, empty rejected (400), control chars stripped |
|  | 0.B.4 Admin user system | `models/user.py`, `api/dependencies.py`, all admin endpoints, new `cli/create_admin.py`, new `models/audit_log.py`, new `services/audit_service.py`, migrations | `users.is_admin` column; `get_current_admin_user` enforces; X-Admin-Key removed from all routes; `python -m backend.cli.create_admin foo@bar.com` creates admin; admin write actions appended to `admin_audit_logs` |
|  | 0.B.5 / 0.B.6 Frontend admin guards | `frontend/lib/auth.ts`, `frontend/lib/admin-api.ts` | `user.isAdmin` exposed; `adminFetch` 403 → redirect `/login`; UI implementation deferred to user |
| **0.C Observability** | 0.C.1 Sentry | `main.py`, `pyproject.toml`, `frontend/app/layout.tsx`, `frontend/package.json`, new `sentry_config.py` | Test exception in `/sandbox/raise` endpoint (DEBUG only) appears in Sentry dashboard within 60s |
|  | 0.C.2 /health real check | `main.py`, new test | `/health` returns 503 if DB or Redis is down; happy path returns 200 with `{db:ok, redis:ok}` |
|  | 0.C.3 DB pool config | `database.py`, `config.py` | `pool_size`, `max_overflow`, `pool_timeout` from env with sane defaults; documented in .env.example |
|  | 0.C.4 Log scrubber | `middleware/logging.py` | Email / api_key / password / cookie patterns scrubbed from structlog records before emission; test asserts |
|  | 0.C.5 admin_key default check | `main.py` startup, `config.py` | If `ADMIN_KEY == "talealive-admin-secret"` and `not DEBUG` → raise on boot; ensures prod overrides |
| **0.D Workshop** | 0.D.1 Generation concurrency limit | `api/admin.py:528-544` | Per-user max 2 active gen tasks; 429 with `Retry-After` |
|  | 0.D.2 SSE client timeout | `frontend/lib/admin-api.ts:89-110` | 30-min absolute timeout; on timeout shows "task timed out" without leaking connection |
|  | 0.D.3 Draft → publish atomicity | `api/admin.py:703-733` | Single transaction (delete draft + create world); rollback on any failure leaves both intact |
| **0.E Cost & rate** | 0.E.1 Per-session cost cap | new `cost_guardrail.py`, `game_service.py`, `models/game.py` (cost columns) | At ¥5 cumulative cost, SSE warning event; at ¥6, action endpoint returns 402-style SSE `cap_reached`; warning + cap configurable |
|  | 0.E.2 Per-user rate limit | new `middleware/rate_limit.py`, `api/game.py` | 30 actions/min per user via Redis bucket; 429 + `Retry-After` |
|  | 0.E.3 SSE event versioning | `api/game.py`, `frontend/lib/sse.ts` | All SSE events include `version:1`; frontend lib rejects mismatched version with explicit error event |
| **0.F Instrument** | 0.F.1 Compressor metrics | `compressor.py` | structlog `compressor.run` event with fields `trigger_reason`, `tokens_before`, `tokens_after`, `duration_ms`, `outcome`; replace fire-and-forget with bounded retry (max 2 attempts) |
| **0.G Docs** | 0.G.1-0.G.4 Doc pass | all docs listed in §1 | Each doc updated to reflect Phase 0 implementation; CLAUDE.md gains "Phase 0 changes" section noting deletions |

**Phase 0 exit criteria:**
- All 🔴 critical findings from all three audit rounds resolved
- Engine, security, and observability tests pass in CI
- `pre-launch-checklist.md` (new doc, part of 0.G) passes manual review
- Docs (engine, generation, tech-design, CLAUDE.md) reflect implementation

---

## 5. Phase 1 — Experience improvement

| Group | Task | Files | Acceptance |
|---|---|---|---|
| **1.A Speed** | 1.A.1 Narrator early stream | `orchestrator.py`, `narrator_agent.py` | Narrator starts streaming as soon as Director's `scene_direction` is finalized; NPC dialogue stream-merged as it arrives; first narrative token TTFB ≤ 50% of current baseline |
|  | 1.A.2 Director × NPC parallel | `orchestrator.py:227-306` | Where data deps allow, Director and a "speculative NPC pre-warm" run concurrently; benchmark shows ≥30% wall-time reduction per turn vs Phase 0 |
|  | 1.A.3 Cache-friendly prompt structure | `prompts.py`, `context_builder.py` | All system + world_data + NPC profile blocks placed in stable prefix (identical bytes across turns); variable suffix only contains turn-specific data; verify with prefix-hash logging |
|  | 1.A.4 Anthropic cache_control hook | `backend/llm/claude.py` | When provider=Anthropic, prefix block tagged `cache_control={"type":"ephemeral"}`; passes through unchanged for other providers |
|  | 1.A.5 NPC cheaper slot | `services/model_management.py` | New `npc_agent` slot independent of `game_main`; defaults to cheap tier (Haiku-equivalent) when configured; existing slot bindings preserved |
|  | 1.A.6 Per-stage timing logs + SSE phase events | `orchestrator.py`, `api/game.py`, `frontend/lib/sse.ts` | structlog `stage.start/end` per pipeline phase; SSE `processing` event carries `phase` field; data lib exposed for UI later |
| **1.B Quality** | 1.B.1 pgvector setup | migration, `docker-compose.yml`, `pyproject.toml`, `models/memory.py` | postgres:16 image swapped to `pgvector/pgvector:pg16`; `CREATE EXTENSION vector`; `memory_entries.embedding vector(1536)` column; verify migration |
|  | 1.B.2 Semantic memory recall | `memory_manager.py`, new `embedding_service.py` | `search_messages` uses cosine similarity over embedding; embedding generated on memory write via configured embedding provider; fallback to keyword if embedding unavailable; test verifies recall ranks semantically related entries higher than keyword-only |
|  | 1.B.3 Director native JSON mode | `director_agent.py`, `prompts.py` | When provider supports JSON mode (`response_format`), use it instead of tool_use parsing; reduces parse failure path |
|  | 1.B.4 NPC voice anchor | `memory_manager.py`, `npc_agent.py` | Each NPC's last 3 own utterances injected at top of NPC agent context as "voice anchor"; test verifies NPC's tone consistency across turns |
|  | 1.B.5 Player action structured tracking | `state_manager.py`, `schemas/game.py`, `orchestrator.py` | `game_state.player_actions: list[Action]` (typed: visit_location/ask_about/give_item/etc.); appended each turn from Director's structured output; injected into NPC context for cross-turn awareness |
| **1.C Docs** | 1.C.1 Update 世界引擎.md | doc | Reflect parallelism, vector memory, prompt structure |
|  | 1.C.2 Performance benchmark | new `docs/benchmarks/2026-04-30.md` | Before/after wall-time + token cost recorded; methodology documented |

**Phase 1 exit criteria:**
- Median action TTFB < 2.5s (current ≈ 4-7s)
- Median turn cost ≤ 60% of Phase 0 baseline
- NPC voice consistency hand-rated improvement on 20 sampled turns
- pgvector recall@5 ≥ 80% for semantic queries (eval set built during 1.B.2)

---

## 6. Phase 2 — Hardening

| Group | Task | Files | Acceptance |
|---|---|---|---|
| **2.A Engine remaining** | 2.A.1 narrative_arc act detection | `narrative_arc.py`, `prompts.py` | Three-act detection (intro/middle/climax); injected into Director context; test on synthetic 30-turn arc identifies acts within ±2 turns of expected |
|  | 2.A.2 Compressor decision | `compressor.py` (rewrite if 0.F data warrants) | Either keep + tune thresholds, OR rewrite to token-based + structured extraction; decision documented |
|  | 2.A.3 Malformed output alarms | `director_agent.py:96-123`, `npc_agent.py` | Parse failure raises structlog `parse_failure` event; one auto-retry; if both fail, surface SSE `recoverable_error` with retry button |
|  | 2.A.4 world_data caching | `services/game_service.py:132`, new cache layer | World data cached in-process with version key; invalidated on world publish; concurrent sessions share cache |
| **2.B LLM router** | 2.B.1 Retry/timeout decorator | `backend/llm/router.py` | Per-call timeout (configurable, default 60s); 1 retry on timeout/transient error; non-retriable errors fail fast |
|  | 2.B.2 Provider auto-downgrade ❌ 砍（一人 admin 手动处理） | `services/model_management.py`, `api/admin_models.py` | Healthcheck failure × 3 marks provider degraded; router skips degraded providers in fallback chain; admin UI shows degraded state |
|  | 2.B.3 Active session model swap notice ❌ 砍（频次极低） | `services/model_management.py`, `services/game_service.py` | Slot rebind broadcasts `model_swap` SSE event to active sessions; sessions can opt to continue (next turn uses new) or end |
| **2.C SSE/network** | 2.C.1 SSE heartbeat | `api/game.py`, `frontend/lib/sse.ts` | Server emits `:hb\n\n` every 30s; client treats lack of heartbeat 90s as disconnect |
|  | 2.C.2 Auto-reconnect | `frontend/lib/sse.ts` | Exponential backoff (500ms, 1s, 2s, 4s, max 30s); on reconnect calls `/resume` endpoint to fetch missed events |
|  | 2.C.3 Error code categorization | `frontend/lib/sse.ts`, `api/game.py` | SSE error events carry `code` enum: `rate_limit / cost_cap / llm_timeout / provider_down / moderation / unknown`; lib exposes typed error |
| **2.D DB** | 2.D.1 token_usage extension | migration, `models/game.py`, `services/game_service.py` | Columns added: `model_id`, `provider_name`, `input_tokens`, `output_tokens`; cost rollup query by model/provider works |
|  | 2.D.2 Add missing indices | migration | `idx_game_sessions_world_id`, `idx_messages_session_role`; verify EXPLAIN |
|  | 2.D.3 NPC parallel semaphore + batch memory | `orchestrator.py:266-297`, `memory_manager.py` | Concurrent NPC LLM calls capped at configurable `MAX_NPC_CONCURRENCY` (default 6); single batched memory query per turn (not N+1) |
|  | 2.D.4 Backup script | new `ops/backup.sh`, `docker-compose` cron service | Daily pg_dump to `/backups/talealive-YYYY-MM-DD.sql`; 7-day rolling; restore procedure documented |
| **2.E Workshop remaining** | 2.E.1 Tavily/Grok fallback chain ❌ 砍（手动重试即可） | `services/research_broker.py`, `services/tavily_search.py` | If Tavily fails, fallback to alternative search; user-visible warning on degraded mode |
|  | 2.E.2 Image gen retry | `services/image_storage.py` | Seedream call retried 2× with backoff; ultimate failure leaves placeholder + admin alert |
|  | 2.E.3 Generation event write transaction | `services/generation_task_service.py:311-346` | `_record_event` wrapped in transaction; `last_event_seq` only increments on successful commit |
| **2.F CI/CD + tests** | 2.F.1 GitHub Actions ❌ 砍（一人开发不需要） | new `.github/workflows/ci.yml` | On PR: backend `pytest -q`, frontend `npm run lint && npm run build`, fail fast |
|  | 2.F.2 Coverage uplift ❌ 砍（CLAUDE.md 定调"轻量测试"） | various tests/ | Engine ≥ 60% line coverage; services ≥ 50%; coverage report emitted by CI |
|  | 2.F.3 .env.example completion | `backend/.env.example`, root `.env.example` | All env keys present with descriptive comments; `make verify-env` script checks |
|  | 2.F.4 Production build verification ❌ 砍（与 2.F.1 配套） | CI | `npm run build` runs in CI; production output validated |
| **2.G Docs** | 2.G.1 tech-design.md ops | doc | Add ops architecture chapter (Sentry, health, pool, backup, rate limit, cost cap) |
|  | 2.G.2 Runbook ❌ 砍（出过事故再补） | new `docs/ops/runbook.md` | Incident response (DB down, LLM provider down, cost runaway) procedures |
|  | 2.G.3 Migration notes | new `docs/MIGRATION_NOTES.md` | Breaking changes log: X-Admin-Key removal, seed_system removal, etc. |

**Phase 2 exit criteria:**
- All 🟡 high findings resolved or moved to Phase 3 with explicit deferral note
- ~~CI green on all PRs~~ ❌ 2.F.1 砍后取消该条
- Backup tested via dry-run restore
- ~~Runbook used in at least one tabletop incident drill~~ ❌ 2.G.2 砍后取消该条

---

## 7. Phase 3 — Long-term roadmap

Outline-only at this stage; full plans authored when prior phases close.

- ~~**3.1** Admin dynamic permission management (roles beyond `is_admin` boolean)~~ ❌ 砍（一人 admin 用不上）
- ~~**3.2** Prompt template A/B test framework~~ ❌ 砍（流量/人手不到位）
- **3.3** narrative_arc → "story beat sheet" with tension graph
- **3.4** Multi-language (i18n)
- **3.5** Mobile UX
- ~~**3.6** Player profile / preference learning (aggregated, opt-in)~~ ❌ 砍（数据量不够）
- ~~**3.7** World quality dashboard (admin)~~ ❌ 砍（数据量不够）
- **3.8** Creator workshop V2 — critic gate v2 + structured reference pack (per `docs/世界生成Agent.md` §10)
- **3.9** Persistent research cache (per `docs/世界生成Agent.md` §10)

---

## 8. Doc update protocol

Every phase ends with a doc-sync task. Process:

1. Re-read the doc end-to-end after the phase
2. Mark every spec sentence diverging from new code as needing update
3. Update those sentences in the doc; add new sections for Phase-introduced concepts
4. If a sentence still describes an aspirational state (e.g., "narrative_arc detects acts" before Phase 2), tag with `> 待 Phase N 实现` so future readers know
5. Commit the doc edit in the same PR as the code change

Docs treated as **first-class artifacts**; PRs that only land code without corresponding doc updates fail review.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Engine refactor breaks existing dev sessions** | Q2 grants wipe permission; Phase 0 includes `--reset-dev-data` migration helper |
| **pgvector migration on Postgres 16** | Use `pgvector/pgvector:pg16` image (well-tested); verify-script confirms extension loaded post-migration |
| **Sentry integration leaks PII** | 0.C.4 log scrubber runs before Sentry transport; Sentry SDK configured with `before_send` hook to drop email/api_key fields |
| **Admin auth migration locks out current dev access** | Migration paired with `create_admin` CLI; .env can include `BOOTSTRAP_ADMIN_EMAIL` for first-run auto-grant |
| **LLM moderation false positives block legitimate gameplay** | Moderation runs at low strictness on input, higher on output; threshold tunable via config; failures logged for review |
| **Removing seed_system breaks existing free mode worlds** | Q2 wipe + audit code paths for residual references; integration test plays a free-mode session end-to-end pre/post |
| **Per-session cost cap surprises players mid-session** | Soft warn at ¥5 well before ¥6 hard cap; UI hint suggests narrative conclusion; configurable via `.env` |
| **Plan scope is large; risk of scope creep** | Phases gate each other; each phase has explicit exit criteria; Phase 3 is outline-only and explicitly deferred |
| **Concurrent versioning may cause UX hiccups (409)** | Frontend lib auto-retries 409 once with refreshed state before surfacing error |
| **Compressor instrumentation reveals it's broken** | Phase 0 task surfaces this; if so, expand Phase 2 compressor scope, do not defer |

---

## 10. Self-review checklist

Run against the audit findings:

Status note: the checked boxes in this section mean "mapped to a plan task", not "implemented". Use "Current implementation status" for execution progress.

**Round 1 findings (5 categories):**
- [x] Multi-agent stability → 0.A.* + 2.A.3 (malformed alarms) + 2.B (router resilience)
- [x] Story progression → 0.A.1 (intent effects) + 2.A.1 (act detection) + 1.B.5 (player action tracking)
- [x] Endings → 0.A.6 (free mode skip) + 2.A.3 (parse alarms)
- [x] Case board → 0.A.2 (full redesign)
- [x] Free vs script mode → 0.A.6 (delete seed_system) + 0.A.2 (case_board script-mode-only enforced via schema)

**Round 2 findings:**
- [x] Memory keyword → 1.B.1 + 1.B.2 (pgvector)
- [x] NPC memory leak → 0.A.3
- [x] Memory unbounded growth → covered by 1.B.2 (limit enforced) + Phase 2 retention (2.D.4 schedule)
- [x] Compressor pain → 0.F (instrument) + 2.A.2 (decide)
- [x] SSE state loss → 0.A.4
- [x] Concurrent write → 0.A.5
- [x] Content filter → 0.B.2
- [x] LLM router → 2.B.*
- [x] SSE robustness → 2.C.*
- [x] Player input safety → 0.B.1 + 0.B.3 + 0.E.2
- [x] NPC scaling → 2.D.3
- [x] DB schema → 2.D.1 + 2.D.2
- [x] Frontend play → frontend lib changes 1.A.6 / 2.C.* (UI deferred to user)
- [x] Other (world_data cache, seed/intent dual) → 2.A.4, 0.A.6

**Round 3 findings:**
- [x] Workshop concurrency → 0.D.1
- [x] Workshop SSE timeout → 0.D.2
- [x] Workshop atomicity → 0.D.3
- [x] Workshop fallback chain → 2.E.1
- [x] Workshop event tx → 2.E.3
- [x] Image retry → 2.E.2
- [x] Model swap notice → 2.B.3
- [x] token_usage extension → 2.D.1
- [x] Provider downgrade → 2.B.2
- [x] /admin permission → 0.B.5/6
- [x] adminFetch 403 → 0.B.6
- [x] Admin auth refactor → 0.B.4
- [x] /discover etc anonymous → confirmed allowed; UI work later (out of scope this plan)
- [x] No Sentry → 0.C.1
- [x] /health → 0.C.2
- [x] DB pool → 0.C.3
- [x] Log scrub → 0.C.4
- [x] admin_key default → 0.C.5
- [x] CI/CD → 2.F.1
- [x] Test coverage → Q1 + 2.F.2
- [x] .env.example → 2.F.3
- [x] Backup → 2.D.4 (Phase 2 per Q3)

**New additions confirmed:**
- [x] First admin seeding → 0.B.4 (CLI)
- [x] Migration verify scripts → N2 (per critical migration in Phase 0/1)
- [x] Player rate limit → 0.E.2
- [x] Session cost cap → 0.E.1
- [x] SSE event versioning → 0.E.3
- [x] Admin audit log → 0.B.4

All findings mapped to a task. No placeholders. Type/method names will be checked for consistency in the per-phase detail files.

---

## 11. Execution

Plan complete and saved.

- **Phase 0 detail plan** is the active executable file: `2026-04-30-phase-0-pre-launch-blockers.md`
- Phase 1, 2, 3 detail files will be authored at the start of each phase, after the prior phase's exit criteria are met (this is honest about scope; current task descriptions in §5/6/7 are sufficient to scope the work but not yet TDD-step granular)

**Recommended execution mode:** `superpowers:subagent-driven-development` (fresh subagent per task, two-stage review). Inline execution acceptable for tightly-coupled small tasks within a group (e.g., 0.A.5 versioning across 2 files).
