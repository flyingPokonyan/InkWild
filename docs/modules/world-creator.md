# World Creator（创作工坊）模块技术说明

> 状态截至 2026-07-16。世界生成使用受约束 Director + 固定 Workflow；脚本生成仍沿用同一任务/SSE/草稿基础设施。

创作工坊是 admin 端的**多步骤 AI 生成系统**——给一段中文描述，自动生成完整的"世界"（base_setting + locations + characters + playable + cover image）或"剧本"（绑定已有世界，生成 events + endings + playable）。

整个流程是**长任务**（10-30 分钟，含多次 LLM + 联网检索 + 图片生成），通过 SSE 流式给前端推阶段事件。任务状态持久化在 `generation_tasks` + `generation_task_events` 表，支持重连续看（`stream_task_events(task_id, after_seq=N)`）。

它**不直接**做的事：
- 不做玩家游戏运行时编排（这是 [orchestrator](./orchestrator.md) 的事）
- 不直接发布到玩家可见的 worlds/scripts 表（先落 draft，admin 显式 publish）
- 不做 admin 鉴权 / 审计（在 [auth-and-admin](./auth-and-admin.md)）
- 不直接做图片存储（用 `services/image_storage.py` 的 local / OSS 适配）

紧密耦合的上下游：
- 上：`api/admin.py` 的 `/world-generation-tasks` / `/script-generation-tasks` 端点 + 前端 `app/admin/generate/*`
- 下：[llm-router](./llm-router.md)（多个 slot 调用）+ Tavily（联网检索）+ Seedream（图片生成）

## 1. 当前世界生成流程

世界生成不是自由 Agent。Director 只做一次受约束规划，Workflow 冻结 `WorldSpec` 后按节点执行；完成、失败和发布资格由契约与状态机决定。

```text
Phase A: IP recognition
  → 用户确认 strict / loose / none
Phase B: research_pack(skip for known IP) → IP research → Director/WorldSpec
  → world_base → roster → lore + character batches
  → shared events → runtime events → playable/free-start
  → critic/moderation → visual brief/images → final contract → draft
  → durable async quality job → passed / needs_review / failed
```

关键完成语义：

- `strict` 已知 IP 必须有可用 pack、带可追溯 citations 的原作证据和至少一个 must-have；研究失败/过薄时在 builder 前停止，不再生成“同名原创世界”。
- `WorldSpec.ip_name` 继承 Phase A 识别结果，不依赖 pack 是否成功持久化。
- 生成槽单次模型调用最长 600 秒；超时记为 `generation_call_timeout`，不误报为 provider factory 超时。
- 失败/取消任务不创建 quality job；质量任务绑定 payload revision/hash。
- 流程校验使用代码检查规模、must-have、引用、事件和图片；内容质检独立读取最终角色关系、lore、完整事件因果、研究证据与 WorldSpec。
- 正常质量审核 1 次；低分、低置信度或 major violation 才追加第 2 次，结论分歧才追加第 3 次。

### B. World 生成主要节点（`WorldCreatorAgentV2.create_world`）

| phase | 内容 | 产出 |
|---|---|---|
| `research_pack` / `ip_research` | 原创素材研究；已知 IP 用两条互补检索 + evidence compile + canon finalize | `ResearchPack` / `IPKnowledgePack` |
| `world_director` | 冻结规模、主视角候选、lore 维度和调用预算 | `WorldSpec` |
| `world_base` / `character_roster` | 世界骨架、地点和角色名册 | base + roster |
| `lore_pack` / `characters` | lore 批量正文 + 角色详情批次 | lore + characters |
| `shared_events` / `events_data` | 共享历史、角色信息差，以及按互斥锚点分批的运行时事件 | events |
| `playable` / `free_start_stages` | 可玩角色和最多 3 个主视角起点批量生成 | playable + stages |
| `critic` | LLM 复审 + 自动修复 (`repair_completed` / 标记 quality_warnings) | warnings + 可能的 patch |
| `visual_brief` | 静态派生 `CoverBrief` + LLM 辅助出英文名/4 维 descriptor（不再调主 brief LLM）| `CoverBrief` + `char_briefs` 存到 self（不持久化）|
| `images` | hero（21:9）+ 角色头像（2:3）+ server-crop 3:2 cover；走 gpt-image-2 | image URLs |
| `validating` | 形状/必填字段校验 → warnings | warnings |

