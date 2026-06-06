# LLM Token 记账 AOP 化 · 2026-05

> 状态：阶段 A–D 已完成（2026-05-18）；待用户跑 `alembic upgrade head` + 端到端联调验证
> 负责：jie + Claude Code
> 预计：1–1.5 天

## 0. 为什么要做

当前 LLM token / cost 记账有三层缺口，导致**创作工坊（世界 / 剧本生成）和图像生成的成本完全没被统计**：

1. **数据模型层结构性挡死**：`token_usage.session_id` 是 NOT NULL FK → `game_sessions.id`，工坊任务没有 game_session，**插不进去**；`generation_tasks` 表自己也没有任何 token / cost 字段。
2. **消费者层把 usage 事件全部丢了**：9 处 LLM 调用点（`generation_strategy_service` / `world_creator_agent` v1+v2 / `character_roster_builder` / `events_data_builder` / `research_pack_builder` / `visual_brief` / `ip_recognizer` / `ip_research_pipeline` / `research_broker`）的 `async for event in llm.stream_with_tools(...)` 循环只识别 `text_delta` / `tool_use`，从不消费 `type=="usage"`。provider 侧明明在发，router 还盖了 `provider_name`/`model_id` 章，下游没接，等于一路丢。
3. **图像生成没有 usage 概念**：`ImageGenerator.generate_image` 返回的 `ImageResult` 没有 token / cost 字段，工坊 v1/v2 出图的成本完全失踪。

游戏侧（director / npc / narrator）能记录是因为 orchestrator 把 usage 透传到 `game_service.py:580` 那段 inline 写表——但这是"碰巧记上了"的偶发实现，不是架构。

**这次改造的本质**：把 token 记账从业务消费者上拽下来，做成横切关注点（AOP），单点切在 `LLMRouter` 和 `ImageGenerator` 上，业务代码再也不用关心 token 是否落库。

## 1. 核心架构

```
入口设 context                       router 拦截              sink 落库
─────────────────                    ──────────────           ─────────────
game_service.handle_turn()           stream_with_tools:       record_text_usage():
  with usage_context(                  if event.type==           open fresh db
    purpose="game",                       "usage":               compute cost via
    session_id=...,                     sink.submit(event,         pricing_lookup
    user_id=...,                              current_ctx())     insert TokenUsage
  ): ...                               yield event              (best-effort,
                                                                 失败只 log)
generation_task_service.run():       MeteredImageGenerator
  with usage_context(                  .generate_image():
    purpose="world_gen"|              await inner.generate    record_image_usage():
       "script_gen",                  sink.submit_image(...)    image_count=1,
    task_id=...,                                                cost = pricing×count
    user_id=...,
  ): ...
```

### 1.1 三大组件

- **`llm/usage_context.py`** —— `contextvars.ContextVar` 容器 + `UsageContext` dataclass + `set_usage_context()` async context manager。Python 的 contextvars 在 `asyncio.create_task` / `asyncio.gather` 都会自动拷贝当前 context，所以 NPC 并发、fire-and-forget reflection、工坊并发阶段都能正确归因。
- **`services/usage_recorder.py`** —— sink。`record_text_usage(event, ctx)` 和 `record_image_usage(provider_name, model_id, ctx)`。开独立 short-lived db session（同 `_reflect_one_npc` 模式），调 `pricing_lookup.get_pricing_for()` 算成本，写 `TokenUsage`。失败只 log，**不抛**——记账永远不阻断主流程。
- **`llm/router.py`** + **`services/metered_image_generator.py`** —— 拦截点。router 在 yield usage event 时 fire-and-forget 调 sink；image generator 装饰器在 `generate_image` 返回后调 sink。

### 1.2 数据模型变更

`token_usage` 表扩字段（保持单表，所有 admin 查询继续工作）：

| 字段 | 改动 |
|---|---|
| `session_id` | nullable（去掉 NOT NULL）|
| `task_id` | 新增 nullable FK → `generation_tasks.id`，加 index |
| `purpose` | 新增 varchar(20)，CHECK 约束在 7 档枚举 |
| `phase` | 新增 nullable varchar(50)，自由文本子阶段（如 `world_gen.research`） |
| `image_count` | 新增 int default 0 |

应用层约束：`session_id` 和 `task_id` 至少一个非空。`purpose` 永远非空。

**purpose 枚举（粗粒度）**：

```
game           director + npc + narrator + ending_system + world_engine
moderation     engine/moderation
reflection     npc_reflection_service
compression    orchestrator.compression_llm_router
world_gen      创作工坊世界生成相关全部
script_gen     创作工坊剧本生成相关全部
image_gen      所有图像生成
```

