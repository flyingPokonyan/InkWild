# SSE 协议模块技术说明

> 状态截至 2026-05-08。覆盖 Phase 0 SSE 改造 + Phase 1.A.1 早流式 + Phase 2.A.3 llm_parse 错误码 + Phase 2.B.2 connection_lost 看门狗 + cost guardrail 事件（cost_warning / cap_reached）+ state_ready 内部事件协议落地后的形态。

SSE（Server-Sent Events）协议是 InkWild 游戏流式输出的"皮"——后端 `api/game.py::to_sse_event` 把 orchestrator 内部事件序列化成 wire 格式，前端 `lib/sse.ts` 解析回调到 game store。约定 schema：每条 data 行都是 JSON `{"type": "<name>", "version": 1, ...}`。

它**不直接**做的事：
- 不做事件生成（`engine/orchestrator.py` 各 yield 点）
- 不做心跳实现（sse-starlette 内置的 `:` 注释 ping）
- 不做 admin 创作工坊 SSE（事件 schema 是另一套 progress / warning / result / error / done，见 `frontend/lib/admin-sse-events.ts` 与 `services/generation_task_service.py`）

紧密耦合的上下游：
- 上：`engine/orchestrator.py::process_action`（yield 内部事件流）+ `services/game_service.py::_consume_turn`（消费 + commit + 透传）
- 下：`frontend/lib/sse.ts`（fetch + ReadableStream + watchdog）+ `frontend/stores/game.ts`（onProcessing/onNarrative/... 回调消费）

## 1. 能力矩阵

### A. 事件类型清单（按 to_sse_event 对照）

| type | 时机 | 主要 payload | 是否外发 |
|---|---|---|---|
| `session_created` | `start_game` 第一帧 | `session_id` | ✅ 外发 |
| `processing` | 思考态里程碑（v2，蹭 director 流式）/ Director·NPC 调用前（v1 legacy） | **v2**：`kind:"progress"` + `stage`（received / reasoning / npcs_entering / writing）+ `input_summary?`（玩家输入摘要）+ `npcs?`（真实 active NPC 名）。文案由前端按 `stage` 走 next-intl 拼。**v1 legacy**：`phase`（directing/thinking）/ `focus_npcs[]` / `flavor` | ✅ 外发 |
| `narrative` | narrator weave 流式 token | `text` | ✅ 外发 |
| `state_update` | narrator 完结后、ending 前 | `game_state` / `quick_actions` / `triggered_events` | ✅ 外发 |
| `state_ready` | state 结算后、narrative 流之前 | `new_state` / `case_board_history_entries` | ❌ **内部事件**，外泄会 raise ValueError |
| `ending` | hard ending 命中或 director ending_triggered 兜底 | `ending_type` / `title` / `summary` | ✅ 外发 |
| `error` | moderation 拒绝 / DirectorParseError / 运行时异常 | `code`（字符串枚举）/ `legacy_code`（数字兜底）/ `message` / `retry_after_ms` | ✅ 外发 |
| `cost_warning` | session 成本接近 soft warn | `message` / `suggest` / `total_cost_cents` / `cap_cost_cents` | ✅ 外发 |
| `cap_reached` | session 成本超 hard cap，turn 直接终止 | 同上 | ✅ 外发（前端额外触发 onError(cost_cap)） |
| `done` | 流末——v2 在**正文流完 + core(state_updates/ending) 就绪即发**（解锁输入），不再等 director 的 case_board 尾巴（见 `play-turn-loading-2026-05.md`） | — | ✅ 外发 |
| `case_board_update` | **`done` 之后**的 follow-up（仅 script + 走 core 路径）：director 的 case_board 尾巴在后台跑完后补发，案件板晚一拍刷新 | `game_state`（含更新后的 `case_board`） | ✅ 外发 |

### B. Schema 与版本约定

