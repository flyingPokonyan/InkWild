# 状态与持久化模块技术说明

> 状态截至 2026-05-08。覆盖 GameState 全字段 + apply_state_updates + 乐观锁 + state_ready commit 顺序 + SessionLock 落地后的形态。

`engine/state_manager.py` 是世界引擎的状态 single source of truth：定义 `GameState` dataclass、`apply_state_updates` 纯函数、以及带乐观锁的 `save_session_state`。它本身**不做业务规则**——只负责"接收 director 解析出的 updates，深拷贝 + 应用 + 推进若干计数器，然后让上层异步 commit"。

它**不直接**做的事：
- 不做 LLM 调用
- 不做 case_board / event / ending / narrative_arc 字段语义（那些字段它持有，但写入逻辑各自归 [`./case-board.md`](./case-board.md) / [`./world-simulator.md`](./world-simulator.md) / `engine/narrative_arc.py`）
- 不做 SSE 序列化
- 不做并发互斥（互斥归 `services/session_lock.py` 的 Redis 分布式锁）

紧密耦合的上下游：
- 上：`engine/orchestrator.py` 调 `apply_state_updates` + 在 narrator stream 之前 yield `state_ready`
- 上：`services/game_service.py::_consume_turn` 消费 `state_ready` → 调 `_commit_turn_state` → 调 `save_session_state`
- 下：`models/game.py::GameSession` 的 `game_state JSON` + `version` 列

## 1. 能力矩阵

### A. GameState 字段（"状态里都装了什么"）

| 字段 | 状态 | 说明 / 实现 |
|---|---|---|
| `current_time` / `time_index` | ✅ | "第N天·上午"；time_index 是单调推进整数，TIME_SLOTS 5 槽 |
| `current_location` / `visited_locations` | ✅ | 玩家当前位置 + 去过的所有地点（dedup append） |
| `player_inventory` | ✅ | list[str]，apply_state_updates 处理 add/remove |
| `discovered_clues` | ✅ | `list[{id, content, found_at}]`，id 形如 `clue_001` 自动累加 |
| `npc_relations` | ✅ | `dict[npc_name, {trust, mood, last_interaction}]`；trust 硬限 [0, 10] |
| `triggered_events` | ✅ | event 名/id 数组，去重防重触发 |
| `round_number` / `rounds_since_last_clue` | ✅ | 每次 `apply_state_updates` 自增 round_number |
| `last_stage_summary_round` | ✅ | 自由模式章节总结锚点 |
| `npc_intents` | ✅ | 由 [`./intent-system.md`](./intent-system.md) 维护 |
| `info_items` | ✅ | 由 `info_propagation` 维护 |
| `npc_locations` | ✅ | 由 `world_clock` 维护 |
| `narrative_arc` | ✅ | 由 `engine/narrative_arc.py` 维护（三幕） |
| `world_conflicts` | ✅ | 自由模式 `init_npc_intents` 灌入；后续不变 |
| `flags` | ✅ | 给 intent_system / event 等子模块当 KV 黑板 |
| `last_compressed_round` | ✅ | compressor 用，0 = 从未压缩 |
| `case_board` | ✅ | 由 [`./case-board.md`](./case-board.md) 维护（仅 script 模式） |
| `player_actions` | ✅ | 1.B.5 — typed action 历史，cap 20 (`PLAYER_ACTIONS_HISTORY_LIMIT`) |

### B. apply_state_updates 行为（director.state_updates → state diff）

| 更新键 | 行为 | 实现位置 |
|---|---|---|
| `location` | 改 current_location + 自动 append 到 visited_locations（dedup） | `state_manager.py:93-96` |
| `time_advance` | true 触发 `_advance_time`：time_index +1，重算 "第N天·X" | `state_manager.py:98-99` + `_advance_time` |
| `new_clues: list[str]` | 自动分配 `clue_001` 递增 id + found_at 时间戳 | `state_manager.py:101-110` |
| `npc_updates: {npc: {trust_change, mood}}` | trust 硬限 [0, 10]；不存在的 NPC 自动创建 default 关系 | `state_manager.py:112-119` |
| `inventory_changes: {add, remove}` | dedup add；safe remove（不存在不报错） | `state_manager.py:121-127` |
| 自动 round_number += 1 | ✅ | 每次调用都推进 |
| 自动 rounds_since_last_clue 推进 | ✅ | 有 new_clues 归零，否则 +1 |
| **深拷贝 vs 就地修改** | ✅ 深拷贝 | `copy.deepcopy(state)`，原始 state 不变 |
| **不写 DB** | ✅ | 纯函数，commit 由调用方负责 |