每个阶段 emit `progress` 事件（`phase`/`code`/`message`/`meta`），错误 emit `error` 事件，最后 emit `result` 事件（完整数据）+ `done`。

### C. Script 生成阶段流（`create_script`）

| phase | 内容 |
|---|---|
| `research` | 剧情线相关研究 |
| `script_base` | 剧本设定 / script_setting / outline |
| `events` | events_data（事件触发条件 + 效果） |
| `endings` | endings_data（各路径结局） |
| `playable` | 推荐主角 subset |
| `critic` | 复审 + 修复 + `review_started/review_adjusted/review_completed` |
| `script_visual_brief` | 父世界 `CoverBrief` 重建 + script_title_english + 每个 ending 的 `EndingCoverBrief` |
| `script_images` | script cover（3:2）+ N 张 ending card（3:2） |

**封面/角色/结局图 pipeline（2026-05 重构后）**：参见 `docs/plans/cover-image-prompt-redesign-2026-05.md` —— `services/cover_brief.py` + `services/cover_brief_helper.py` + gpt-image-2 极简自然语言 prompt 范式取代了原 `services/visual_brief.py` 的 dense DP-grammar 路径。

### D. SSE 事件 schema

| 事件名 | 时机 | payload 字段 |
|---|---|---|
| `progress` | 每阶段开始/进度/完成 | `phase`、`code`（如 `started`/`completed`/`brief_started`/`brief_ready`/`drafting_pulse`/`repair_completed`/`review_adjusted`）、`message`、`meta`（任意） |
| `warning` | 非致命问题（重试 / fallback） | 同 progress |
| `result` | 任务最终成功 | 完整 world / script JSON |
| `error` | 致命失败 | `{phase, message}` |
| `done` | 流末 | （无 payload） |

前端 `lib/admin-sse-events.ts::dispatchAdminSseEvent` 五种事件都映射到回调（`onProgress` / `onWarning` / `onResult` / `onError` / `onDone`）。

### E. 任务持久化与重连

| 能力 | 状态 | 实现 |
|---|---|---|
| `generation_tasks` 表（id / kind / status / payload / draft_id / created_by / 等） | ✅ | `models/generation_task.py` |
| `generation_task_events` 表（顺序日志，每条带 `seq` 单调递增） | ✅ | 同上 |
| 单事务写 event + 更新 last_event_seq（2.E.3） | ✅ | `_record_event` 显式 try/commit/except/rollback |
| 失败回滚不递增 seq（保证客户端 after_seq=N 永远拿连续） | ✅ | 同上 |
| `stream_task_events(task_id, after_seq)` 重连续看 | ✅ | `api/admin.py:/generation-tasks/{task_id}/stream` |
| 任务结束（result/error/done）后 stream 立即关 | ✅ | service 端检测 status |

### F. 并发限制（Phase 0.D.1）

| 能力 | 状态 | 实现 |
|---|---|---|
| 单 admin 最多 2 个 active 任务 | ✅ | `MAX_ACTIVE_TASKS_PER_ADMIN` |
| 超出抛 `GenerationTaskLimitExceeded`（HTTP 429 + Retry-After） | ✅ | `api/admin.py` line ~60-90 |
| Postgres advisory transaction lock（防竞态） | ✅ | service 端 `pg_advisory_xact_lock` |
| 内存级 asyncio.Lock 双重防护（同 process 内并发） | ✅ | `_generation_task_limit_locks[admin_user_id]` |
| 老任务（`request_payload.admin_user_id` 字段引入前的）不被计数 | 🟡 | 已知 caveat |

### G. 草稿 → 发布原子性（Phase 0.D.3）