| 能力 | 状态 | 实现 |
|---|---|---|
| 每条 wire payload 强制带 `version: 1` | ✅ | `to_sse_event` line 125 |
| 前端 schema 校验（version 不匹配抛错） | ✅ | `sse.ts::validateGameSSEPayload` |
| `version` 兼容 `schema_version` 别名 | ✅ | `sse.ts:76` |
| Wire 格式按 SSE spec：`event: <name>\ndata: <json>\n\n` | ✅ | `to_sse_event` 返回 `{"event": ..., "data": json.dumps(...)}` 由 sse-starlette 序列化 |
| `to_sse_event` 显式拒绝 `state_ready`（内部事件不能外发） | ✅ | `api/game.py:122-123` `raise ValueError` |
| 仅声明字段透传（未声明字段 dropped），防止意外泄露内部字段 | ✅ | `to_sse_event` 各分支显式 `if "x" in event` 后赋值 |
| JSON `ensure_ascii=False` 中文不转 unicode 转义 | ✅ | `to_sse_event` 末尾 |

### C. 心跳与连接保活

| 能力 | 状态 | 实现 |
|---|---|---|
| 30s 间隔 SSE 注释心跳（`: ping ...`） | ✅ | `EventSourceResponse(..., ping=SSE_PING_INTERVAL_SECONDS=30)` |
| 注释行 `:` 开头被前端解析忽略，但刷新 `lastDataTimestamp` | ✅ | `sse.ts::processChunk` line 162-166 + `streamAction` 主循环 |
| 90s 全静默看门狗 → emit `connection_lost` 错误 | ✅ | `sse.ts:295-312` `CONNECTION_LOST_THRESHOLD_MS` |
| 看门狗每 10s 检查一次 | ✅ | `CONNECTION_LOST_CHECK_INTERVAL_MS` |
| 连接断开后 `reader.cancel()` 让主循环退出，不自动重连 | ✅ | `sse.ts:307` |
| `connection_lost` 触发后 watchdog 不重复 fire | ✅ | `connectionLostFired` flag |

### D. 错误码体系

| 能力 | 状态 | 实现 |
|---|---|---|
| 字符串枚举：rate_limit / cost_cap / llm_timeout / provider_down / moderation / llm_parse / unknown | ✅ | `api/game.py:38-47` |
| 前端额外加 `connection_lost`（看门狗触发，无后端事件） | ✅ | `sse.ts:19-29` |
| `legacy_code` 数字兜底（AppError 既有数字码继续上报） | ✅ | `to_sse_event` line 162-166 |
| AppError 数字码 → 字符串枚举映射（40001 → moderation, 50001 → provider_down） | ✅ | `_classify_legacy_app_error` |
| 运行时异常分类（TimeoutError → llm_timeout / 类名带 connect/network → provider_down / 兜底 unknown） | ✅ | `_classify_runtime_exception` |
| `retry_after_ms` 字段（rate_limit 用，HTTP 429 Retry-After 头解析） | ✅ | `to_sse_event` line 169-170 + `sse.ts::readRetryAfterMs` |
| 未知字符串 code → unknown（前端） | ✅ | `sse.ts::normalizeSSEErrorCode` |
| HTTP 层 429 之前 SSE stream 不开启时，前端从 `Retry-After` 头构造 SSEError | ✅ | `sse.ts::buildHttpError` |
| `llm_parse` 区别于 `provider_down`（provider 还活，给的输出无法 parse —— UI 提供"重试该回合") | ✅ | orchestrator DirectorParseError 直接 yield `{type: error, code: "llm_parse"}` |

### E. cost guardrail 集成

| 能力 | 状态 | 实现 |
|---|---|---|
| `cost_warning` 独立 type（非 error，不阻断） | ✅ | `to_sse_event` 分支 line 173-181 + `game_service.py:218-225` |
| `cap_reached` 独立 type（turn 直接终止） | ✅ | `game_service.py:208-217` |
| 前端 `onCostWarning` / `onCapReached` 独立回调 | ✅ | `sse.ts::SSECallbacks` |
| `cap_reached` 同时触发 `onError({code: "cost_cap"})` 让通用错误处理统一捕获 | ✅ | `sse.ts:135-141` |
| payload 含 `total_cost_cents` / `cap_cost_cents` 让前端展示精确数字 | ✅ | `costGuardrailPayload` |

### F. 客户端解析与 buffering