### C. 乐观锁 / 并发安全

| 能力 | 状态 | 实现 |
|---|---|---|
| `version` 列（int，default 0） | ✅ | `models/game.py::GameSession.version` |
| `save_session_state(expected_version=...)` 原子 update | ✅ | `state_manager.py:139-168` 用 `WHERE id=:sid AND version=:expected` |
| 版本不匹配抛 `StaleVersionError` | ✅ | rowcount != 1 → raise |
| 上层翻译为 AppError(40901) HTTP 409 | ✅ | `game_service.py:352`、`game_service.py:640` |
| 同一 session 内串行（同 process） | ✅ | Redis `SessionLock` 锁住 `lock:session:{sid}` |
| 跨 process / pod 串行 | ✅ | 同上（Redis 全局） |
| 锁 TTL（避免 worker 崩了死锁） | ✅ | `settings.session_lock_timeout` |
| `nx=True` set 模式（防覆盖别人的锁） | ✅ | `session_lock.py:13-17` |
| 前端自动重试 409 | ❌ | 当前没有自动重试；UI 需要靠用户重试 |

### D. state_ready commit 协议（SSE → DB 串行）

| 能力 | 状态 | 实现 |
|---|---|---|
| Orchestrator 在 narrator stream **之前** yield `state_ready` 内部事件 | ✅ | `orchestrator.py:858-863` |
| game_service 收到 `state_ready` 立即 `_commit_turn_state` | ✅ | `game_service.py:492-503` |
| commit 失败抛 StaleVersion 不开始流 narrative | ✅ | 异常向上抛、SSE 转 error |
| commit 成功后才开始 yield 给 SSE 客户端 narrative tokens | ✅ | 内部事件不外泄 |
| `state_ready` 不会被 `to_sse_event` 序列化（防泄漏） | ✅ | `api/game.py::to_sse_event` 显式拒绝 |
| `done` 事件兜底 commit（`emit_state_ready=False` 路径） | ✅ | `game_service.py:514-523` |
| commit 时同步写入 case_board_history（事务内） | ✅ | `_commit_turn_state` 调 `_add_case_board_history_entries` |

### E. 持久化映射（GameState ↔ DB 列）

| GameState 字段 | DB 落点 | 协议 |
|---|---|---|
| 全部 18 个字段 | `game_sessions.game_state JSON` | 通过 `GameState.to_dict()` |
| 反序列化 | `GameState.from_dict(data)` | 用 `__dataclass_fields__` 过滤未知 key（前向兼容） |
| `round_number` | 同时写到 `game_sessions.rounds_played`（rounds_mode=increment/set_one） | `_commit_turn_state` 计算 |
| `last_played_at` | 每次 commit 自动更新 | `extra_values` |
| `version` | 由 SQL `version + 1` 原子 +1 | 不存在 dataclass 里 |
| `state_snapshot`（rollback 用） | `game_sessions.state_snapshot` | `process_action` 入口前快照，retry 用 |

### F. player_actions 历史（1.B.5）

| 能力 | 状态 | 实现 |
|---|---|---|
| 每轮 Director 输出 typed `player_action` | ✅ | `DirectorResult.player_action` |
| 进 GameState.player_actions 列表 | ✅ | `orchestrator.py:446-455` |
| 带 round 戳 | ✅ | `entry = {"round": round_number, **action}` |
| **cap 20** 防膨胀 | ✅ | `PLAYER_ACTIONS_HISTORY_LIMIT=20` slice 末尾 |
| 透传给每个 NPC system prompt（recent_player_actions） | ✅ | `orchestrator.py:654` |
| Director 没分类时跳过（不强插空 entry） | ✅ | `if director_result.player_action is not None` |

### G. to_dict / from_dict 协议

| 能力 | 状态 | 备注 |
|---|---|---|
| 显式 18 字段 to_dict（不依赖 dataclasses.asdict） | ✅ | 字段加减必须改两处，强制有意识演进 |
| from_dict 用 `__dataclass_fields__` 过滤 | ✅ | DB 里旧版本多余 key 不会报错 |
| nullable / default 字段都有 default_factory | ✅ | 旧 session JSON 没新字段时 from_dict 不爆 |
| 没有 schema migration 机制 | 🟡 | 单纯靠 default 兜底；字段语义破坏性变更需手写迁移 |

## 2. 关键能力实现要点

### 2.1 乐观锁 + state_ready commit 顺序

