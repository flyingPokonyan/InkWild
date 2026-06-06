# 案件板（Case Board）模块技术说明

> 状态截至 2026-05-08。覆盖案件板 5 类型 schema（mystery / emotional / faction / mechanism / horror）+ 增量 ops 操作 + clue_id 锚点校验 + append-only history 全部落地后的形态。仅在 **script 模式** 生效，自由模式完全跳过。

案件板是**剧本模式专属**的玩家辅助工具——把"已发现线索 / 嫌疑人 / 待解疑问 / 关键节点"这些散落在叙事里的信息结构化展示，让玩家不必自己记笔记。它的形态完全由剧本的 `script_type` 决定（推理 / 情感 / 阵营 / 机制 / 恐怖 5 种各自一套字段）。

它**不直接**做的事：
- 不做 LLM 调用（Director 在自己的 turn 输出 `case_board_ops`，案件板只是把 ops 应用到现有快照）
- 不做 DB 写（commit 由 [`./state-and-persistence.md`](./state-and-persistence.md) 的 `_commit_turn_state` 在事务内 append history）
- **NPC 看不到案件板**——这是玩家工具，详见 [`./npc.md`](./npc.md) §4 信息隔离表

紧密耦合的上下游：
- 上：`engine/director_agent.py`（Director 输出 `case_board_ops`）
- 中：`engine/case_board.py::apply_case_board_ops`（纯函数应用）
- 下：`game_state.case_board`（current 快照 in `GameState.case_board`）+ `case_board_history` 表（append-only 操作历史）+ `GET /api/game/{sid}/case-board` 路由

## 1. 能力矩阵

### A. ops 协议

| 能力 | 状态 | 实现 |
|---|---|---|
| 三类 op：`set_field` / `upsert_list_item` / `remove_list_item` | ✅ | `schemas/case_board.py::CaseBoardOp.op_type` Literal |
| `path: list[str]` 锚定操作目标（如 `["current_objective"]`、`["suspects"]`） | ✅ | `case_board.py::_resolve_parent_dict` |
| `match: dict` 列表项匹配条件（list ops 必填） | ✅ | `_apply_upsert_list_item` / `_apply_remove_list_item` |
| `value: JSON` 写入新值 | ✅ | set_field 任意 JSON；upsert_list_item 必须 dict |
| `reason: str | None` 记录原因（写入 history） | ✅ | 透传 history `reason` 列 |
| Pydantic 校验（path 非空、value/match JSON-like、list ops 必须有 match） | ✅ | `CaseBoardOp.validate_*` |
| nested path 解析（如 `["evidence"]` 下找列表，再 match clue_id） | ✅ | `_resolve_list_target` |
| upsert：列表项命中 match → update；不命中 → append | ✅ | `_apply_upsert_list_item` 双路径 |
| remove：命中 match → del；不命中 → no-op（不报错） | ✅ | `_apply_remove_list_item` |

### B. clue_id 锚点校验（防止 Director 幻觉）

| 能力 | 状态 | 实现 |
|---|---|---|
| 所有 op 的 `match` 和 `value` 中 `clue_id` 字段必须存在于 `discovered_clues` | ✅ | `_validate_clue_refs` + `_iter_clue_ids` |
| 同回合 new_clues 也算有效（先 apply state_updates 再 apply ops） | ✅ | orchestrator 顺序：state → events → case_board ops |
| 嵌套 dict / list 内的 clue_id 都会扫到 | ✅ | `_iter_clue_ids` 递归 |
| 校验失败抛 `InvalidClueRefError`（继承 CaseBoardError） | ✅ | 上层捕获后丢弃整批 ops |
| 非字符串 clue_id 也报错 | ✅ | `"clue_id must be a string"` |

### C. 类型 schema（script_type 驱动）