| 能力 | 状态 | 实现 |
|---|---|---|
| `fetch` + `ReadableStream` 自实现，不用 `EventSource`（CLAUDE.md 强约束） | ✅ | `sse.ts::streamAction` |
| `\r\n` 归一化为 `\n`，按 `\n\n` 分 block | ✅ | `sse-parser.ts::extractSSEBlocks` |
| 跨 chunk buffer（最后一段 `rest` 留到下次 read） | ✅ | `sse-parser.ts:11-13` |
| 单 block 内多 `data:` 行拼接（用 `\n` join） | ✅ | `sse.ts:171 + 187` |
| `event:` 缺省时 fallback `"message"` | ✅ | `sse.ts:156` |
| 纯注释 block（heartbeat-only）跳过 dispatch | ✅ | `sse.ts:176-179` |
| done 事件之后流提前关闭也走 `onDone` | ✅ | `streamAction` finally + `sawDone` flag |

### G. Admin SSE（仅引用，详见 world-creator 模块）

| 能力 | 状态 | 实现 |
|---|---|---|
| 事件类型：progress / warning / result / error / done | ✅ | `frontend/lib/admin-sse-events.ts::dispatchAdminSseEvent` |
| 不强制 `version` 字段（与 game SSE schema 解耦） | 🟡 | 后续可统一，不紧迫 |
| 30 分钟超时（创作生成任务可能跑很久） | ✅ | `admin-api.ts::ADMIN_STREAM_TIMEOUT_MS` |
| 复用 `extractSSEBlocks` parser | ✅ | `admin-api.ts` import |

详见 `docs/modules/world-creator.md`（待写）的 SSE 章节。本文不展开 admin 事件 schema。

## 2. 关键能力实现要点

### 2.1 state_ready 内部事件（不外发）

**问题**：早期实现里 narrator token 一边 yield 一边没 commit state，玩家中途断连后回来 `game_state` 跟刚看到的内容对不上（线索写到了 UI 但没存 DB）。

**解决**：orchestrator 在 narrator 流之前先算好 `new_state`，**在同一个 generator 流里** yield 一个 `state_ready` 内部事件。`game_service._consume_turn` 截到这个 type 时调 `_commit_turn_state`（带乐观锁的 `save_session_state`），commit 成功后**继续消费**同一个 turn_stream 不断流。`api/game.py::to_sse_event` 看到 `state_ready` 直接 raise ValueError —— 万一编排链 bug 把它流出来，单测和运行期都会立刻炸。

**实现**：
- orchestrator 产出：`engine/orchestrator.py:858-863` —— 在 `apply_state_updates` 之后、`narrator_agent.stream(...)` 之前 yield
- service 拦截：`services/game_service.py:492-503`
- API 拒绝：`api/game.py:122-123`

**取舍**：拒绝了"先 yield narrative，最后 commit"的简单方案——SSE 中途断连时玩家看到的内容跟 DB 不一致，是 0.A.4 的根因。也拒绝了"两个独立 stream"——一个 stream 同时承担"内部协调 + 客户端外发"是 generator 复用的核心好处，加多个 stream 会拆碎事件顺序保证。

### 2.2 错误码二元体系（字符串枚举 + legacy_code）

**问题**：原先 AppError 全是数字码（40001 / 50001 / ...），前端 if/else 一堆数字 magic number；想加新错误类型（rate_limit / llm_timeout）又不想破坏既有 admin 日志查询（按数字 code 过滤）。

**解决**：wire 格式同时携带：
- `code`：字符串枚举（rate_limit / cost_cap / llm_timeout / provider_down / moderation / llm_parse / unknown）—前端业务消费
- `legacy_code`：原始 AppError 数字码 —admin / log / 调试用

`to_sse_event` 接受两种调用形式：传 `{code: "<string>", legacy_code: <int>}`（新代码）或 `{code: <int>}`（旧 AppError 兜底）—自动用 `_classify_legacy_app_error` 转字符串并保留数字。

**实现**：`api/game.py:152-172`。Orchestrator 内部新代码直接 yield 字符串 code（如 DirectorParseError → `code: "llm_parse"`，moderation → `code: 40001`（兼容）→ 自动归 moderation）。

**取舍**：拒绝了"一刀切只用字符串"——所有现有日志查询、admin 报表、AppError 抛错点都得改。二元方案让两套体系并行运行，渐进迁移。

