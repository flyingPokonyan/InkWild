# World Simulator（世界模拟器）模块技术说明

> 状态截至 2026-05-08。覆盖 WorldSimulator.tick 三步骤（intent / info / clock）+ event_system + ending_system（hard + AI judgment + summary）+ info_propagation 跟 NPC 私有记忆联动 + script-only hard ending 隔离全部落地后的形态。

WorldSimulator 是 [`./orchestrator.md`](./orchestrator.md) 主流水线的**第二阶段**（moderation_in 之后、Director 之前），跑一次 **<50ms 纯规则 tick**：让 NPC 的内心意图推进、信息在 NPC 之间扩散、世界时钟前进、按时间表更新 NPC 位置。它不调 LLM——所有 LLM 调度交给后续的 Director / NPC / Narrator。

它**不直接**做的事：
- 不做 LLM 调用——pure rule engine
- 不做记忆 SQL 写入（只产出 WorldEvent，由 orchestrator 转 memory_manager 写入）
- 不做案件板更新（详见 [`./case-board.md`](./case-board.md)）
- 不做 GameState commit（详见 [`./state-and-persistence.md`](./state-and-persistence.md)）

紧密耦合的上下游：
- 上：`orchestrator.process_action` 在 director 调用前调 `tick(state, world_data)`
- 内：`engine/intent_system.py`（详见 [`./intent-system.md`](./intent-system.md)）+ `engine/info_propagation.py` + `engine/world_clock.py`
- 下：`tick_result.world_events` 进 Director context 的「## 本轮世界事件」段
- 下：`tick_result.world_events`（type=info_spread / npc_action）由 orchestrator 调 `memory_manager.write_info_propagation_memories` / `write_dual_perspective_memories` 写入 NPC 私有记忆
- 下：`event_system.check_events` + `apply_event_effects` 在 director 之后跑
- 下：`ending_system.check_hard_endings` + `merge_ai_ending_judgment` + `generate_ending_summary` 在 narrator 之前判定 + 在 narrator 之后生成总结

## 1. 能力矩阵

### A. 时间推进（WorldClock）

| 能力 | 状态 | 实现 |
|---|---|---|
| 5 时段循环（上午 / 下午 / 傍晚 / 夜晚 / 深夜） | ✅ | `state_manager.TIME_SLOTS` |
| time_index 单调推进，"第N天·X" 反算 | ✅ | `state_manager._advance_time` |
| 每 tick 按 schedule 更新 NPC 位置（`npc_locations[name]`） | ✅ | `world_clock.py:48-53` |
| schedule 缺失某时段 → NPC 位置不变（不被强制清空） | ✅ | `if expected_location` |
| 环境过渡描述（如"晨光熹微，镇上渐渐热闹起来"）每 tick 输出一句 | ✅ | `ENVIRONMENT_TRANSITIONS` 5 条 |
| 时间触发 event 检测（trigger_type=time） | ✅ | `world_clock._time_condition_met` + `triggered_events` 去重 |
| 时间格式 `第1天·上午` 解析（`·` 分隔） | ✅ | `_extract_time_slot` |

### B. WorldSimulator.tick 编排

| 能力 | 状态 | 实现 |
|---|---|---|
| 入口深拷贝 state（避免就地破坏） | ✅ | `world_simulator.py:45` |
| step 1: IntentSystem.advance + apply_intent_effects | ✅ | `world_simulator.py:50-53` |
| step 2: InfoPropagation.propagate | ✅ | `world_simulator.py:58-59` |
| step 3: WorldClock.advance（位置 + 时间 event + 环境描述） | ✅ | `world_simulator.py:65-68` |
| 三步骤各自 try/except + warn 日志（一步失败不阻塞其他两步） | ✅ | 每步独立 `try / except: logger.warning(...)` |
| 输出 `TickResult(updated_state, world_events, environment_changes)` | ✅ | `world_simulator.py:22-28` |
| 性能预算 <50ms / tick | 🟡 监控 | 没显式 timing 埋点，依赖 `world_tick` orchestrator stage |
| LLM 0 调用（保证 tick 永远跑得动） | ✅ |  |

### C. 信息扩散（InfoPropagation）