| 能力 | 状态 | 实现 |
|---|---|---|
| `world_drafts` / `script_drafts` 草稿表 | ✅ | `models/draft.py` |
| 发布走单事务：`delete draft + create world` 或 `delete draft + create script` | ✅ | `api/admin.py:publish_world_draft` / `publish_script_draft` |
| 任一步失败 → 全回滚（草稿仍在，目标资源未创建） | ✅ | 同上 |
| Audit log（record_admin_action）写在 commit 之前 | ✅ | line ~616 / ~655 / ~885 |
| Audit 失败也回滚（保护审计完整性） | ✅ | 单事务 |
| 已发布世界覆盖（admin 用 `publish_world_draft` 覆盖同名 world） | 🟡 | 实测可行，UX 还粗糙 |

### H. SSE 客户端超时（Phase 0.D.2）

| 能力 | 状态 | 实现 |
|---|---|---|
| 30 分钟绝对超时 | ✅ | `frontend/lib/admin-api.ts` |
| Caller abort 支持（用户主动取消） | ✅ | `AbortController` |
| 超时显示 "task timed out" 不泄露连接 | ✅ | 显式 close + UI message |
| 不实现自动重连（admin 长任务断了重新启动） | 🟡 | 待评估，没痛点 |

### I. 联网检索

| 能力 | 状态 | 实现 |
|---|---|---|
| Tavily 主路径 | ✅ | `services/tavily_search.py` |
| Grok web_search 备用（接口在 LLM provider 层） | 🟡 | `WebSearcher` 接口存在；但 ResearchBroker 用 web_searcher 没串成 fallback |
| Tavily 失败 fallback 到 alternative search | ❌ | 已砍（一人 admin 手动重试即可） |
| Research 结果 LLM 总结成 reference_doc | ✅ | `ResearchBroker._summarize` 用 research_summarizer slot |
| Reference_doc 跨阶段累积 + truncate | ✅ | `_merge_reference_text(*parts)` |
| 信号检测（如有"基于现实历史"信号才触发研究） | ✅ | `_collect_research_signals` + `_decide_research_policy` |

### J. 图片生成（Phase 2.E.2）

| 能力 | 状态 | 实现 |
|---|---|---|
| Seedream 调用（`backend/llm/seedream.py`） | ✅ | `ImageGenerator.generate_image` |
| 2 次 retry（共 3 次尝试） + backoff 0.5s/2s | ✅ | `seedream.py` |
| 仅对 transient 错误重试（timeout / 5xx / connection） | ✅ | 异常类名匹配 |
| 4xx 立即失败 | ✅ | 同上 |
| 最终失败 fallback 到 placeholder URL（**不抛错**） | ✅ | `IMAGE_PLACEHOLDER_URL = "/static/placeholder-cover.png"` |
| 失败 emit `image_generation.failed` warn（含 prompt + attempts + error） | ✅ | structlog |
| 重试时 emit `image_generation.retry` info | ✅ | 同上 |
| 头像 + 封面分开生成（封面后 emit `cover_completed`，全部完成 emit `completed`） | ✅ | `create_world` line ~1146-1156 |
| 玩家可玩角色（playable）每人一张头像 | ✅ | `_generate_character_image` |

### K. Critic gate（生成质量复审）

| 能力 | 状态 | 实现 |
|---|---|---|
| Critic LLM pass（review/打分/给修复建议） | ✅ | `_normalize_generation_review_result` / `_normalize_playable_review_result` |
| 自动修复一次（按 review 提的问题 LLM 出 patch） | ✅ | `_build_repair_note` + 重新调主 LLM |
| 修复后再次 critic（无限循环兜底：修复不通过留 quality_warnings） | ✅ | line ~1010-1113 |
| Playable review 单独路径（`review_started/review_adjusted/review_completed`） | ✅ | line ~1310-1334 |
| Critic gate v2（更结构化的 reference pack） | ❌ | Phase 3，等 V1 数据 |

### L. 后端 service 函数

| 函数 | 作用 |
|---|---|
| `start_world_generation(prompt, genre, era, admin_user_id)` | 创建 task + draft 行（status=running） |
| `launch_world_generation(task_id)` | 后台 fire-and-forget 启动 generator + 把每个 yield 写 generation_task_events |
| `start_script_generation(world_id, outline, admin_user_id)` | 同上，剧本版 |
| `launch_script_generation(task_id)` | 同上 |
| `stream_task_events(task_id, after_seq)` | SSE 重连续看 |
| `_record_event(task_id, event_name, payload, increment_seq=True)` | 单事务写 event + 更新 last_event_seq（2.E.3） |