### 2.3 90s 看门狗 vs 30s 心跳

**问题**：长 LLM 调用 wall-time 可能超 1 分钟（特别是创作工坊 agentic 流程套用游戏 SSE）；如果用 EventSource 默认行为（30s 无数据自动重连）会反复重启完全不可接受。同时也要能检测真断网。

**解决**：
- 后端：sse-starlette `ping=30` 每 30 秒发一行 `:` 注释（任何 generator 无 yield 时自动插入），保证有"还活着"的字节流
- 前端：`fetch + ReadableStream` 不依赖 EventSource 的自动重连；记 `lastDataTimestamp`（任何字节都刷新——含心跳）；超过 `CONNECTION_LOST_THRESHOLD_MS=90_000` 触发 `connection_lost` 错误并 cancel reader

**实现**：
- 后端：`api/game.py::SSE_PING_INTERVAL_SECONDS = 30` + `EventSourceResponse(..., ping=...)`
- 前端 watchdog：`sse.ts:295-312`；每 10s 检查一次（`CONNECTION_LOST_CHECK_INTERVAL_MS`）

**取舍**：阈值 90s = 3 倍心跳间隔，给一定容差（瞬时 GC、容器抢占之类）。拒绝了"自动重连"——SSE 流是 stateful 的（绑当前 turn），重连会复制看到的 narrative 段。让用户手动刷新更直观；后续 P2 想做断点续传需要单独设计。

### 2.4 cost guardrail 双 type（warn 不阻断、cap 强终止）

**问题**：单局成本失控时既要"温柔提示玩家可以收尾了"又要"超 hard cap 强行止损"，两件事生命周期完全不同——warn 之后玩家继续玩没问题，cap 后这个 turn 必须停。挤进 `error` type 会让前端无法区分。

**解决**：独立两个 type：
- `cost_warning` 不阻断后续事件流（仍然走完整 turn）
- `cap_reached` 后立刻 yield done 直接终止（不会再有 narrative / state_update）

前端两个独立回调（`onCostWarning` / `onCapReached`）；`cap_reached` 额外触发 `onError({code: "cost_cap"})` 走通用错误 UI 路径。

**实现**：
- 服务端：`services/game_service.py::process_action` line 202-225
- 序列化：`api/game.py::to_sse_event` line 173-181
- 前端：`sse.ts::dispatchEvent` line 132-141

**取舍**：拒绝了"全部用 error type 区分 code"——`cost_warning` 不是错误（玩家没做错任何事，只是算账上来打个招呼），归到 error 在 UI 上视觉污染。两 type 各自语义干净。

### 2.5 :ping 注释行的双重作用

**问题**：注释行（`:` 开头）按 SSE spec 是 keepalive，浏览器 EventSource 默认就 silently 吞掉；自实现 reader 也得跟。但完全 ignore 会丢失"流还活着"的信号——看门狗就废了。

**解决**：把 ":<text>" 行在 `processChunk` 里 continue（不进 dispatch），但**整条 read 操作只要拿到任何字节**（包括注释）就刷 `lastDataTimestamp`——这部分在 `streamAction` 主循环 line 316-320，跟 `processChunk` 解耦。

**实现**：
- 跳过 dispatch：`sse.ts:162-166`
- 刷 timestamp：`sse.ts:316-320`（read loop 里，无关解析）