| 能力 | 状态 | 实现 |
|---|---|---|
| InfoItem (source, content, known_by, created_at_round) 数据结构 | ✅ | `info_propagation.py:14-39` |
| 同位置 NPC 立即知晓（delay=0） | ✅ | `_same_location` 检查 npc_locations |
| 有社交关系延迟 2 轮（与 known_by 任一有 npc_relations 项） | ✅ | `SOCIAL_TIE_DELAY = 2` + `_has_social_tie` |
| 全镇延迟 5 轮（任何 NPC，兜底） | ✅ | `TOWN_WIDE_DELAY = 5` |
| 每轮一次 propagate，扩散事件以 WorldEvent(type="info_spread") 输出 | ✅ | `info_propagation.py:49-76` |
| 已知者集合就地扩展（known_by += new_knowers） | ✅ | `info.known_by.extend(new_knowers)` |
| 只对有 source 的 InfoItem 推进（known_by 空跳过） | ✅ | `if not info.known_by` |
| info_spread 事件供 orchestrator 写入 NPC 私有记忆 | ✅ | `memory_manager.write_info_propagation_memories` |
| 关系判断启发式（共享 npc_relations 项即"有社交联系"） | 🟡 简陋 | `_has_social_tie` 只看 npc_relations 字典存在 |

### D. World event 类型与下游消费

| event_type | 来源 | 下游消费 |
|---|---|---|
| `npc_action` | IntentSystem.advance（urgency≥8） | (a) 进 Director 「## 本轮世界事件」段；(b) involved_npcs ≥ 2 时双视角写记忆；(c) effects 同步落地到 GameState |
| `info_spread` | InfoPropagation.propagate | 进 Director context + 给每个 new_knower 写一条 memory_type=info_propagation 私有记忆 |
| `time_event` | WorldClock 触发的时间型 event | 进 Director context（暂未单独落地到 GameState） |
| `environment` | 保留（dataclass 支持，目前 WorldClock 不输出） | 🟡 |
| 通用：所有 event 进 Director context | ✅ | `orchestrator.py:362-364` 拼成 `[event_type] description` 列表 |
| environment_changes（5 条时段过渡文案中的当前一句） | ✅ | 进 Director context「## 环境变化」段 | `orchestrator.py:367-368` |

### E. event_system（剧本/世界级 event 触发）

| 能力 | 状态 | 实现 |
|---|---|---|
| 5 种 trigger_type：time / clue / location / clue_count / rounds_without_progress | ✅ | `event_system._matches_condition` |
| 模式过滤（`mode = both / script_only / free_only`） | ✅ | `event_system.py:14-18` |
| 已触发 event 去重（`state.triggered_events`） | ✅ | `event_system.py:11-12` |
| event.effects 落地：add_clues / npc_updates / unlock_location | ✅ | `apply_event_effects` 复用 `apply_state_updates` |
| 触发顺序：在 director 输出 state_updates 应用之后再 check | ✅ | `orchestrator.py:824-827` |
| 多个 event 同 turn 触发（每个独立 apply_event_effects） | ✅ | for loop |
| event 不存在 name/id → 跳过（不报错） | ✅ | `if not event_key: continue` |
| trigger_condition 解析失败（KeyError/TypeError）静默 → False | ✅ | try/except 兜底 |

### F. ending_system

| 能力 | 状态 | 实现 |
|---|---|---|
| `check_hard_endings`（仅 script 模式） | ✅ | `ending_system.py:92-109` |
| 自由模式 hard ending 跳过（`if game_mode == "free": return None`） | ✅ | `ending_system.py:93-94` |
| 三种 hard 条件类型：time / max_rounds / rounds_without_progress | ✅ | `_hard_condition_met` |
| 同时满足多 ending → 取最高 priority | ✅ | `max(matched, key=priority)` |
| Director 兜底 ending（`director_result.ending_triggered`） | ✅ | `merge_ai_ending_judgment` |
| AI judgment 必须 `should_end=True` 且 ending_type 匹配且对应 ending 有 soft_conditions | ✅ | `merge_ai_ending_judgment` |
| `hard_endings` 优先于 AI judgment | ✅ | `orchestrator.py:842-846` if-elif |
| `generate_ending_summary` 独立 LLM 调用（slot=ending_summary） | ✅ | `ending_system.py:39-89` |
| ending_summary slot 路由（`resolve_slot_router(db, "ending_summary") or game_router`） | ✅ | `api/game.py:98` + `services/model_management.py:62` |
| ending_summary 输出 strict JSON（ending_narrative + path_review + evidence_review） | ✅ | prompt 强制 JSON、`json.JSONDecodeError` 兜底 |
| ending_summary 失败兜底（极简文案，不抛异常） | ✅ | `ending_system.py:76-89` |
| evidence_review 仅 mystery 类型有（其他类型 null） | ✅ | prompt 引导 |