## 2. 关键能力实现要点

### 2.1 SSE 长任务的事件 sourcing 模型

**问题**：生成一份完整世界要 10-30 分钟。期间 admin 浏览器可能切走、断网、刷新。如果用纯流式 SSE（不持久化），断了就只能重头跑——成本和等待都不可接受。

**解决**：把"任务进度"建模成事件流，持久化到 `generation_task_events` 表（带单调递增 `seq`）。前端 SSE 接收事件的同时，每条 event 都带 `seq`。断线后重连用 `?after_seq=N` 拉缺失事件，状态可恢复。

**实现**：
- 后台启动方式：`launch_world_generation(task_id)` 用 `asyncio.create_task` fire-and-forget；任务函数里每个 `yield event` 都先调 `_record_event` 持久化再发出
- `stream_task_events(task_id, after_seq)`：先从 DB 拉 `seq > after_seq` 的事件批量发，然后跟 in-memory pubsub channel 接续实时事件
- 任务结束（emit `result` / `error` / `done`）后，service 持久化 status=completed/failed，stream 自动关

**取舍**：
- 拒绝了"纯内存 + 心跳"方案——admin 偶发断网就丢全部进度
- 拒绝了"用 worker queue（Celery / RQ）"——一人开发引入新基建不值得，asyncio.create_task + DB 持久化在 100 admin 并发内够用

### 2.2 _record_event 单事务（Phase 2.E.3）

**问题**：早期 `_record_event` 写 event 行 + 递增 last_event_seq 不在同一个事务里——失败时可能 last_event_seq 已涨但 event 行没插，前端 `after_seq=N` 永远拉不到 N+1，重连卡死。

**解决**：把"INSERT generation_task_events + UPDATE generation_tasks.last_event_seq"包到单事务。失败回滚两个动作，重新抛出原异常给上层处理。

**实现**：`generation_task_service.py:_record_event` 显式 `async with self.session_factory() as session:` + try/commit/except/rollback。回归测试 mock IntegrityError 验证 last_event_seq 不变。

**取舍**：
- 拒绝了"先 commit event 再 commit seq"方案——任一步失败都会让两者状态不一致
- 拒绝了"用 SAVEPOINT"——增加复杂度，全事务回滚更清晰

### 2.3 草稿 → 发布原子事务（Phase 0.D.3）

**问题**：早期发布草稿是"先 create world，再 delete draft"两步——中间失败会导致草稿被删但 world 没创建（或反之 world 创建了但草稿还在导致重复）。

**解决**：发布走单事务：
1. open transaction
2. INSERT into worlds（或 scripts）
3. INSERT into admin_audit_logs
4. DELETE from world_drafts
5. commit

任一步抛错全回滚，草稿保留 + 目标资源未创建。回归测试用"audit 失败"模拟事务前抛错，断言 draft 仍在 + worlds 表无新行。

**实现**：`api/admin.py:publish_world_draft` line ~860+ / `publish_script_draft` line ~1080+。审计写在 delete 之前（保护"曾经发布过"的事实即使后续事务失败也丢不了——但这个事实本身要求 commit 才生效；更重要的是不让审计成为最后失败点）。

**取舍**：
- audit log 写入失败也回滚——舍弃"事实已发生但没记账"的可能，宁愿用户重试
- 不允许"草稿 + world 同时存在"的中间态——简化语义，admin 编辑流程只关心"草稿 OR 已发布"

### 2.4 五层模型 + critic gate

**问题**：早期世界生成是单次 LLM 调用——LLM 偶发产出空字段、地点不一致、角色 personality 跟 secret 矛盾。质量不稳定。

**解决**：五层递进 + 多 LLM pass：
- **policy** 层先决定"要不要查资料"（根据描述里有没有"基于民国/赛博朋克/特定历史"等信号）
- **research** 用 Tavily 拉真实素材，LLM 总结成 reference_doc
- **strategy** 用 reference_doc 出 "brief"——是个"骨架计划"，让 execution 阶段有约束
- **execution** 用 brief + reference 调主 LLM 出最终产物
- **validation** 形状校验（必填字段 / list 类型 / playable ⊆ characters）+ critic LLM 复审 + 自动修复一次
- 修复后再 critic，仍不通过留 quality_warnings 标记给 admin