| script_type | 字段（除 common 3 个外） | Director 输出指引 |
|---|---|---|
| `mystery`（推理） | `suspects[]` / `evidence[]` | 每发现新线索更新 evidence + 更新嫌疑人 suspicion_level |
| `emotional`（情感） | `relationships[]` / `memory_fragments[]` / `emotional_threads[]` | 深度互动后更新 depth + 触发回忆解锁 memory_fragments |
| `faction`（阵营） | `faction_guesses[]` / `alliances[]` / `betrayal_signals[]` | 观察可疑行为更新 confidence + 记录背叛信号 |
| `mechanism`（机制） | `active_tasks[]` / `resources` / `rules_revealed[]` | 任务状态变化 + 新规则发现 |
| `horror`（恐怖） | `threat_level` / `escape_progress` / `safe_zones[]` / `anomalies[]` | 危险事件调整 threat_level + 推进 escape_progress |
| Common 三字段 | `current_objective` / `key_questions[]` / `progress_phase` | 所有 script_type 必填 |
| schema 注入 Director tool | ✅ | `prompts.build_director_tool(script_type)` 动态扩 input_schema.case_board_ops |
| schema 注入 Director system prompt | ✅ | `case_board_prompts.build_case_board_prompt_rules(script_type)` |
| 未知 script_type | 🟡 | `_TYPE_SCHEMAS.get(...) → {}` 静默退化为只有 common 三字段 |

### D. apply_case_board_ops（纯函数）

| 能力 | 状态 | 实现 |
|---|---|---|
| 输入：`(game_state: dict, current_board: dict | None, ops: list)` | ✅ | `case_board.py:21-25` |
| 输出：`(new_board: dict, history_entries: list[dict])` | ✅ | tuple 返回，无 side effect |
| **不修改入参**（深拷贝 current_board） | ✅ | `deepcopy(current_board)` |
| 单条 op 失败抛 CaseBoardError → 整批 ops 全丢（不部分应用） | ✅ | 异常前推，调用方 try 整体 |
| current_board 非 dict 抛 InvalidCaseBoardOpError | ✅ | 防 game_state 损坏 |
| dict op input 自动 Pydantic 校验（`_coerce_op`） | ✅ | 兼容 Director 直接给 dict |

### E. case_board_history 表（append-only）

| 能力 | 状态 | 实现 |
|---|---|---|
| 每条 op 一行 history（含 before/after） | ✅ | `apply_case_board_ops` 返回 history_entries 列表 |
| `op_type / path / payload / before / after / reason / round_number` 列 | ✅ | `models/case_board_history.py` |
| 写入时机：`_commit_turn_state` 事务内（跟 game_state commit 原子） | ✅ | `game_service.py:642-648` |
| done 事件兜底写入（emit_state_ready=False / v2 fallback 路径） | ✅ | `game_service.py` done 分支 |
| **v2 case_board follow-up**（2026-05-30）：core 路径下 case_board 不阻塞 `done`，由其后的 `case_board_update` 事件补发——`_commit_case_board_followup` 只更 `case_board` 字段 + append history（不动 rounds_played、不覆盖并发后台写） | ✅ | `game_service._commit_case_board_followup`；见 `../plans/play-turn-loading-2026-05.md` |
| 永不删（append-only） | ✅ | 没 delete 路径 |
| 索引 `(session_id)` + `(session_id, id)` 优化时序 query | ✅ | `Index` |
| **不去重**（同一 op 重复执行会写两条） | ✅ | by design — 玩家想看到完整时间线 |

### F. 跟 Director 的协作

| 能力 | 状态 | 实现 |
|---|---|---|
| Director tool input_schema 仅在 `script` 模式 + 非空 script_type 时加 `case_board_ops` 字段 | ✅ | `prompts.build_director_tool` |
| Director system prompt 加段「## 案件面板更新规则」（按 script_type 5 套文案） | ✅ | `case_board_prompts._TYPE_PROMPT_RULES` |
| Director system prompt 强调："只能通过 case_board_ops 更新案件面板，不要输出整份 case_board 快照" | ✅ | `prompts.py:372` |
| DirectorResult.case_board_ops（list[dict] default []） | ✅ | `director_agent.py:42` + `_coerce_case_board_ops` |
| Director 失败 / 没输出 ops → 案件板沿用上回合 | ✅ | empty list 路径 |