### G. 跟下游模块的协作

| 协作点 | 状态 | 实现 |
|---|---|---|
| `tick_result.updated_state` 替换 game_state（深拷贝过的） | ✅ | `orchestrator.py:351` |
| `tick_result.world_events` 拼成 Director context 段 | ✅ | `orchestrator.py:360-364` |
| `tick_result.environment_changes` 拼成 Director context 段 | ✅ | `orchestrator.py:367-368` |
| `info_spread` 事件写每个 new_knower 的私有记忆 | ✅ | `orchestrator.py:473-478` 调 `memory_manager.write_info_propagation_memories` |
| `npc_action` 事件 with ≥2 involved_npcs 写双视角记忆 | ✅ | `orchestrator.py:480-493` 调 `write_dual_perspective_memories` |
| 私有记忆走 batch embedding + DB 持久化（`game_service._consume_turn` done 阶段） | ✅ | 详见 [`./npc.md`](./npc.md) §3.3 |
| narrative_arc.update 在 director 之后跑（不在 tick 内） | ✅ | `orchestrator.py:460-468` |
| state_ready 在 ending 判定后 yield（保证 ending state commit 一起原子） | ✅ | `orchestrator.py:858-863` |

### H. 错误处理

| 能力 | 状态 | 实现 |
|---|---|---|
| WorldSimulator 三子系统各自 try/except | ✅ | `world_simulator.py:50-70` |
| 任一子系统失败不阻塞 turn（warn + 继续） | ✅ | `logger.warning("intent_system_error" / "info_propagation_error" / "world_clock_error")` |
| event_system 单 event 解析失败静默丢弃 | ✅ | `_matches_condition` try 兜 KeyError/TypeError |
| ending_system generate_ending_summary 失败兜底文案 | ✅ | `ending_system.py:76-89` |
| ending_summary JSON parse 失败 → 极简兜底 | ✅ | `json.JSONDecodeError` 分支 |

## 2. 关键能力实现要点

### 2.1 三步 tick 编排（intent → info → clock）

**问题**：早期 NPC 行为只靠"玩家 action → Director 决定 NPC 反应"——玩家不在场时世界完全冻结。需要一个**确定性、廉价、可观测**的 pre-Director tick 让世界能自己走。

**解决**：`WorldSimulator.tick` 三步骤串行：(1) IntentSystem.advance 推进 NPC 内心意图 + 落地 effect，(2) InfoPropagation.propagate 让信息按位置/关系/全镇扩散，(3) WorldClock.advance 推进 NPC 位置 / 时间 event / 环境描述。每步 try/except 隔离，单步失败不影响其他两步。无 LLM 调用，<50ms 跑完。

**实现**：
- `world_simulator.py:44-76` tick 主体
- 入口深拷贝 state（防止三步骤间互相破坏）
- TickResult 聚合三步骤产出的 events + environment_changes

**取舍**：拒绝了"用 LLM 模拟世界"——成本不可控且不稳定。确定性规则虽然粗糙（intent 关键词分类、info 启发式社交联系），但给 Director 提供了"世界正在自己动"的输入信号，Director 再用 LLM 判断后续叙事。代价是规则触发的 effect 比较程式化（同样关键词每次产生一样 effect），后续可以补 D 表覆盖率。

### 2.2 world_events 三个下游分发路径

**问题**：tick 产出的 WorldEvent 既要让 Director 知道"刚才发生了什么"，又要给具体 NPC 写私有记忆（信息隔离要求），又要落地到 GameState。三个目的不能复用同一份数据流——Director 看的是聚合描述、NPC 看的是个人视角的记忆条目、State 改的是结构化字段。