`phase` 用来下钻看异常，比如 `world_gen.research` / `world_gen.characters` / `script_gen.events`。

## 2. 分阶段任务

### 阶段 A — 数据模型 + Sink 骨架（半天）

- [ ] Alembic 迁移：
  - `token_usage.session_id` → nullable
  - 新增 `task_id` nullable FK + index
  - 新增 `purpose` varchar(20) NOT NULL（默认 'game' 用于已有行回填）
  - 新增 `phase` nullable varchar(50)
  - 新增 `image_count` int default 0
  - CHECK 约束 `(session_id IS NOT NULL) OR (task_id IS NOT NULL)`
  - 老行 backfill：`UPDATE token_usage SET purpose='game' WHERE purpose IS NULL`
- [ ] `models/game.py:TokenUsage` 同步加字段
- [ ] `llm/usage_context.py` 新建：
  - `@dataclass UsageContext { purpose, session_id?, task_id?, user_id?, phase? }`
  - `_usage_context: ContextVar[UsageContext | None] = ContextVar(..., default=None)`
  - `@asynccontextmanager async def usage_context(**kwargs)` —— set + reset
  - `current_usage_context() -> UsageContext | None`
- [ ] `services/usage_recorder.py` 新建：
  - `async def record_text_usage(event: dict, ctx: UsageContext)` —— 算 cost，写 TokenUsage
  - `async def record_image_usage(provider_name, model_id, ctx, count=1)` —— 查 `image_price_cents_per_image`，写 TokenUsage（input/output_tokens=0, image_count=count）
  - 顶层 try/except 吞所有异常，只 `logger.warning("usage.record_failed", ...)`
- [ ] 单元测试：context 在 `asyncio.create_task` 和 `gather` 下能传播；sink 失败不抛

### 阶段 B — Router 拦截 + 图像装饰器（半天）

- [ ] `llm/router.py:stream_with_tools` —— 在识别 usage event 的分支里：
  ```python
  if event.get("type") == "usage":
      ctx = current_usage_context()
      if ctx is not None:
          asyncio.create_task(record_text_usage(event, ctx))
  ```
  注意：放在盖章逻辑（line 163-169）之后，确保 sink 拿到的 event 带 provider_name/model_id。
- [ ] `services/metered_image_generator.py` 新建装饰器：
  ```python
  class MeteredImageGenerator(ImageGenerator):
      def __init__(self, inner, provider_name, model_id): ...
      async def generate_image(self, prompt, aspect_ratio, resolution):
          result = await self.inner.generate_image(...)
          ctx = current_usage_context()
          if ctx is not None:
              asyncio.create_task(record_image_usage(
                  self.provider_name, self.model_id, ctx
              ))
          return result
  ```
- [ ] `services/model_management.py:resolve_slot_image_generator` —— 返回前包一层 `MeteredImageGenerator`，拿到的 provider/model_id 信息从 slot 绑定来。
- [ ] 单元测试：router 拦截后 sink 被调用、event 仍正常 yield 出去；image generator 装饰器同理。

### 阶段 C — 入口设 context + 删除老写表（半天）

- [ ] `services/game_service.py` —— `handle_turn` / `resume` / `retry` 等入口处 `async with usage_context(purpose="game", session_id=..., user_id=...)` 包住主体。
- [ ] **删 `game_service.py:561-590` 那段 inline `TokenUsage(...)` 写入**（保留 cost_guardrail 的 `estimate_usage_cost_cents` 用于实时 guardrail 计算，但不再落库）。
- [ ] `engine/orchestrator.py:compression_llm_router` 调用点 —— 短暂 push `phase="compression"` 子 context（如有需要可单独拿 purpose=`compression`）。
- [ ] `services/npc_reflection_service.py:maybe_reflect` —— `async with usage_context(purpose="reflection", session_id=...)` 包住。注意 reflection 是 fire-and-forget，要在 `_reflect_one_npc` 内部设 context（而不是外部 game_service），因为外部 context 已经退栈。
- [ ] `engine/moderation.py` —— `purpose="moderation"`（如果它是独立调用而不是被 game flow 包含）。先验证它在主流程哪个位置被调用。
- [ ] `services/generation_task_service.py:run` —— `async with usage_context(purpose="world_gen" if task.kind=="world" else "script_gen", task_id=task.id, user_id=...)` 包住整个任务执行。
- [ ] 在世界 / 剧本生成 pipeline 的关键阶段，临时覆盖 `phase`（用 `usage_context(purpose=..., phase="world_gen.research")` 创建子 context）。先做：research_pack、characters、events、visual_brief、image。
- [ ] 跑一遍 game + workshop 双链路，sanity check：每个调用点都被 sink 接住，db 里能看到对应 purpose 的行。