### G. 错误容忍

| 能力 | 状态 | 实现 |
|---|---|---|
| CaseBoardError 静默拒绝（不致命 turn） | ✅ | `orchestrator.py:838-839` warn + 继续 |
| 失败时**整批 ops 全丢**，不部分应用 | ✅ | `apply_case_board_ops` 异常向上抛，调用方丢整体 |
| 失败原因记 structlog `case_board_invalid_ops` | ✅ | `logger.warning("case_board_invalid_ops", error=str(exc))` |
| 失败时 history 也不写（保证 history 一致性） | ✅ | history 列表只在 op 成功时 append |
| 玩家完全无感（看不到 error toast） | ✅ | 没 SSE error 事件 |

### H. API 接口（GET /api/game/{sid}/case-board）

| 能力 | 状态 | 实现 |
|---|---|---|
| 返回 `{current: dict, history: list[CaseBoardHistoryItem]}` | ✅ | `schemas/game.py::CaseBoardResponse` |
| current = `game_state.case_board`（最新快照） | ✅ | `api/game.py:351` |
| history 按 `id ASC` 时序排序 | ✅ | `order_by(CaseBoardHistory.id.asc())` |
| 仅 session 所有者可读（`get_current_user` ownership 检查） | ✅ | `api/game.py:326-328` |
| 不存在 session → 40003 | ✅ | AppError 翻译 |
| **无写入接口** — 案件板只能由 Director ops 改 | ✅ | by design，玩家不能直接编辑 |

### I. 模式隔离

| 能力 | 状态 | 实现 |
|---|---|---|
| 自由模式跳过整个 case_board 路径 | ✅ | `orchestrator.py:830` `if director_result.case_board_ops and game_mode == "script"` |
| 自由模式 Director tool 不含 case_board_ops 字段 | ✅ | `build_director_tool` `if game_mode == "script"` |
| 自由模式 system prompt 不加「案件面板规则」段 | ✅ | `prompts.py:365` `if game_mode == "script"` |
| 自由模式 GET /case-board 返回 `current={}` + 空 history（仍然能查） | 🟡 | 不报错但永远空，UI 应该不展示该 tab |

## 2. 关键能力实现要点

### 2.1 增量 ops 而非全量快照

**问题**：早期想让 Director 每轮输出**完整** case_board JSON。试下来三个问题：(1) Director 经常**漏写**——本轮没动到的 evidence 项整列被它默认抹掉；(2) token 成本随案件板增长线性涨；(3) 没法做 history（只有快照丢丢丢）。

**解决**：换成增量 ops——Director 只输出"本轮**变化**的部分"，每条 op 是一个 `{op_type, path, match?, value?, reason?}` 结构。三种 op 覆盖所有可能：覆盖某个标量字段（set_field）、列表 upsert、列表 remove。`apply_case_board_ops` 把 ops 串行应用到上回合快照得新快照。

**实现**：
- `engine/case_board.py` 全文，纯函数 + 深拷贝
- `schemas/case_board.py::CaseBoardOp` Pydantic 校验
- `prompts.py:212-252` Director tool input_schema 注入

**取舍**：增量 ops 复杂度比快照高（要解析 path、要校验引用），但换来 (a) Director prompt 引导更聚焦"本轮变化"，(b) history 自然有了 before/after，(c) token 省了 ~50%（一条 op 平均 30-80 tokens 而不是整份 JSON 几百 tokens）。

### 2.2 clue_id 锚点严格校验

**问题**：Director 偶尔幻觉 `clue_id`——引用 `clue_999` 但 `discovered_clues` 里只有 `clue_001..clue_007`。如果硬应用进 case_board，玩家界面出现"幽灵线索 ID"，前端尝试 cross-reference 时找不到原文。