**解决**：分三条路：
1. **Director context**：所有 events 拼成 `[event_type] description` 列表进系统 prompt 的「## 本轮世界事件」段（聚合视角）
2. **NPC 私有记忆**：`info_spread` → `write_info_propagation_memories` 给每个 new_knower 写一条 `memory_type=info_propagation`；`npc_action` 含 ≥2 NPC → `write_dual_perspective_memories` 给两个 NPC 各写一条**视角不同**的记忆
3. **GameState 落地**：intent_system 产出的 npc_action 自带 `effects` dict，`apply_intent_effects` 把 npc_locations / new_info_items / npc_relations / flags 落到 state（**就地修改** updated_state，因为 tick 入口已深拷贝过）

**实现**：
- 路径 1：`orchestrator.py:362-364`
- 路径 2：`orchestrator.py:473-493` + `engine/memory_manager.py::write_info_propagation_memories` / `write_dual_perspective_memories`
- 路径 3：`engine/world_simulator.py:79-106` `apply_intent_effects`

**取舍**：三路分发显得繁琐，但它支撑了 NPC 信息隔离原则（详见 [`./npc.md`](./npc.md) §4）——Director 看到的"信息扩散"是上帝视角，NPC 自己的记忆是"我现在知道了 X"，两边语义不同。复用同一个数据结构会破坏隔离。

### 2.3 hard ending vs AI judgment 优先级

**问题**：剧本作者写了"hard ending（time > 30 触发 BAD）"，但同时玩家可能在 25 轮通过完美推理触发了 GOOD 结局——Director 在自己的 turn 也能输出 `ending_triggered`。两个机制并存，怎么决定优先级？

**解决**：orchestrator 顺序：先 `check_hard_endings`，命中直接拿；没命中才看 `director_result.ending_triggered`。即"hard 条件兜底，AI judgment 优先于'什么都不发生'"。AI judgment 还要走 `merge_ai_ending_judgment` 二次校验：`should_end=True` + `ending_type` 必须匹配某个有 `soft_conditions` 的 ending 才算数（防 Director 幻觉编造结局名）。

**实现**：
- `orchestrator.py:842-846` if-elif
- `ending_system.check_hard_endings` script-only 隔离
- `ending_system.merge_ai_ending_judgment` 严格匹配
- 自由模式：check_hard_endings 直接 return None；只能靠 Director judgment（极少触发，自由模式没结局压力）

**取舍**：拒绝了"hard ending 优先级压过 AI judgment"——剧本作者的 hard 条件通常是兜底机制（如"超过 30 轮强制结束"），玩家在那之前就完美完成主线时不应该被强行覆盖。但当前的 hard-priority 也意味着"作者写的 max_rounds=30 触发后玩家无论做什么都进 BAD"——这是 by design 的规则上限。

### 2.4 generate_ending_summary 独立 LLM 调用 + JSON 兜底

**问题**：结局画面除了 `ending_type` + `title` 两个粗粒度字段外，玩家想看一段 200-400 字的"个性化结局叙事 + 关键节点回顾 + （仅 mystery）证据评估"。如果让主 narrator 在 turn 内生成，会跟 narrative 流式混在一起影响节奏；让 Director 输出 JSON 又会让 Director 单 turn 输出 schema 太复杂。

**解决**：在 narrator 流完后、ending event 发出前，独立跑一次 LLM 调用 `generate_ending_summary`：(a) 用专属 slot `ending_summary`（成本可控可换档），(b) 输出 strict JSON（不许 markdown 块、不许多余文本），(c) JSON 解析失败兜底极简文案而不是抛异常导致 ending 事件发不出去。

**实现**：
- `engine/ending_system.py:39-89`
- 输入：ending_type / title / case_board / memory_context / triggered_events / 统计
- 输出 schema：`{ending_narrative, path_review, evidence_review | null}`
- slot 解析：`api/game.py:98` `resolve_slot_router(db, "ending_summary") or game_router`
- orchestrator 调用：`orchestrator.py:931-941` 包在 try/except 里，generation 失败仅 warn，不阻塞 ending 事件