### 阶段 D — 补 admin 视图（半天）

- [ ] `services/analytics_service.py` 新增：
  - `cost_by_purpose(db, days)` —— group by purpose 的 cost 总和 + 占比
  - `generation_task_cost(db, task_id)` —— 单个生成任务的 token / cost 汇总（按 purpose、按 phase）
  - `expensive_generation_tasks(db, days, limit, min_cost_cents)` —— top N 生成任务，关联 user 和 kind
- [ ] `api/admin_analytics.py` 三个新端点对应上面。
- [ ] `frontend/app/admin/analytics/page.tsx` 加卡片：
  - "按用途分类"（cost_by_purpose）—— 今日 / 7 天 game / world_gen / script_gen / image_gen 各占多少
  - "最贵的生成任务"（expensive_generation_tasks）—— 列表展示
- [ ] 工坊任务详情页 —— 显示这次任务总共花了多少（generation_task_cost）。位置：`frontend/app/admin/generate/...` 任务进度页或者历史页。

### 阶段 E — 验证收尾（待用户验证）

- [ ] **`alembic upgrade head` 跑迁移**（`e2f3a4b5c6d7_token_usage_aop_fields`）
- [ ] 现有 admin analytics 页面所有指标重新跑一遍，确认 KPI / trend / by_provider / by_model / session_cost / expensive_sessions 都没坏（理论上不会，schema 是增量字段且 session_id 仍由 game 行写入）
- [ ] 跑一次完整工坊世界生成 + 剧本生成 + 图像生成，db 里能看到每阶段 token / cost 行
- [ ] 跑一次完整游戏对局（含 NPC、reflection、moderation），确认 game purpose 行数与之前 inline 写表的数量一致
- [ ] 测试 sink 失败场景：人为让 pricing_lookup 抛错，确认主流程不受影响（已有单元测试覆盖：`test_record_text_usage_swallows_db_failure`）
- [ ] 跑现有 `docs/modules/llm-router.md` 和 `docs/modules/state-and-persistence.md` 是否需要更新
- [ ] 此 plan 状态改为"已完成"

### 实施日志（2026-05-18）

**阶段 A — 数据模型 + Sink 骨架** ✅
- `migrations/versions/e2f3a4b5c6d7_token_usage_aop_fields.py` —— 加 task_id / purpose / phase / image_count，relax session_id，老行回填 purpose='game'，CHECK 约束
- `models/game.py:TokenUsage` —— 同步新字段
- `llm/usage_context.py` —— `UsageContext` dataclass + `usage_context()` ctx manager + `push_usage_context() / pop_usage_context()` 命令式 API + `VALID_PURPOSES` enum
- `services/usage_recorder.py` —— `record_text_usage()` / `record_image_usage()` + `fire_and_forget_*()`，failure-swallowing
- `tests/test_usage_context.py` —— 11 个测试：context 默认值 / set+reset / asyncio.create_task 传播 / gather 传播 / 嵌套合并 / 嵌套覆盖 / sink 三种失败路径

**阶段 B — 拦截点** ✅
- `llm/router.py` —— `stream_with_tools` 在 usage 事件路径加 `_fire_and_forget_text_usage(event, ctx)`，懒导入避免循环
- `services/metered_image_generator.py` —— `MeteredImageGenerator` 装饰器，wrap 后 `purpose=image_gen` 覆盖父级（保留 task_id/session_id/user_id 用于归属）
- `services/model_management.py:resolve_slot_image_generator` —— 两条路径（slot-bound + grok 回退）都包 `MeteredImageGenerator`
- `tests/test_usage_recording_hooks.py` —— 6 个测试：router 有/无 ctx 行为 / image wrapper 有/无 ctx / image wrapper purpose 覆盖 / image wrapper 失败不计费

**阶段 C — 入口设 context + 删 inline 写表** ✅
- `services/game_service.py`：
  - 3 入口（`start_game` / `process_action` / `resume_game`）的 LLM 段包 `with usage_context(purpose="game", session_id=..., user_id=...)`
  - 删除 `_consume_turn` 中 `if usage := event.get("usage"): TokenUsage(...)` 那 30 行 inline 写表（line 561-590）
  - 删除 `get_pricing_for` / `estimate_usage_cost_cents` 已无用的导入
- `services/generation_task_service.py`：
  - `_run_world_generation` 改为薄 wrapper + `_run_world_generation_impl`，`push_usage_context(purpose="world_gen", task_id, user_id)` + try/finally pop
  - `_run_script_generation` 同样模式（purpose="script_gen"）
  - 加 `_load_task_user_id(task_id)` 辅助
