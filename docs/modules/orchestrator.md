# Orchestrator 模块技术说明

> 状态截至 2026-05-08。覆盖 Phase 0 全套 + Phase 1（早流式 / cache-friendly / 玩家行动追踪 / 三幕检测）+ Phase 2（NPC 信号量 + batch query / Director parse retry / NPC 容错 / SSE 心跳 / LLM router timeout）落地后的形态。

> ⚠️ **v2 运行时更新（2026-05）**：本文主体描述 **v1 流水线**（`process_action` 旧路径，含 narrator 早流式 prelude / `processing(phase=directing/thinking)` / IntermissionAgent 氛围短句）。当前**默认走 `_process_action_v2`**（`settings.runtime_architecture_v2_enabled=True`）：L1 narrator 提前起跑（scene_direction 就绪即织合，不等 director 全量）、NPC 早绑（partial 信号触发）、director 输入/输出瘦身。其**整轮加载生命周期**又于 **2026-05-30（play-turn-loading）** 重设——见 **[§2.7](#27-v2-整轮加载生命周期2026-05-30)** + [`docs/plans/play-turn-loading-2026-05.md`](../plans/play-turn-loading-2026-05.md) + [`sse-protocol.md`](./sse-protocol.md)。v2 已移除 prelude 早流式 + IntermissionAgent；本文 v1 描述在 v2 路径不适用，以代码为准。

Orchestrator 是世界引擎的**主调度器**——`process_action(...)` 是单回合（一次玩家行动）的核心异步生成器，按固定时序调度 moderation / world tick / Director / NPC / Narrator / 状态结算 / 后置任务，逐步 yield SSE 事件。

它**不直接**做的事：
- 不做 LLM 调用（`engine/director_agent.py` / `npc_agent.py` / `narrator_agent.py` 各自负责）
- 不做 DB 写入（commit 在 `services/game_service.py::_consume_turn` 收到 `state_ready` 内部事件后）
- 不做 memory 查询的 SQL（`engine/memory_manager.py`）
- 不做 SSE 序列化（`api/game.py::to_sse_event`）

紧密耦合的上下游：
- 上：`services/game_service.py`（消费 orchestrator 的事件流，commit state，触发 reflection 异步任务）
- 下：所有 `engine/` 子模块 + `services/npc_reflection_service.py`

## 1. 能力矩阵

### A. 主流水线编排

| 能力 | 状态 | 实现 |
|---|---|---|
| 8 阶段固定时序（moderation_in → world_tick → director → npc → narrator → moderation_out → state commit → postprocess） | ✅ | `process_action` 主体 |
| 阶段间错误隔离（director 抛 → 干净 abort；NPC 抛 → fallback；narrator prelude 抛 → warn 继续） | ✅ | 各阶段 try/except |
| 内部事件 `state_ready`（不外泄前端） | ✅ | `process_action` line ~858；外泄会被 `to_sse_event` 显式拒绝 |
| moderation 输入拒绝 → SSE `error{code:40001}` 立即 return | ✅ | line ~327 |
| DirectorParseError → SSE `error{code:llm_parse}` 立即 return | ✅ | line ~412（2.A.3） |
| 单 NPC 失败 → fallback `NPCResult(dialogue="")` 不崩 turn | ✅ | `_run_all_npcs` 顺序+并行两路径 |
| narrator prelude 失败 → warn 不中断（直接进 weave） | ✅ | line ~779 |
| `_maybe_compress` 后置异步触发（不阻塞 done） | ✅ | line ~952 |

### B. 阶段 timing 埋点

| 能力 | 状态 | 实现 |
|---|---|---|
| `_emit_stage_timing` 统一埋点函数 | ✅ | line ~63 |
| 8 个阶段 stage：moderation_input / world_tick / director / npc_sequential 或 npc_parallel / narrator_first_token / narrator_prelude / narrator / moderation_output / turn_total | ✅ | 散布在各阶段 |
| 每条日志带 session_id + round_number + duration_ms + 自定义字段 | ✅ | 所有调用 |
| outcome 字段（passed/rejected/flagged 等） | ✅ | moderation 阶段 |
| narrator_first_token 区分 source（prelude/weave/single） | ✅ | line ~770 / ~885 |
| 自由模式 stage_summary 触发不单独埋点（合并在 narrator） | 🟡 | 没单独 stage |

### C. NPC 调度

| 能力 | 状态 | 实现 |
|---|---|---|
| 顺序对话模式（NPC-1，默认） | ✅ | `_run_all_npcs` sequential 分支 + `peer_dialogues_so_far` 注入 |
| 并行 fallback 模式 | ✅ | `asyncio.gather(..., return_exceptions=True)` |
| 模式切换 flag（`settings.npc_dialogue_sequential_enabled`） | ✅ | line ~664 |
| Director 指定 `npc_speech_order` 控制谁开口 | ✅ | line ~666-675 |
| 发言人上限 `npc_max_speakers_per_turn` 默认 3（兜底 trim） | ✅ | line ~671-673 |
| 信号量并发上限 `npc_max_concurrency` 默认 6（仅并行路径生效） | ✅ | `asyncio.Semaphore` |
| 同场 peer NPC 计算（按 schedule 时段定位） | ✅ | line ~600-620 |
| peer personality 截断 60 字（不泄 secret） | ✅ | line ~618-620 |
| 单 NPC 抛错容错 → fallback 空 dialogue（2.A.3） | ✅ | 顺序+并行两路径都有 |
| NPC 跳过 voice_anchor / peer_relations / reflection 加载失败兜底 warn | ✅ | line ~563/577/592 try/except |
| Narrator 早流式跟 NPC 并行 | ✅ | `asyncio.create_task(_run_all_npcs())` |
| 玩家行动 `recent_player_actions` 透传到每个 NPC（1.B.5） | ✅ | line ~654 |

### D. Narrator 早流式 + weave

| 能力 | 状态 | 实现 |
|---|---|---|
| Prelude 阶段跟 NPC 任务并行（1.A.1） | ✅ | line ~751-790 |
| 早流式开关 `settings.narrator_early_stream_enabled` 默认 True | ✅ | line ~746 |
| Prelude tokens 直接 yield narrative（玩家立即看见） | ✅ | line ~774 |
| Weave 阶段拿 `prelude_text` 续写，不重复开头 | ✅ | line ~870-893 |
| TTFB 计入 `narrator_first_token`（区分 prelude/weave/single） | ✅ | 同 B |
| Prelude usage + weave usage 合并到 done 事件 | ✅ | `_merge_usage` |
| 早流式失败 fallback 走单次 weave（不会两遍重复内容） | 🟡 | prelude 失败 prelude_text 留空，weave 自己开场 |

### E. 上下文构造（喂 Director 的 memory_context）

| 能力 | 状态 | 实现 |
|---|---|---|
| 结构化记忆段（director memory_extracts 累计） | ✅ | `memory_manager.build_memory_context` |
| 世界张力段（`world_conflicts`） | ✅ | line ~333-340 |
| NPC schedule 段（同场 NPC 信息） | ✅ | `build_npc_schedule_context` |
| 世界脉搏段（`build_world_pulse_directive`，按模式定调） | ✅ | line ~346 |
| 本轮世界事件段（`world_events_context`） | ✅ | line ~362-364 |
| 环境变化段（`environment_changes`） | ✅ | line ~367-368 |
| narrative_arc 三幕摘要段 | ✅ | `arc_summary` |
| 自由模式 stage_summary 追加（≥30 轮触发） | ✅ | line ~849-856 |
| recall_memory 工具回调注入（关键词搜旧记忆） | ✅ | line ~389-392 |

### F. 信息传播 + 记忆写入调度

| 能力 | 状态 | 实现 |
|---|---|---|
| `write_info_propagation_memories`（world_events → 各 NPC 私有记忆） | ✅ | line ~473 |
| `write_dual_perspective_memories`（NPC↔NPC 互动事件，双视角） | ✅ | line ~480-493 |
| Director `inform_npc_calls` 显式植入 NPC 私有记忆（0.A.3 余项） | ✅ | line ~497-520 |
| 拒绝 inform 不存在 NPC（防 Director 幻觉污染） | ✅ | line ~502 + warn |
| importance high/medium/low → 8/5/3 数值 | ✅ | `_importance_to_int` map |
| `batch_query_npc_memories` 一次 SQL + 一次 embed（修 N+1，2.D.3） | ✅ | line ~530 |
| 记忆写入实际持久化在 `game_service` 后置（这里只构造 dual_memory_entries） | ✅ | line ~471 + done 事件透传 |

### G. 状态结算

| 能力 | 状态 | 实现 |
|---|---|---|
| `apply_state_updates`（director state_updates → GameState） | ✅ | line ~824 |
| `check_events` + `apply_event_effects`（world_data.events 触发） | ✅ | line ~825-827 |
| `apply_case_board_ops` 仅 script 模式 | ✅ | line ~830 |
| 案件板 op 失败抛 CaseBoardError → 静默丢弃 + warn（不致命） | ✅ | line ~838-839 |
| 案件板 history append-only 透传到 done 事件 | ✅ | line ~862 / ~983 |
| `check_hard_endings`（free 模式跳过 hard） | ✅ | line ~842 |
| Director `ending_triggered` 兜底（`merge_ai_ending_judgment`） | ✅ | line ~845-846 |
| 玩家行动 `player_actions` append + cap 20（1.B.5） | ✅ | line ~446-455 |
| narrative_arc 每轮重算（含三幕检测，2.A.1） | ✅ | line ~460-468 |

### H. World tick + 模拟

| 能力 | 状态 | 实现 |
|---|---|---|
| `WorldSimulator.tick`（时钟推进 + world_events + environment_changes） | ✅ | line ~350 |
| TickResult.world_events 进 director context | ✅ | line ~362-364 |
| TickResult.updated_state 替换 game_state | ✅ | line ~351 |

### I. 内容审核

| 能力 | 状态 | 实现 |
|---|---|---|
| 输入审核（拒绝 → SSE error 立即 return） | ✅ | `check_input_moderated` line ~319 |
| 输出审核（仅 warn 不阻断） | 🟡 | line ~905-919；阻断会让玩家看到半截内容更糟 |
| moderation slot 异步解析（按 db 拿 router） | ✅ | `_resolve_moderation_router` |

### J. 后置异步任务（不阻塞 SSE done）

| 能力 | 状态 | 实现 |
|---|---|---|
| 触发 `_maybe_compress`（≥20 轮未压缩） | ✅ | line ~952 |
| `_run_compression_with_retry` 最多 2 次 + structured `compressor.run` 日志 | ✅ | line ~171-211 |
| Memory 持久化 + reflection 触发**不在 orchestrator** | — | 由 `game_service._consume_turn` 收 done 后处理 |

### K. SSE 事件输出（向 game_service 流出）

| 事件 type | 时机 | 内部/外发 |
|---|---|---|
| `processing` (phase=directing) | **v1**：director 调用前 | 外发 |
| `processing` (thinking) | **v1**：非早流式且 NPC 调用前 | 外发 |
| `processing` (kind=progress, stage=received/reasoning/npcs_entering/writing) | **v2**（§2.7）：蹭 director 流式真实里程碑 | 外发 |
| `narrative` | prelude(v1) / weave 流式 | 外发 |
| `state_ready` | state 结算后、narrative 流前 | **内部**（`game_service` 消费后 commit） |
| `state_update` | narrator 完结后 | 外发 |
| `ending` | hard ending 或 director 兜底命中 | 外发 |
| `error` | moderation 拒绝 / DirectorParseError | 外发 |
| `done` | 流末——**v2 在正文流完 + core 就绪即发**（不等 case_board 尾巴，§2.7）；含 usage + memory_extracts + dual_memory_entries + history_entries + npc_dialogues | 外发（game_service 再加工） |
| `case_board_update` | **v2**（§2.7）：`done` 之后的 case_board follow-up（仅 script + core 路径） | 外发 |

## 2. 关键能力实现要点

### 2.1 SSE state commit 顺序（state_ready 内部事件）

**问题**：早期实现里，narrator token 一边 yield 一边没 commit state，玩家中途断连后回来 game_state 跟刚看到的内容对不上（线索写到了 UI 但没存 DB）。

**解决**：orchestrator 在 narrator stream **之前**先算好 `new_state`，yield 一个**内部事件** `state_ready{new_state, case_board_history_entries}`。`game_service._consume_turn` 收到这个事件就调 `save_session_state` commit DB（带乐观锁），commit 成功后才开始 yield narrative tokens 给 SSE 客户端。

**实现**：
- orchestrator: `process_action` 在 `apply_state_updates` 之后、`narrator_agent.stream(...)` 之前，line ~858 yield `state_ready`
- game_service: `_consume_turn` 收到 `state_ready` 类型时调 `_commit_turn_state`，更新 `expected_version`，然后**继续**消费同一个 turn_stream（不断流）
- `to_sse_event` 看到 `state_ready` 直接 `raise ValueError`——保证它不会泄漏给前端

**取舍**：拒绝了"先 yield narrative，最后 commit"的简单方案——那个方案早期 SSE 中途断连导致 game_state 跟玩家看到的剧情不一致，是 0.A.4 的根因。

### 2.2 早流式（Phase 1.A.1）

**问题**：玩家发送 action 后要等 Director（最慢，2-5s）→ 所有 NPC（每个 1-3s）→ 才开始看到 Narrator 的第一个字。TTFB 5-10s 是常态。

**解决**：Director 决定 `scene_direction` 后，立刻并行启动两件事：
1. NPC tasks（用 `asyncio.create_task`）
2. Narrator 的 `stream_prelude`（写一段不依赖 NPC dialogue 的氛围开场）

Prelude tokens 直接 yield 给玩家。Prelude 跑完后再 await NPC 队列，最后跑 Narrator 的 `stream`（weave 阶段）织合 scene_direction + npc dialogues 续写后续。`prelude_text` 透传给 weave，避免重复开头。

**实现**：
- 主开关 `settings.narrator_early_stream_enabled`（默认 True）
- 实际触发条件还需 `bool(npc_tasks)`——没 NPC 时直接走单次 weave
- `_merge_usage(weave_usage, prelude_usage)` 合并 token 计数
- prelude 抛异常 fallback 走 weave，不重复（line ~779-780）

**取舍**：用 background task 而不是 streaming gather；`asyncio.create_task` 让 prelude 跟 NPC 真并行，没有等 NPC 第一个 token 才启动的隐藏依赖。

### 2.3 NPC-1 顺序对话（默认模式）

**问题**：早期 NPC 用 `asyncio.gather` 并行——每个 NPC 各自 monologue，互相看不见对方说什么。"赵姐说茶刚泡好"和"王福说今儿话怎么少"是平行宇宙。

**解决**：Director 在 `npc_speech_order` 字段决定本轮真正开口的人和顺序；orchestrator 串行 await；后发言的 NPC 在 system prompt 里看到 `peer_dialogues_so_far`（前面已说的话），可以接话/反驳/装没听见。

**实现**：
- `_run_all_npcs` 顺序分支，line ~694
- 每次 await 之前更新 `kwargs["peer_dialogues_so_far"]`
- 空 dialogue 不累积（NPC prompt 明确"沉默是合法选择"，详见 `npc.md`）
- `npc_max_speakers_per_turn` 默认 3 兜底 trim
- flag `npc_dialogue_sequential_enabled` 关掉退化为并行 gather

**取舍**：拒绝了"全员并行 + 第二轮重 weave"——那需要 LLM 调用翻倍 cost，且 Director 没有"决定谁开口"的杠杆。当前方案让 Director 主导群戏节奏（详见 `npc.md §3.10`）。

### 2.4 单 NPC 失败容错（2.A.3）

**问题**：`asyncio.gather` 默认 fail-fast——任一 NPC 抛错（LLM provider 抽风 / 解析失败）整个 gather 抛，整个 turn 崩溃，玩家看到全屏 error。

**解决**：
- 顺序模式：每次 await 用 try/except，单个 NPC 抛错 fallback `NPCResult(dialogue="", usage=None)` + `logger.warning("npc.run_failed", ...)`，循环继续
- 并行模式：`asyncio.gather(..., return_exceptions=True)` 收所有结果，再用 zip + isinstance(Exception) 替换为 fallback

**实现**：line ~700-734。fallback 的 NPCResult 不会进 `peer_dialogues_so_far`（`if res.dialogue:` 守门）。

**取舍**：拒绝了"重试整个 turn"——一个 NPC 出问题让玩家看不到任何东西更糟。空 dialogue + 警告日志够了，玩家最多看到"赵姐没接话"这种自然降级。

### 2.5 案件板 ops 静默拒绝

**问题**：Director 偶尔会幻觉 `clue_id`（引用不存在的线索），如果硬应用进 case_board，玩家界面出现"幽灵线索"。

**解决**：`apply_case_board_ops` 是纯函数，每条 op 检查引用的 `clue_id` 必须存在于 `discovered_clues`（含同回合 new_clues）。无效 op 抛 `CaseBoardError`，orchestrator 捕获并 `logger.warning("case_board_invalid_ops")`，**当前回合不更新 case_board** 但 turn 不崩。

**实现**：line ~830-839。详见 `case-board.md`。

### 2.6 自由模式章节总结

**问题**：自由模式没有 hard ending，长会话容易"无目的漂流"——玩家不记得自己 30 轮前在干嘛。

**解决**：`should_trigger_stage_summary` 在自由模式 + `last_stage_summary_round` 距今 ≥30 轮 + 有高 urgency NPC intent 或世界冲突时返回 True。这时 orchestrator 给 `scene_direction` 追加一段 `【叙述附加要求】<stage_summary_instruction>`，让 Narrator 在本轮叙事里自然带出阶段总结。

**实现**：line ~849-856 + `engine/orchestrator.py:84-103` 的 `should_trigger_stage_summary` / `build_stage_summary_instruction`。

**取舍**：通过 narrator 自然带出，不增加额外 LLM 调用；缺点是 narrator 可能"硬塞"导致体验割裂——这是个 trade-off。

### 2.7 v2 整轮加载生命周期（2026-05-30）

> 仅 `_process_action_v2`。取代 v1 的 prelude 早流式 + `processing(phase=directing/thinking)` 模板句 + IntermissionAgent 氛围短句（IntermissionAgent 已删除，`intermission` model slot 现为 vestigial）。完整设计见 `docs/plans/play-turn-loading-2026-05.md`。

**问题**：(1) 首包前 ~16–20s 只有一个金点 + 写死套话（"世界正在酝酿…"），生硬、像系统日志、一句后干等。(2) `done` 要等 director **完整**输出才发，但 director 的 `case_board_ops` 占其输出 ~38% 且**最后才吐**——正文 ~32s 流完后，`done` 要等到 ~42s，中间 ~10s 输入框锁着无信号（**done-gap**），玩家以为卡死。

**解决（两件事）**：

1. **思考态进度反馈**：蹭 director 流式真实里程碑发 `processing{kind:"progress", stage}`——`received`（提交即发）/ `reasoning`（director 起跑，带玩家输入摘要）/ `npcs_entering`（`on_partial` 拿到 `active_npcs`，带**真实 NPC 名**）/ `writing`（`scene_direction` 就绪）。后两个由 `_on_partial_director`（跑在 director task 内）推 `asyncio.Queue`，主等待循环 drain 后 yield。零额外 LLM、全真话、每回合不同。前端 `StreamingStatusRail` 渲染成小号 Branch logo + 按 stage 走 next-intl 文案。

2. **done gap 真修**：`_on_partial_director` 在 **`player_action`** key 出现时抓 **core 快照**（`core_tool_input`，剔除 `case_board_ops`）并 set `core_ready`。Phase 3 用该快照经 `DirectorAgent._build_result_v2` 建 core `DirectorResult` → 跑完状态结算 → **正文流完即 yield `done`（解锁输入）**。Phase 4（follow-up）：`await director_task` 拿完整结果 → `apply_case_board_ops` → yield `case_board_update`（带完整 mem_extract bundle），案件板晚一拍刷新。`game_service._commit_case_board_followup` 只更 `game_state.case_board` 字段、不动 `rounds_played`、不覆盖并发后台写（offstage tick / reflection）。

**为什么靠谱（质量保证）**：
- case_board 仍由**同一次 director 调用 / 同一 prompt** 生成——不降级、不二次调用，只是不**阻塞**解锁。
- **`player_action` 是 case_board_ops 之前最后一个 *required* 字段**（schema 顺序：…→`state_updates`→`quick_actions`→`ending_triggered`→`player_action`→（追加在最后的）`case_board_ops`）。它就绪即保证 `state_updates`/`ending_triggered` 已闭合 → **结局判定在解锁前就定了，绝不会"该结局却放人继续"**。
- **fallback（§8）**：无 partial 信号（provider 不流式 / 字段顺序不利）→ 退回 `await` 完整 director_task，case_board inline 应用、不发 follow-up——退回旧时序但**保正确**。free 模式无 case_board → 同样不发 follow-up，mem_extract 仍在 `done`。
- memory 抽取（读 case_board 推理）移到 follow-up，拿得到完整 case_board，质量不降。

**实现**：`_on_partial_director`（里程碑 + `core_ready`/`core_tool_input`）；Phase 3 core 解析 + `case_board_deferred`；Phase 4 `case_board_update`。前端：`StreamingStatusRail` 重写 + `LoadingPulse variant="branch"` + `ChatPanel` AnimatePresence 300ms 淡出 + `stores/game.ts onCaseBoardUpdate`。测试 `tests/test_orchestrator_v2_loading.py`（5 个）。

**实测（活栈一轮）**：done-gap 从 ~10s → **0.04s**；4 个里程碑真实数据按序；`case_board_update` 在 `done` 之后。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/orchestrator.py` | 主流水线（`process_action`）+ 后置压缩（`_run_compression*`）+ 阶段 timing helper |
| `backend/services/game_service.py` | 消费 orchestrator 流（`_consume_turn`）+ DB commit + reflection 后置触发 |
| `backend/api/game.py` | SSE 路由 + `to_sse_event` 序列化 + `_classify_runtime_exception` 错误码归类 |
| `backend/engine/processing_hint.py` | `processing` 事件 payload 构造（phase / focus_npcs / flavor） |
| `backend/engine/director_agent.py` | DirectorAgent + DirectorParseError（详见 director.md） |
| `backend/engine/npc_agent.py` | NPCAgent + NPCResult（详见 npc.md） |
| `backend/engine/narrator_agent.py` | stream / stream_prelude（详见 narrator.md） |
| `backend/engine/world_simulator.py` | tick + TickResult（详见 world-simulator.md） |
| `backend/engine/state_manager.py` | apply_state_updates + GameState（详见 state-and-persistence.md） |
| `backend/engine/case_board.py` | apply_case_board_ops + CaseBoardError（详见 case-board.md） |
| `backend/engine/ending_system.py` | check_hard_endings + merge_ai_ending_judgment + generate_ending_summary |
| `backend/engine/event_system.py` | check_events + apply_event_effects |
| `backend/engine/narrative_arc.py` | NarrativeArcTracker + ArcData + detect_act |
| `backend/engine/compressor.py` | should_compress + build_compression_prompt + token 估计 |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `NARRATOR_EARLY_STREAM_ENABLED` | `true` | 1.A.1 早流式总开关 |
| `NPC_DIALOGUE_SEQUENTIAL_ENABLED` | `true` | NPC-1 顺序对话；False 退化并行 gather |
| `NPC_MAX_CONCURRENCY` | `6` | 并行路径信号量上限 |
| `NPC_MAX_SPEAKERS_PER_TURN` | `3` | 顺序路径发言人 cap |
| `COMPRESSION_THRESHOLD` | `20` | 多少轮未压缩触发 compressor |
| `MAX_CONTEXT_ROUNDS` | `15` | 喂给 LLM 的最近回合数 |

## 5. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_orchestrator.py` | 主流水线 / case_board ops / NPC 全局信息隔离 / ending 事件 / 玩家行动追踪 / NPC 失败容错 / DirectorParseError → llm_parse |
| `tests/test_orchestrator_early_stream.py` | 早流式 prelude + weave 合并 / prelude usage 累加 / flag 关闭路径 |
| `tests/test_orchestrator_npc_slot.py` | NPC 廉价 slot 路由 + fallback |
| `tests/test_orchestrator_timing.py` | 阶段 timing 全 emit + processing/directing 提示 + 无 NPC 时跳过 npc_parallel |
| `tests/test_npc_concurrency_semaphore.py` | 信号量限制并发 peak |
| `tests/test_npc_sequential_dialogue.py` | NPC-1 speech_order / peer_dialogues / max_speakers / coerce 过滤 |
| `tests/test_director_inform_npc.py` | inform_npc_calls 写 director_told memory + 拒绝未知 NPC |
| `tests/test_game_service.py` | _consume_turn 与 state_ready commit 顺序 / 重试 / 乐观锁 |

## 6. 已知短板与未来扩展

### P2

- **prelude 失败 fallback 体验**：当前 prelude 抛错只 warn，weave 会自己开场——会出现 narrative 段感觉"重启了一次"。改进点是 prelude 失败时 yield 一个 placeholder narrative 让 weave 续上去，但工作量不小，等真有玩家投诉再做。
- **stage_summary 阶段单独 emit timing**：自由模式章节总结现在合并在 narrator timing 里，不知道单独耗时；可以加一个独立 stage 标签。
- **后置压缩失败可见性**：`_run_compression_with_retry` 失败后只 warn，玩家完全不知道；如果上下文越来越长导致 LLM 拒绝，需要往前端 emit 提示。

### P3

- **multi-turn rollback**：当前一旦 state commit，玩家无法撤销；做"分支选择"或"存档点"需要把 case_board_history 升级成事件 sourcing 模型。
- **多玩家同局**：所有 schema 都是 user_id × session_id 一对一，多人需要 schema 重设计 + Director 重新设计如何处理多输入。
- **TTFB 进一步压低**：早流式后 TTFB 通常 ~1-2s（Director），再压可能要做"NPC 推测式预热"（已被 NPC-1 替代废弃）或"Director 流式 partial decisions"。