**解决**：`_validate_clue_refs` 在每条 op 应用前递归扫 `match` 和 `value`，所有以 `clue_id` 为 key 的字段必须 ∈ 当前 `discovered_clues`。锚点合法范围包含**同回合刚生成的 new_clues**——orchestrator 顺序是先 `apply_state_updates`（写入 new_clues）再 `apply_case_board_ops`，所以 Director 当回合发现的线索可以立刻被引用。

**实现**：
- `case_board.py:69-99`：`_discovered_clue_ids` + `_validate_clue_refs` + `_iter_clue_ids` 递归
- 失败抛 `InvalidClueRefError`（CaseBoardError 子类）
- orchestrator 捕获后整批丢弃，warn 日志

**取舍**：拒绝了"宽松模式（保留未知 clue_id）"——一旦数据不一致就难以收回。严格校验 + 整批丢弃（不部分应用）让"案件板永远跟 discovered_clues 对得上"成为强不变量。代价是 Director 偶尔幻觉一次会丢掉同 turn 所有真实 ops；这是可接受的，下一轮 Director 会重试。

### 2.3 case_board_history append-only

**问题**：玩家在长 session 里想知道"这条嫌疑判断是哪轮加的、之前是什么样"。如果只存最新快照，回顾完全不可能。

**解决**：`apply_case_board_ops` 返回值是 `(new_board, history_entries)`，每条 op 的 before/after 都打包成一个 `CaseBoardHistoryEntry` dict。`game_service._commit_turn_state` 在 commit game_state 的**同一事务**里把这些 history 写入 `case_board_history` 表，保证"快照变了 ↔ history 多一行"原子一致。

**实现**：
- `case_board.py:46-55`：每条 op 完成后 append CaseBoardHistoryEntry
- `models/case_board_history.py`：表结构 + index
- `game_service.py:642-648`：`_add_case_board_history_entries`，事务内 add row
- `game_service.py:524-531`：done 兜底路径（仅在 emit_state_ready=False 流程，目前没用）
- `api/game.py:330-349`：GET 路由按 id ASC 拉全量

**取舍**：没做"history 折叠 / 压缩"——长 session 可能 history 几百行。但单条 row 体积小（before/after 通常是单条 evidence/suspect 子对象），暂未到优化阈值。需要时可以加 `is_archived` 列做软删。

### 2.4 错误静默拒绝（不致命）

**问题**：案件板毕竟是辅助工具——它出错不应该让玩家看不到 narrative。早期把 CaseBoardError 当成 fatal turn error，玩家某轮 Director 幻觉了一个 clue_id，整个 turn 红 toast 报错，体验完全崩坏。

**解决**：orchestrator 把 `apply_case_board_ops` 包在 try/except 里，捕获 `CaseBoardError` → `logger.warning("case_board_invalid_ops")`，**当前回合不更新 case_board** 但继续走完 turn。玩家看到的 narrative / state_update / 等正常事件没有任何变化，只是案件板"这一轮没动"。

**实现**：`orchestrator.py:830-839`。

**取舍**：拒绝了"暴露给用户 + 提示重试"——案件板不像主线 narrative，可以"下一轮 Director 自己修正"。代价是玩家看不到失败原因，需要从 structlog 排查；这交给开发者用 `case_board_invalid_ops` 日志关键字查。

### 2.5 仅 script 模式生效

**问题**：自由模式没有"剧本核心问题 / 嫌疑人 / 已知线索"这种结构化谜题——给玩家强行展示一个空案件板既混淆又无用。

**解决**：三处 `if game_mode == "script"` 互锁：(1) Director tool input_schema 不加 case_board_ops 字段，(2) Director system prompt 不加更新规则段，(3) orchestrator 应用 ops 前再 check 一次。任意一处失守对其他两处也无害——Director 不会输出 ops、orchestrator 也会跳过。

**实现**：
- `prompts.py:213` `build_director_tool(script_type, game_mode)` 函数签名带 game_mode
- `prompts.py:365-373` system prompt 段 conditional
- `orchestrator.py:830` apply 前再 check