**取舍**：拒绝了"复用 narrator slot"——ending summary 跟 narrative 调性不同（narrative 沉浸式第二人称，summary 第三人称回顾性），混用会影响 narrative 风格的 prefix-cache 一致性。代价是多一次 LLM 调用，但仅在 ending 那一回合发生，对全 session 平均成本影响小。

### 2.5 info_propagation 三档延迟

**问题**：信息在世界里怎么扩散是 NPC 群像感的关键——王福偷偷跟玩家说的事不应该 5 秒后赵姐就知道。但纯位置同场的扩散又不够——隔壁村的远房亲戚也可能被传到。

**解决**：三档：(a) **同位置**（`_same_location` 检查 npc_locations 是否同值）→ delay=0，立即知晓；(b) **有社交关系**（`_has_social_tie` 检查 npc_relations 字典里有对方）→ delay=2 轮；(c) **全镇兜底** → delay=5 轮。三档独立判断，任一满足就 propagate。每轮一次，新加入的 known_by 在下轮才能继续扩散给他们的圈层。

**实现**：
- `info_propagation.py:78-99` `_find_new_knowers` 三档串联
- `_same_location` 用 npc_locations dict 比较
- `_has_social_tie` 启发式：双方在 npc_relations 字典里互相有 entry 即视为有联系（这是粗糙近似——真正的双向关系应该看 `npc_relations` 表，但当前 InfoPropagation 只看 GameState 内的 dict）
- 输出 WorldEvent(type="info_spread", involved_npcs=new_knowers)

**取舍**：拒绝了"用 NPC-2 的 npc_relations 表做精确社交图"——info_propagation 跑在 tick 里，访问 DB 表不合适（破坏纯函数 + 增加延迟）。当前启发式是 in-memory 黑板的近似，准确度足够"该传到的传到、不该传到的不传到"的体感。NPC-3 后台模拟时可能要重新审视。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/world_simulator.py` | WorldSimulator + tick + TickResult + apply_intent_effects |
| `backend/engine/world_clock.py` | WorldClock.advance + 5 时段环境过渡文案 + time event 检测 |
| `backend/engine/info_propagation.py` | InfoPropagation.propagate + 三档延迟 + InfoItem |
| `backend/engine/intent_system.py` | IntentSystem（详见 [`./intent-system.md`](./intent-system.md)）+ WorldEvent 数据类 |
| `backend/engine/event_system.py` | check_events + apply_event_effects + 5 种 trigger_type |
| `backend/engine/ending_system.py` | check_hard_endings + merge_ai_ending_judgment + generate_ending_summary + 兜底文案 |
| `backend/engine/orchestrator.py:348-358` | tick 调用 + world_tick stage timing |
| `backend/engine/orchestrator.py:825-846` | event_system + ending_system 在 director 之后 |
| `backend/engine/orchestrator.py:471-493` | world_events → memory_manager 三路分发 |
| `backend/engine/orchestrator.py:928-948` | ending event 发出 + ending_summary 异步生成 |
| `backend/engine/memory_manager.py::write_info_propagation_memories` | info_spread → 私有记忆条目 |
| `backend/engine/memory_manager.py::write_dual_perspective_memories` | 双 NPC 互动 → 双视角记忆 |

## 4. 配置项

| Slot | 用途 |
|---|---|
| `ending_summary` | `generate_ending_summary` 专用 LLM 调用；未绑定时 fallback 到 `game_router` 主档（`api/game.py:98`） |

WorldClock / IntentSystem / InfoPropagation 没有 env 变量。所有阈值是模块常量：

| 常量 | 值 | 位置 |
|---|---|---|
| TIME_SLOTS | 5 槽（上午 / 下午 / 傍晚 / 夜晚 / 深夜） | `state_manager.py:11` |
| ENVIRONMENT_TRANSITIONS | 5 条文案 | `world_clock.py:14-20` |
| InfoPropagation.SAME_LOCATION_DELAY | 0 | `info_propagation.py:45` |
| InfoPropagation.SOCIAL_TIE_DELAY | 2 | `info_propagation.py:46` |
| InfoPropagation.TOWN_WIDE_DELAY | 5 | `info_propagation.py:47` |

## 5. 数据库 schema

无独立表。所有状态由 `GameState` 持有（详见 [`./state-and-persistence.md`](./state-and-persistence.md)）：
- `npc_locations: dict[npc_name, location]` — WorldClock 写
- `info_items: list[dict]` — InfoPropagation 维护 + intent effect 加新条
- `triggered_events: list[str]` — event_system + world_clock 共同维护去重
- `flags: dict` — intent effect 黑板
- `world_conflicts: list[dict]` — 自由模式 init_npc_intents 灌入，tick 不改

`ending_summary` 输出（`ending_narrative` / `path_review` / `evidence_review`）作为 ending SSE 事件 payload 发给前端，**不持久化**——重新查 ending 详情时由前端缓存或重生成。

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_world_simulator.py` | tick 三步骤串联 + 子系统失败隔离 + apply_intent_effects |
| `tests/test_world_clock.py` | NPC schedule 位置更新 + 5 环境过渡 + time event 触发 + 已触发去重 |
| `tests/test_info_propagation.py` | 三档延迟（同位置 / 社交 / 全镇）+ known_by 推进 + info_spread 事件 |
| `tests/test_intent_system.py` | 见 [`./intent-system.md`](./intent-system.md) |
| `tests/test_event_system.py` | 5 种 trigger_type + mode 过滤 + 已触发去重 |
| `tests/test_ending_system.py` | hard ending 优先级 / script-only / AI judgment merge / 严格 ending_type 校验 |
| `tests/test_ending_summary.py` | strict JSON 解析 / JSON 错误兜底 / mystery vs 非 mystery evidence_review |
| `tests/test_orchestrator.py` | tick → director context / world_events → 私有记忆 / hard ending 路径 / ending 事件发出顺序 |