- `services/npc_reflection_service.py:reflect` —— LLM 段包 `with usage_context(purpose="reflection", session_id=...)`，覆盖继承的 `game`
- `engine/orchestrator.py` —— 压缩 LLM 段包 `with usage_context(purpose="compression", session_id=...)`
- `engine/moderation.py:classify` —— LLM 段包 `with usage_context(purpose="moderation")`

**阶段 D — 补 admin 视图** ✅
- `services/analytics_service.py` 加：
  - `cost_by_purpose(db, days)` —— group by purpose 总和 + 占比 + tokens + image_count
  - `generation_task_cost(db, task_id)` —— 单任务 by phase + purpose breakdown
  - `expensive_generation_tasks(db, days, limit, min_cost_cents)` —— TOP N 关联 user
- `api/admin_analytics.py` 加 3 个端点：
  - `GET /api/admin/analytics/cost-by-purpose?days=N`
  - `GET /api/admin/analytics/generation-tasks/{task_id}/cost`
  - `GET /api/admin/analytics/expensive-generation-tasks?days=N&limit=K`
- `frontend/app/admin/analytics/page.tsx` —— 加两张表格卡片："按用途分类" + "最贵的生成任务（TOP 10）"，purpose enum 用中文 label

**回归测试**：targeted 101 tests passed（usage_context、hooks、game_service、orchestrator、compressor、moderation、workshop、generation_task、cost_guardrail、world_creator_v2、world_creator_agent_dynamic、generation_strategy、research_pack_builder）。全量 733 passed / 4 pre-existing failed（与本次改动无关：IP 抽取、OSS 后端、事件状态、bootstrap binding）。

**偏离计划之处**：
- 工坊任务详情页未加 cost 面板（drafts 页不直接持有 task_id，加 UI 会引入额外耦合）。当前替代方案：`expensive-generation-tasks` 表 + `generation-tasks/{task_id}/cost` API 端点供 ad-hoc 查询。如果你需要 draft 页上嵌入"这次花了多少"卡片，再补一个小补丁。

## 3. 关键决策记录

- **单点写入而非双写** —— `game_service.py:580` 那段删掉。整个系统只有 sink 一处写 TokenUsage，杜绝"将来又忘了接 usage 事件"的可能。代价是 token 记账与 Message 行不在同一 txn——可以接受，token 是审计 / 会计数据，不要求与对话原子性。
- **purpose 粗粒度 + phase 自由文本** —— 7 档 enum 满足"按大类分账"，phase 满足下钻排查异常。新增大类时改 CHECK 约束 + enum，不常发生；phase 不限制，开发者随时塞。
- **图像复用 token_usage 表，不另开** —— `image_count` 字段 + `input/output_tokens=0` 表示图像行，cost_cents 由 `provider_models.image_price_cents_per_image × image_count` 算。所有 admin 查询不用区分文本 / 图像。
- **sink 异步 + 吞异常** —— `asyncio.create_task(record_text_usage(...))` 不 await，主流程不等。sink 内部 try/except 全包，最差结果是丢账不影响业务。
- **contextvars 在 reflection 这种 fire-and-forget 任务里要在子任务内部 set**，因为父 context 已经退栈。一致原则：谁是"逻辑根任务"，谁负责 set。

## 4. 不在范围内（明确不做）

- 不动游戏侧 cost_guardrail 实时校验逻辑——它仍然按当前 turn 累计算（不依赖 token_usage 表落库）。
- 不做 token 用量预算 / 告警（"工坊本月超 $X 报警"）—— 这是后续话题。
- 不做按 user / world 维度的成本分账视图 —— admin 已有 expensive_sessions 类似维度，足够一阵子。
- 不重写 admin analytics 前端整体设计——只在现有页面加卡片。

## 5. 参考文件清单

实现时直接打开的文件：

```
backend/
  models/game.py                              # TokenUsage 加字段
  migrations/versions/_new_                   # 新 alembic
  llm/usage_context.py                        # 新建
  llm/router.py                               # 拦截
  services/usage_recorder.py                  # 新建 sink
  services/metered_image_generator.py         # 新建装饰器
  services/model_management.py                # resolve_slot_image_generator 包装
  services/game_service.py                    # set context + 删 580 那段
  services/generation_task_service.py         # set context
  services/npc_reflection_service.py          # set context (子任务内)
  engine/orchestrator.py                      # compression context
  engine/moderation.py                        # moderation context
  services/analytics_service.py               # 3 个新函数
  api/admin_analytics.py                      # 3 个新端点
frontend/
  app/admin/analytics/page.tsx                # 加卡片
  app/admin/generate/.../任务详情页           # 显示 task cost
docs/
  modules/llm-router.md                       # 更新
  modules/state-and-persistence.md            # 更新
```