**取舍**：三层 check 略冗余但廉价。一旦未来想让自由模式也有某种轻量"目标板"，三处都改即可——没耦合到深处。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/case_board.py` | apply_case_board_ops 纯函数 + CaseBoardError 等异常类 |
| `backend/engine/case_board_prompts.py` | 5 类型 schema 片段 + Director prompt 文案 |
| `backend/schemas/case_board.py` | CaseBoardOp / CaseBoardHistoryEntry Pydantic 模型 |
| `backend/schemas/game.py` | CaseBoardResponse / CaseBoardHistoryItem（API 响应） |
| `backend/models/case_board_history.py` | case_board_history 表 ORM |
| `backend/engine/prompts.py` | `build_director_tool(script_type, game_mode)` 注入 case_board_ops |
| `backend/engine/director_agent.py` | DirectorResult.case_board_ops + `_coerce_case_board_ops` |
| `backend/engine/orchestrator.py:830-839` | apply ops + history 累积 + 异常静默 |
| `backend/services/game_service.py::_add_case_board_history_entries` | 事务内 append history |
| `backend/api/game.py::get_case_board` | GET /api/game/{sid}/case-board 路由 |

## 4. 数据库 schema

```sql
case_board_history (
  id INT PRIMARY KEY AUTOINCREMENT,
  session_id UUID FK game_sessions.id NOT NULL,
  round_number INT NOT NULL,             -- 这条 op 发生在第几回合
  op_type VARCHAR(50) NOT NULL,          -- set_field | upsert_list_item | remove_list_item
  path JSON NOT NULL,                    -- list[str]
  payload JSON NOT NULL,                 -- {match, value}
  before JSON,                           -- 操作前的目标值
  after JSON,                            -- 操作后的目标值
  reason TEXT,                           -- Director 给的原因
  created_at
)
INDEX (session_id), (session_id, id)

-- current 快照不在独立表，存在 game_sessions.game_state.case_board 字段
-- （详见 state-and-persistence.md）
```

## 5. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_case_board.py` | apply_case_board_ops 三种 op / 嵌套 path / clue_id 锚点 / history 累积 |
| `tests/test_case_board_prompts.py` | 5 种 script_type schema 合并 + prompt 文案 |
| `tests/test_orchestrator.py` | case_board ops 应用路径 + CaseBoardError 静默 + script-only 隔离 |
| `tests/test_game_service.py` | _add_case_board_history_entries 事务内 commit + done 兜底路径 |
| `tests/test_game.py`（部分） | GET /api/game/{sid}/case-board 路由 ownership + 历史时序 |

## 6. 已知短板与未来扩展

### P2

- **history 折叠 / 压缩**：长 session 的 case_board_history 可能几百行，前端加载时序时一次性拉全量。当前还没出过性能问题，但 P2 应该考虑分页或客户端按 round_number 过滤。
- **case_board 时序回放**：history 已经有 before/after，理论上可以做"按 round 回退"或"动画播放整个推理过程"，前端目前只用 current，浪费了已经写好的数据。
- **未知 script_type 静默退化**：当前 `_TYPE_SCHEMAS.get(...) → {}` 退化为只有 common 三字段，case_board 仍可工作但内容贫瘠。如果将来工坊允许自定义 script_type，应该 fail-fast 而不是静默。

### P3

- **玩家手动编辑案件板**：当前案件板只能由 Director ops 改。玩家想自己手写"我怀疑 X"做不到。要做需要新接口 + 一套"玩家 op vs Director op"的优先级规则——不轻量，等真有需求再开。
- **跨 session 案件板模板**：同一玩家玩第二轮同一剧本，case_board 完全重新开始；理论上可以参考第一轮的 history 给出"上次到这步发现了 X"的提示。
- **自由模式的"目标板"轻量版**：自由模式没结构化谜题，但玩家也想看自己的探索进度。一个简化版"current_objective + key_questions"的目标板可以共用 case_board 表 + 简化 schema。