**问题**：早期 narrator 一边 yield token 一边没 commit，玩家中途断连后回来 game_state 跟刚看到的剧情对不上（narrative 提到"线索 A"但 DB 没存）。同时多端打开同一 session 会产生覆盖写。

**解决**：两层防御。
1. **commit-before-stream**：orchestrator 在 narrator stream **之前**算好 `new_state`，yield 一个内部事件 `state_ready{new_state, case_board_history_entries}`。`game_service._consume_turn` 收到立刻 `_commit_turn_state`，commit 成功才放后续 narrative tokens 进 SSE 链路。
2. **乐观锁**：`save_session_state` 用 `UPDATE game_sessions SET version=version+1, game_state=:s WHERE id=:sid AND version=:expected_version`。rowcount != 1 抛 `StaleVersionError`，上层翻译成 HTTP 409 / SSE error code 40901。

**实现**：
- `state_manager.py:139-168` save_session_state
- `orchestrator.py:858` state_ready yield
- `game_service.py:492-503` 收到事件 → `_commit_turn_state`
- `game_service.py:609-652` `_commit_turn_state` 包装 + StaleVersion 兜底 + case_board_history append

**取舍**：拒绝了"先 yield narrative，最后 commit"——那个方案下 SSE 中途断连导致 game_state 跟玩家看到的剧情不一致。代价是 narrative TTFB 多等一次 DB roundtrip（~10ms），相对 LLM 时间忽略不计。

### 2.2 SessionLock（Redis 分布式锁）

**问题**：玩家在两个浏览器同时点 action / retry / resume，三个 SSE 流并发跑同一 session 的 orchestrator，会产生交叉写 + 状态错乱。乐观锁能防覆盖但浪费一次完整 LLM turn，体验差。

**解决**：在 `/action` / `/retry` / `/resume` 三个会改 session 状态的入口前，用 Redis `SET lock:session:{sid} 1 NX EX <ttl>` 抢锁。抢不到直接 HTTP 429 + 中文文案"请等待上一轮回复完成"。锁 TTL = `settings.session_lock_timeout`（默认 60s 量级），防止 worker 崩了死锁。

**实现**：
- `services/session_lock.py` — 极简 acquire/release
- `api/game.py:238-281` 三个写接口都加锁；finally 块里 release
- 读接口（`/state` / `/case-board` / `/detail`）**不加锁**——只读乐观，靠最新 commit 的 game_state

**取舍**：乐观锁只是兜底。前置 SessionLock 是体感更好的"快速失败"，避免玩家看完一长段 narrative 才发现这次写被 reject。两层防御互补。

### 2.3 player_actions cap 20

**问题**：长会话玩家可能有几百轮行动，全塞进 game_state JSON 会让每次读写 DB 的 row 越来越大、NPC prompt 越来越长。

**解决**：1.B.5 引入 `PLAYER_ACTIONS_HISTORY_LIMIT=20`，每轮 append 后 slice 末尾 20 条。NPC system prompt 实际只渲染最近 5-8 条（参见 [`./intent-system.md`](./intent-system.md) 跟 NPC 模块），多出来的 12-15 条留作分析 / 未来 NPC reflection 输入。

**实现**：`orchestrator.py:451-455`。Director 没分类（`player_action is None`）时不强插空 entry。

**取舍**：拒绝了"按时间窗口"或"按重要度"裁剪。20 条固定上限可观测、可回放、JSON 大小有界。如果未来某模块需要更长历史，应单独建表 `player_actions(session_id, round, ...)` 而不是再扩 game_state。

### 2.4 from_dict 前向兼容

**问题**：每次 GameState 加新字段（比如 1.B.5 加 `player_actions`、case_board 等），DB 里已经有大量旧 session JSON 不含新 key，直接 `cls(**data)` 会因 unknown kwarg 报错；反过来如果删字段，新代码 `**old_data` 会因多余 key 报错。

**解决**：`from_dict` 用 `{k: v for k, v in data.items() if k in cls.__dataclass_fields__}` 过滤——已知字段从 JSON 取，未知字段直接丢；缺失字段由 `default_factory` 补。新增字段不需要 migration，删字段也只是 JSON 里有死键。

**实现**：`state_manager.py:78-80`。

**取舍**：放弃了显式 schema migration——好处是迭代快，代价是字段**语义**破坏性变更（比如 trust 从 [0,10] 改成 [-10,10]）必须手写迁移脚本，光改 dataclass 不够。这层风险靠 code review 把关。

### 2.5 to_dict 显式列字段

**问题**：用 `dataclasses.asdict` 自动序列化看似省代码，但加字段时容易漏写——dataclass 加了字段但持久化层没意识到，写进 DB 后下轮读不出来。