**取舍**：跟"在 processChunk 里专门检测注释 → 刷 timestamp"等价但更优雅——liveness 信号不应该跟 SSE protocol 解析耦合。任何字节流量都算"还活着"。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/api/game.py` | SSE 路由（start / action / retry / resume / pause）+ `to_sse_event` 序列化 + `to_error_events` 错误兜底 + `_classify_legacy_app_error` / `_classify_runtime_exception` |
| `backend/services/game_service.py` | `_consume_turn` 消费 orchestrator 流 + 拦截 state_ready commit + cost guardrail 触发 |
| `backend/engine/orchestrator.py` | 各 yield 点（process_action 内）+ state_ready 内部事件 |
| `backend/engine/processing_hint.py` | `processing` 事件 payload 构造（phase / focus_npcs / flavor） |
| `backend/middleware/error_handler.py` | `AppError` 数字码定义 + 全局异常 → JSON envelope |
| `frontend/lib/sse.ts` | `streamAction` fetch + ReadableStream + watchdog；`SSECallbacks` 接口；错误码归一化 |
| `frontend/lib/sse-parser.ts` | `extractSSEBlocks` 跨 chunk buffer |
| `frontend/lib/admin-sse-events.ts` | admin SSE 事件 schema（progress/warning/result/error/done） |
| `frontend/lib/admin-api.ts` | `streamAdminEvents` admin 流式调用器（不同的超时和回调） |
| `frontend/stores/game.ts` | game store 消费各 SSE 回调 |

## 4. 配置项

| 环境变量 / 常量 | 值 | 含义 |
|---|---|---|
| `SSE_PING_INTERVAL_SECONDS` | `30` | 后端心跳间隔（秒），sse-starlette 内置注释行 |
| `CONNECTION_LOST_THRESHOLD_MS` | `90_000` | 前端看门狗静默阈值（ms） |
| `CONNECTION_LOST_CHECK_INTERVAL_MS` | `10_000` | 前端看门狗轮询间隔 |
| `EXPECTED_GAME_SSE_SCHEMA_VERSION` | `1` | 前端校验版本号 |
| `ADMIN_STREAM_TIMEOUT_MS` | `30 * 60 * 1000` | admin 创作 SSE 总超时（30 分钟） |
| `GAME_ACTION_RATE_LIMIT_PER_MINUTE` | `30` | 触发 rate_limit 错误的阈值（HTTP 层） |

## 5. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_game_api.py` | start/action/retry/resume SSE 端到端 + AppError → SSE error 转换 + cost guardrail wire |
| `tests/test_game_service.py` | `_consume_turn` 处理 state_ready 提交顺序 + 乐观锁冲突 |
| `tests/test_orchestrator.py` | state_ready yield 时机；error/ending/done 顺序 |
| `tests/test_orchestrator_early_stream.py` | 早流式 narrative 帧顺序（prelude → state_ready → weave） |
| `tests/test_processing_hint.py` | processing 事件 payload 构造（phase / focus_npcs / flavor） |
| 前端 vitest（lib/sse） | extractSSEBlocks 跨 chunk + 注释跳过 + version 校验 |

## 6. 已知短板与未来扩展

### P1

- **断流后无法续传**：当前 `connection_lost` 触发后用户必须刷新整个会话；turn 中途断连 narrative 已发的部分 commit 了 state（state_ready 之后），但前端不会拿回那些已 yield 的 narrative token —— 需要做"按 round_number 拉已写入 messages"作为兜底重建。

### P2

- **`version: 1` 升级路径还没规划**：未来要加新 type 或改 payload 字段时升 version 还是兼容并存？现在是字段透传式的兼容（多了字段前端不会炸），版本机制留着但没真用。
- **admin SSE schema 跟 game SSE 没统一**：admin 走 `progress/warning/result/error/done`，没 `version` 字段；game 走 `processing/narrative/state_update/...` 强制 version。两套 callback 无法复用。优先级低——admin SSE 只有创作工坊一个消费方。
- **stage_summary 自由模式没单独事件**：章节总结现在合并在 narrator 普通 narrative 里，前端无法做"高亮章节标题块"之类的差异渲染。可以加 `narrative_kind` 字段或独立 type，但需求未明。
- **error 后是否一定 done**：`to_error_events` 末尾会自动 yield done，但 orchestrator 内部直接 yield error 后 return 时 done 是被外层包住——单测覆盖不全。

### P3

- **多路复用同一 SSE 连接**：当前一个 turn 一条 stream；想做后台事件（NPC↔NPC 自模拟、定时世界事件）push 给前端需要 keepalive 长连接 + 多路 type，远超当前协议范围。
- **wire 格式从 SSE 升 WebSocket / HTTP/2 push**：SSE 单向、HTTP/1 head-of-line，后续做"玩家发 partial action 边打边推荐"或"双向交互"会卡。
- **客户端断线自动重连**：当前 `connection_lost` 后纯人工刷新；做"自动重发请求带 last_round + last_token_offset"需要 provider 端支持 prefix-cache 和后端 narrative 持久化按 token 粒度——工程量很大。