**实现**：
- 主入口 `WorldCreatorAgent.create_world / create_script` 按阶段串
- 每阶段 emit `started` → 跑 → emit `completed` 进度事件
- critic gate 在 `playable` 之后单独跑（line ~987-1113）
- repair pass 重新调 generation 主 LLM，把 review reasons 注入 prompt（`_build_repair_note`）

**取舍**：
- 多 pass 让生成成本翻 2-3 倍，但质量上去后 admin 不必频繁手动改/重新生成，净收益正
- 用三个独立 LLM slot（`world_creator` / `world_creator_planner` / `world_creator_critic`）便于 admin 按需调档（critic 可以用主档增加严格度）
- 拒绝了 critic gate v2（结构化 reference pack）—— 等 V1 跑数据再做（Phase 3）

### 2.5 图片生成 retry + placeholder（Phase 2.E.2）

**问题**：Seedream 偶发抽风（rate limit / 网络抖动 / 5xx）会让一次世界生成的最后一步失败——前面 20 分钟全废。

**解决**：图片调用加 2 次 retry（共 3 次尝试，backoff 0.5s/2s），仅对 transient 错误重试。最终失败 fallback 到 placeholder URL（`/static/placeholder-cover.png`）——**不抛错**让流程继续。Admin 可以后续手动重新生成图片。

**实现**：
- `seedream.py` 内置 retry 逻辑（按异常类名匹配 transient: APIConnectionError / APITimeoutError / RateLimitError / 5xx）
- 4xx 立即失败（auth / invalid 不该 retry）
- placeholder URL 常量在 `services/image_storage.py`
- 失败 emit `image_generation.failed` warn（含 prompt + attempts + 最终错误类型）

**取舍**：
- placeholder 不抛错而是降级——20 分钟生成内容不能因为一张图崩
- retry 只 2 次—— 再多没意义，rate limit 通常要等几分钟，不如 admin 手动改时再触发
- placeholder 路径写死成常量——拒绝了"配置项"，简单胜于灵活

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/services/world_creator_agent.py` | WorldCreatorAgent 主类（create_world / create_script + 各阶段实现 + critic gate） |
| `backend/services/generation_task_service.py` | 任务持久化 / launch / stream / _record_event |
| `backend/services/generation_strategy_service.py` | brief 生成（policy + strategy 层） |
| `backend/services/generation_prompt_builder.py` | 各阶段 prompt 模板 |
| `backend/services/generation_feedback.py` | 反馈/重新生成入口 |
| `backend/services/research_broker.py` | Tavily / web_searcher 统一入口 |
| `backend/services/tavily_search.py` | Tavily API client |
| `backend/llm/seedream.py` | 图片生成 + retry + placeholder |
| `backend/services/image_storage.py` | local / OSS 适配 + placeholder 常量 + save_generated_image_result |
| `backend/api/admin.py` | `/world-generation-tasks` / `/script-generation-tasks` / `/generation-tasks/{id}/stream` 路由 + 草稿发布 |
| `backend/models/generation_task.py` | GenerationTask / GenerationTaskEvent ORM |
| `backend/models/draft.py` | WorldDraft / ScriptDraft |
| `frontend/lib/admin-api.ts` | admin SSE helper（30min 超时 + abort） |
| `frontend/lib/admin-sse-events.ts` | SSE 事件 schema + dispatcher |
| `frontend/app/admin/generate/world/...` / `frontend/app/admin/generate/script/...` | 生成 UI |
| `frontend/components/admin/workshop/...` | 各阶段 UI 组件 |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `TAVILY_API_KEY` | `""` | Tavily 检索；空值跳过研究阶段 |
| `GROK_API_KEY` | `""` | Grok web_search 备用 |
| `IMAGE_STORAGE_BACKEND` | `local` | 图片存储后端（`local` / `oss`） |
| `IMAGE_STORAGE_DIR` | `static/images` | local 后端目录 |
| `OSS_*` 系列 | `""` | 阿里云 OSS 配置（admin 在 prod 用） |

| Slot | 模型档位 | 用途 |
|---|---|---|
| `world_creator` | 主档 | 主生成 LLM（execution 阶段） |
| `world_creator_planner` | 廉价档（可选） | brief / search plan 等小开销决策 |
| `world_creator_critic` | 主档（可选） | critic 复审；用主档保证严格度 |
| `research_summarizer` | 廉价档（可选） | 把 Tavily 结果压成 reference_doc |

未绑定的 slot 全部 fallback 到 `world_creator` 主档。

## 5. 数据库 schema

参见 [data/schema.md](../data/schema.md)。本节速查：

```sql
generation_tasks (
  id, kind ENUM('world','script'),
  status ENUM('pending','running','succeeded','failed','cancelled'),
  request_payload JSON,         -- 含 admin_user_id（0.D.1 后加）
  result_payload JSON,
  error_message,
  draft_id,                     -- 反查 world_drafts / script_drafts
  last_event_seq,               -- 单调递增（2.E.3 单事务保证）
  created_at, updated_at, completed_at
)
INDEX (status, created_at)
INDEX (kind, draft_id)