**解决**：`to_dict` 显式列出 18 个字段。新增字段必须改两处（dataclass + to_dict），编译/测试时立刻暴露。配 `from_dict` 的容错过滤，整体形成"显式持久化、容错反序列化"的不对称防线。

**取舍**：略冗余的样板代码 vs 静默丢字段的运行时 bug——选了前者。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/state_manager.py` | GameState dataclass、apply_state_updates、save_session_state、StaleVersionError |
| `backend/services/session_lock.py` | Redis 分布式锁 acquire/release |
| `backend/services/game_service.py` | `_consume_turn` / `_commit_turn_state` / `_add_case_board_history_entries` |
| `backend/api/game.py` | 三个写接口的 SessionLock + StaleVersion → 40901 转换 |
| `backend/models/game.py` | GameSession.version + game_state JSON 列 |
| `backend/engine/orchestrator.py` | yield `state_ready` 触发 commit；player_actions append + cap |

## 4. 配置项

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `SESSION_LOCK_TIMEOUT` | 由 `settings` 控制 | Redis 锁 TTL（秒），超时自动释放防死锁 |
| `MAX_CONTEXT_ROUNDS` | `15` | 进 LLM 上下文的最近 message 数（影响 process_action 起点） |

`PLAYER_ACTIONS_HISTORY_LIMIT = 20` 在 `state_manager.py:17` 是模块常量，不暴露 env。

## 5. 数据库 schema

```sql
game_sessions (
  id UUID PRIMARY KEY,
  user_id, world_id, character_id, script_id,
  authors_note TEXT,
  state_snapshot JSON,            -- retry 用，process_action 入口前快照
  last_action_text TEXT,
  retry_count INT,
  version INT NOT NULL DEFAULT 0, -- 乐观锁
  mode VARCHAR(20),               -- script | free
  status VARCHAR(20),             -- playing | paused | ended
  game_state JSON DEFAULT {},     -- GameState.to_dict() 全字段
  context_summary TEXT,           -- 长会话压缩摘要
  ending_type, rounds_played, started_at, last_played_at, ended_at
)
INDEX (user_id, status), (user_id, last_played_at), (world_id)

messages (
  id, session_id, role, content,
  state_snapshot JSON,            -- assistant 消息保存当时 game_state 快照
  npc_dialogues JSON,             -- {npc: dialogue} 仅 assistant
  is_compressed BOOLEAN,
  created_at
)
```

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_state_manager.py` | apply_state_updates 各分支 / clue id 自增 / trust 硬限 |
| `tests/test_game_service.py` | _consume_turn 与 state_ready commit 顺序、StaleVersion → 40901 |
| `tests/test_session_lock.py` | acquire/release / 重复抢锁 / TTL 行为 |
| `tests/test_orchestrator.py` | state_ready 仅在 emit_state_ready=True 时 yield |
| `tests/test_game_stream_events.py` | 40901 错误码经 SSE error 事件传出 |

## 7. 已知短板与未来扩展

### P2

- **前端 409 自动重试**：当前 `frontend/lib/sse.ts` 没有针对 `code: 40901` 的自动重试，玩家会看到一次普通 error toast。常见诱因是用户在两个 tab 同时点 action — 加一次自动 retry（同 action_text）能消化 90% 误触。在写本节时该 case 还需要观察发生频率再决定是否做。
- **schema 演进**：GameState 加字段不需要 migration，但**改字段语义**（如 trust 范围、clue_id 命名规则）目前靠 code review 兜底；P2 应该加一个 schema_version 字段 + lazy migration helper。
- **state_snapshot 的 retry 路径**：`session.state_snapshot` 当前只在 `process_action` 入口前刷新一次。如果 retry 时玩家又触发了别的写（如 case_board GET 不算，但未来如果加了 case_board PUT），rollback 点会跑偏。

### P3

- **multi-turn rollback / 分支选择**：当前一旦 `_commit_turn_state` 成功，玩家无法撤销那一轮。做"存档点"或"剧情分支"需要把 case_board_history 范式扩到 GameState 全字段（事件 sourcing），以及 SessionLock 的多分支语义。
- **多端同步广播**：玩家在 PC + 手机同时打开同一 session，PC commit 后手机的 game_state 不会自动刷新（要手动 reload）。需要 server push（额外 SSE channel 或 WebSocket）。
- **cross-session 角色档案**：玩家×NPC 维度的持久化（同一玩家在不同局里的 NPC 关系延续）跟当前 session 维度的 GameState 是两张表，目前没做。