## 7. 已知短板与未来扩展

### P2

- **WorldSimulator 性能埋点**：当前只有 `world_tick` 整体 stage timing（详见 [`./orchestrator.md`](./orchestrator.md) §1.B）。子系统级别耗时没单独埋点；如果某次 NPC 数 >10 导致 intent_system 慢，要看不到。改进点：每子步骤 debug 级 timing。
- **intent action effect 关键词覆盖**：`_compute_action_effects` 只识别 5 类动词（监视 / 威胁 / 灭口 / 准备 / 通用），其他 plan_stage 文案落不下 effect。详见 [`./intent-system.md`](./intent-system.md) §7。
- **info_propagation 社交关系**：当前 `_has_social_tie` 启发式（双方在 npc_relations 字典里互相有 entry）跟 NPC-2 的持久 npc_relations 表脱节。NPC-2 关系应该参与扩散判断——但加入需要在 tick 里访问 DB（破坏纯函数），需要把 NPC-2 关系预加载到 GameState 里。
- **time_event effects 落地**：当前 WorldClock 触发的 time event 只生成 WorldEvent 让 Director 知道，但 `event_def.effects` 没被 apply（不像 event_system.apply_event_effects 那样落到 state）。如果剧本作者想让某时间点自动加线索/改 NPC 心情，目前要走 `events_data` 而非 `world_clock` 路径。

### P3

- **NPC-3 后台模拟**：玩家不在场时 tick 让 NPC↔NPC 真互动并更新 npc_relations.trust。需要 IntentSystem 加 target_npc / target_action 字段 + tick 累计 trust delta + 阈值触发 LLM 重写 history_summary。详见 [`./intent-system.md`](./intent-system.md) §7。
- **天气 / 季节 / 大世界事件**：当前 ENVIRONMENT_TRANSITIONS 5 条只覆盖时段，没下雨没节庆没社会大事。要做需要扩 WorldClock 输入（世界配置加 weather schedule / festivals）+ 扩 environment_changes 文案。
- **ending_summary 持久化**：当前每次查 ending 详情都要重新生成（如果前端没缓存），重玩同一结局会拿到不同文本。如果想做"结局回顾页"应该把 ending summary 落到 `game_sessions.ended_at` 旁边或独立表。
- **多结局并存**：当前 hard / AI 都只取**一个** ending；多支线游戏可能想要"主线 BAD + 支线 GOOD" 同时显示。要改 ending event payload 为 list + 前端展示策略。