generation_task_events (
  id, task_id, seq,             -- 客户端 after_seq=N 用
  event_name,                   -- progress / warning / result / error / done
  payload JSON,
  created_at
)
UNIQUE (task_id, seq)
INDEX (task_id, seq)

world_drafts (
  id, name, payload JSON,       -- 完整生成产物
  created_by_admin_id,
  generation_task_id,           -- 反查
  created_at, updated_at
)
script_drafts (similar)
```

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_admin_generation_tasks_api.py` | 端点鉴权 + 启动 + stream + 并发限制（429） |
| `tests/test_generation_task_limit.py` | 并发限制核心逻辑（advisory lock + active count） |
| `tests/test_generation_task_record_event.py` | 单事务 INSERT + UPDATE + 失败回滚 + last_event_seq 不变（2.E.3） |
| `tests/test_admin_drafts_api.py` | 草稿列表 / 发布原子事务 / audit 失败回滚 |
| `tests/test_world_creator_agent_dynamic.py` | WorldCreatorAgent 端到端基础流程 |
| `tests/test_image_storage.py` | 存储后端切换 + placeholder URL 短路 |
| `tests/test_research_broker.py` | Tavily 调用 + summarize fallback |

## 7. 已知短板与未来扩展

### P2

- **Tavily fallback 链没接成**：`WebSearcher` 接口在但 `ResearchBroker` 没用它做 Tavily 失败 fallback。当前 Tavily 挂时阶段 fallback 走"无 reference_doc"——质量降级但流程继续。改进点工作量小（在 ResearchBroker 加 try/except + Grok 调用），但当前一人 admin 手动重试即可，没痛点。
- **草稿覆盖发布 UX**：`publish_world_draft` 当前会"用同名覆盖已有 world"，admin 看不到"将覆盖"提示。改进点是发布前显式 detect 同名 + 让 admin 确认是否覆盖。
- **单 admin 限制 caveat**：`generation_tasks.request_payload.admin_user_id` 引入前的旧任务不被计数，理论上一个 admin 可以"清空旧任务后再起 4 个 active"。当前没暴露，但需要在迁移文档（MIGRATION_NOTES）标记。

### P3

- **Critic gate v2**（roadmap 3.8）：当前 critic 是单次 LLM pass + 一次自动修复。v2 计划用结构化 reference pack（schema 校验 + 自动 patch + 多轮迭代）。等 V1 跑数据再做。
- **持久化研究缓存**（roadmap 3.9）：当前每次 research 都重新调 Tavily + 总结。同样的查询主题（如"民国上海茶馆"）多人多次重复 = 浪费。加 (query_hash → reference_doc) 缓存表能大幅降本。等创世量上来再做。
- **生成任务可中断**：当前任务一旦 launch 就不能取消（asyncio.create_task fire-and-forget）。admin 想中途停掉只能等超时。可以加 cancel endpoint + task.status='cancelled' 检查点，但工作量不小。
- **图片重新生成 UI**：placeholder 出现时 admin 没有"重新生成此图"的快捷按钮。当前要走"打开草稿编辑 → 单独触发图片生成"，体验差。
