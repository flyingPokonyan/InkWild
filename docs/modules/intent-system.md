# Intent System（NPC 意图系统）模块技术说明

> 状态截至 2026-05-08。覆盖 0.A.1 修复（urgency ≥ 8 触发 action 落地 effect）+ 自由模式 init_npc_intents + intent 注入 NPC system prompt + intent 跟 narrative_arc / stage_summary 联动落地后的形态。

Intent System 给每个 NPC 维护一份**结构化意图**（current_goal + urgency + plan_stage + blocked_by + plan_stages），使 NPC 不再只被动响应 Director instruction，而是"心里有自己想做的事"。它跑在 [`./world-simulator.md`](./world-simulator.md) 的 tick 里，每轮**确定性**（无 LLM）推进每个 NPC 的 urgency / plan_stage，urgency ≥ 8 时生成 npc_action `WorldEvent` 并落地 effect 到 GameState。

它**不直接**做的事：
- 不做 LLM 调用——纯规则引擎，<5ms / NPC
- 不做"NPC 互相说什么"（那是 [`./npc.md`](./npc.md) 顺序对话 + Director 调度）
- 不做 NPC 跟玩家关系演变（那是 `state_manager.apply_state_updates::npc_updates`）
- 不维护 NPC 位置（那是 `engine/world_clock.py` 按 schedule 更新 `npc_locations`）

紧密耦合的上下游：
- 上：`engine/world_simulator.py::tick` 第 1 步调 `IntentSystem.advance` + 第 2 步 `apply_intent_effects` 落地 effects
- 上：`services/game_service.py::start_game` 自由模式调 `init_npc_intents` 初始化
- 下：`engine/prompts.py::build_npc_system` 把 `current_intent` 渲染进 NPC system prompt 的可变后缀
- 下：`orchestrator.should_trigger_stage_summary` 把高 urgency intent 当作"该做章节总结"的触发信号之一

## 1. 能力矩阵

### A. NPCIntent 数据结构

| 字段 | 类型 | 状态 | 说明 |
|---|---|---|---|
| `current_goal` | str | ✅ | NPC 此刻最想做的事；free 模式默认取 `npc.secret`，没 secret 则用 "{name}维持日常秩序" 兜底 |
| `urgency` | float [1.0, 10.0] | ✅ | 紧迫度，每 tick 自动 +0.5（max 10） |
| `plan_stage` | int | ✅ | 当前在 plan_stages 中的索引 |
| `plan_stages` | list[str] | ✅ | 默认 ["观望", "准备", "行动"]；world creator 可覆盖 |
| `blocked_by` | str \| None | ✅ | 解锁条件，如 `"clue_count >= 5"`；满足时清空且 plan_stage +1 |
| 持久化 | dict in `GameState.npc_intents[name]` | ✅ | to_dict / from_dict round-trip |
| 默认值兜底 | ✅ | from_dict 容忍缺失字段 |

### B. tick 循环行为（IntentSystem.advance）

| 步骤 | 行为 | 实现位置 |
|---|---|---|
| 1. 检查 blocked_by 是否解除 | 满足条件 → 清空 blocked_by + plan_stage +1（不超过最后阶段） | `intent_system.py:117-119` |
| 2. urgency 自然增长 +0.5（cap 10） | ✅ 每 tick 必涨 | `intent_system.py:122` |
| 3. urgency ≥ 8 且无 blocker → 生成 `WorldEvent(type="npc_action")` | ✅ 0.A.1 修复重点 | `intent_system.py:125-138` |
| 4. event.effects 由 `_compute_action_effects` 计算（npc_locations / new_info_items / npc_relations / flags） | ✅ | `intent_system.py:178-240` |
| 5. 把更新后 intent 写回 state.npc_intents | ✅ | `intent_system.py:141` |
| 错误隔离（intent_system 抛 → world_simulator warn 继续） | ✅ | `world_simulator.py:54-55` |
| 跑前后状态深拷贝（更新隔离） | ✅ | tick 入口已 deepcopy state |

### C. blocked_by 条件解析

| 能力 | 状态 | 实现 |
|---|---|---|
| 正则匹配 `"<var> <op> <int>"` 形如 `clue_count >= 5` | ✅ | `_CONDITION_RE = r"^(\w+)\s*(>=|<=|>|<|==)\s*(\d+)$"` |
| 支持 `clue_count` / `round_number` / `time_index` 变量 | ✅ | `_resolve_variable` 三 case |
| 不匹配模式 → 返回 False（永远不解锁） | 🟡 | LLM 写错条件直接锁死，没 fallback |
| 支持复合条件（and / or） | ❌ | 单条件 only |
| 支持字符串变量（如 `discovered = "X"`） | ❌ | 仅整数比较 |

### D. action 落地 effect（0.A.1 修复点）

| stage_text 关键词 | 产生的 effect | 实现 |
|---|---|---|
| 含「监视」「跟踪」 | `npc_locations[npc] = current_location` + `flags[{npc}_observing] = True` | `_compute_action_effects:194-197` |
| 含「威胁」「警告」 | 移动到 target 位置 + 写 `npc_relations[target]` mood=紧张 + 写 `info_items` 双方都知道 | `_compute_action_effects:201-220` |
| 含「灭口」「袭击」「执行」 | `flags[{target}_in_danger] = True` + 写单边 info_item | `_compute_action_effects:222-235` |
| 含「准备」 | `flags[{npc}_preparing] = True` | `_compute_action_effects:237-238` |
| 其它 stage_text | effects 全空（仍生成 event 但无落地） | 兜底 |
| target 提取（从 stage_text 找已知 NPC 名） | ✅ | `_extract_target_from_stage` 字符串包含匹配 |
| effects 由 `apply_intent_effects` 落地到 GameState | ✅ | `world_simulator.py:79-106` |
| trust_change / mood / last_interaction 写入 npc_relations | ✅ | `apply_intent_effects:88-104` |
| flags 写入 GameState.flags（黑板 KV） | ✅ | `apply_intent_effects:86` |

### E. intent 初始化（free 模式 vs script 模式）

| 模式 | 初始化路径 | 实现 |
|---|---|---|
| **自由模式** | `init_npc_intents(npcs, world_tensions)` 在 `start_game` 调用 | `intent_system.py:56-101` + `game_service.py:120-123` |
| 自由模式 NPC 默认 goal | `npc.secret` 或 "{name}维持日常秩序" | `init_npc_intents:67-69` |
| 自由模式 plan_stages 默认 | ["观望", "准备", "行动"] | `init_npc_intents:72` |
| 自由模式 world_conflicts | 由 `world.free_setting` 拆行生成 | `init_npc_intents:86-95` |
| 自由模式 info_items 初始灌入 | 每个 npc.knowledge 一条 InfoItem，known_by=[自己] | `init_npc_intents:76-84` |
| **剧本模式** | 不初始化 npc_intents（默认 dict {}） | `game_service.py:112` 走 free-only 路径 |
| 剧本模式 intent 来源 | 暂无 — `current_intent` 在 NPC prompt 里为空段（不渲染） | by design |
| 创世期 LLM 写 plan_stages / initial_urgency / blocked_by | 🟡 部分 | `world_creator_agent` 可填，但 free-only 真正使用 |

### F. NPC system prompt 注入（"你心里在意的事"）

| 段落 | 注入条件 | 实现 |
|---|---|---|
| `## 你心里在意的事` 段头 | `current_intent.current_goal` 非空 | `prompts.py:534-555` |
| `- 你心里此刻最想做的事：{goal}（紧迫程度 N/10）` | urgency 可格式化 | `prompts.py:543-548` |
| `- 你正处在「{stage_label}」阶段` | 0 ≤ plan_stage < len(plan_stages) | `prompts.py:553` |
| `- 但你被「{blocked_by}」挡住` | blocked_by 非空 | `prompts.py:554-555` |
| 位置 | NPC prompt **可变后缀**（场景之后、peer_dialogues 之前） | line ~534 |
| 段头明确"影响你的语气和优先级，但不要直接说出来" | ✅ 防 NPC 直接念出心理活动 | `prompts.py:550` |
| 来源 | `game_state.npc_intents[npc_name]` | orchestrator 取 dict 后透传 |
| 信息隔离 | 只传**自己的** intent；其他 NPC 的 intent 永远不暴露 | 见 [`./npc.md`](./npc.md) §4 隔离表 |

### G. 跨模块协作

| 协作点 | 状态 | 实现 |
|---|---|---|
| `WorldSimulator.tick` step 1 调 IntentSystem.advance | ✅ | `world_simulator.py:50-53` |
| 生成的 npc_action WorldEvent 进 director context（"## 本轮世界事件"段） | ✅ | `orchestrator.py:362-364` |
| 双 NPC 卷入的 npc_action 写双视角私有记忆 | ✅ | `memory_manager.write_dual_perspective_memories`（详见 [`./world-simulator.md`](./world-simulator.md)） |
| 单 NPC npc_action 通过 info_propagation 扩散 | ✅ | `info_propagation.propagate` 下一 tick 处理新 info_items |
| `should_trigger_stage_summary` 用高 urgency intent 作为触发条件 | ✅ | `orchestrator.py:93-100`（自由模式 + ≥30 轮 + 至少一个 urgency≥8） |
| `build_stage_summary_instruction` 把 urgent goals 喂给 narrator | ✅ | `orchestrator.py:111-128` |
| narrative_arc 三幕检测（未直接消费 intent，但同样跑在 tick 后） | 🟡 间接 | `engine/narrative_arc.py` 仅看 round / clue count |

### H. 已知短板（每行下文 §3 详述）

| 短板 | 状态 |
|---|---|
| urgency 持续涨但永远等不到 ≥ 8（goal 太宽泛 / blocked_by 永久卡死） | 🟡 |
| 玩家不在场时 NPC↔NPC 关系 trust 演变 | ❌（NPC-3 待做） |
| Director 编辑 NPC intent 的 tool（外力调整 plan_stages / urgency） | ❌（NPC-4 待做） |
| 复合条件 blocked_by（如 `clue_count >= 3 and round_number > 10`） | ❌ |
| stage_text 关键词匹配的 effect 表只覆盖 5 类动词 | 🟡 |
| 剧本模式不初始化 npc_intents | 🟡 by design，但导致剧本 NPC prompt 没"在意的事"段 |

## 2. 关键能力实现要点

### 2.1 urgency ≥ 8 真正生成 action effect（0.A.1 修复）

**问题**：早期 IntentSystem 只更新 urgency 数值，没有 "urgency 高到一定程度 → NPC 真的做点什么 → 改变世界" 的回路。结果就是：自由模式跑 30 轮后所有 NPC urgency 都顶到 10，但世界毫无变化、玩家完全感觉不到 NPC 在背后行动。

**解决**：urgency ≥ 8 且 blocked_by 为空时，IntentSystem 生成一个 `WorldEvent(event_type="npc_action", description="{npc}执行计划：{stage_label}", effects=...)`。effect 由 `_compute_action_effects` 按 stage_text 关键词分类计算（监视 / 威胁 / 灭口 / 准备 / 其他），WorldSimulator 用 `apply_intent_effects` 落地到 npc_locations / npc_relations / info_items / flags。

**实现**：
- `intent_system.py:125-138` 触发条件 + WorldEvent 构造
- `intent_system.py:178-240` `_compute_action_effects` 关键词分类
- `world_simulator.py:79-106` `apply_intent_effects` 把 effects 写入 GameState
- 生成的 npc_action WorldEvent 同时进 (a) Director context 段「## 本轮世界事件」，(b) info_propagation 当作新 info_item 扩散，(c) `write_dual_perspective_memories` 给两个 NPC 各写记忆

**取舍**：拒绝了"用 LLM 生成 effect"——确定性规则虽然粗糙（5 个关键词分类、字符串包含 match），但<5ms 跑得起。LLM 生成 effect 会让自由模式的 tick 时长翻倍且不稳定。当前 5 类关键词覆盖大部分常见 plan_stage 文案；不在白名单的 stage 退化为"只生成 event 不落地 effect"，仍能进 Director context 让 LLM 后续叙事用，不会失语。

### 2.2 blocked_by 条件求值

**问题**：world creator 经常给 NPC 写 plan_stage 之间的"门槛"——比如"杀手要等玩家发现 5 条线索后才会动手"。需要一种轻量条件 DSL 让 LLM 能写、引擎能跑。

**解决**：单一正则 `^(\w+)\s*(>=|<=|>|<|==)\s*(\d+)$` 解析三元式。变量在 `_resolve_variable` 里硬编码白名单（`clue_count` / `round_number` / `time_index`），不支持嵌套或复合条件。匹配失败时静默返回 False（永远阻塞）。

**实现**：
- `intent_system.py:104` 正则
- `intent_system.py:149-167` `_is_unblocked` + `_resolve_variable`
- 解锁后行为：`blocked_by = None` + `plan_stage = min(stage+1, len(stages)-1)`

**取舍**：拒绝了 Python `eval` / DSL 解释器——LLM 写错很容易变成命令注入。变量白名单 + 整数比较是"够用就行"的最小集。代价是 LLM 写复合条件（"and"/"or"）会被静默拒绝，永远卡死——但 world creator agent 的 few-shot 已经引导写单条件，实际未观察到 stuck 案例。

### 2.3 free 模式 init_npc_intents

**问题**：自由模式没有剧本提供"NPC 此刻在做什么"的种子；如果 npc_intents 初始化为空，NPC system prompt 就没有"## 你心里在意的事"段，NPC 的对话会缺乏目的性，跑久了像在"等指令"。

**解决**：`start_game` 在 `mode == "free"` 时调 `init_npc_intents(npc_dicts, world_tensions)`：(a) 每个 NPC 从 `secret` 字段或兜底 "{name}维持日常秩序" 取 current_goal，初始 urgency=3，stage=0；(b) 每条 npc.knowledge 写一条 known_by=[自己] 的 InfoItem 进 info_items，给 info_propagation 当种子；(c) `world.free_setting` 按行拆成 world_conflicts 并写明 involved_npcs。

**实现**：
- `intent_system.py:56-101` 整个 init 函数
- `game_service.py:112-123` 入口判断
- 关联：world_creator_agent 在创世时写 `npc.initial_urgency` / `plan_stages` / `blocked_by` 字段，init_npc_intents 透传

**取舍**：剧本模式**不**初始化 npc_intents——剧本通过 events_data 控制节奏，NPC 心思由 Director 每轮决定。代价是剧本模式 NPC system prompt 永远没"在意的事"段，弱化了角色"目的感"。这条短板已知，但加 intent 到剧本模式会跟 events / endings 触发逻辑产生冲突，需要更大改造，暂未做。

### 2.4 NPC system prompt 注入（"心里在意的事"）

**问题**：even 把 intent 算出来了，如果不注入 NPC prompt，NPC 仍然像无目的角色。注入又要小心：直接说"NPC 你的目标是 X"会让 LLM 把目标念出来变成"我现在要监视你"——破坏沉浸。

**解决**：在 NPC prompt 可变后缀加段「## 你心里在意的事（影响你的语气和优先级，但不要直接说出来）」+ 三行：(1) 主目标 + 紧迫度 N/10，(2) 当前阶段 label，(3) blocked_by 描述（非空时）。段头明确"不要直接说出来"约束 LLM 把意图作为**潜台词**而非台词。

**实现**：
- `prompts.py:534-555` 段渲染逻辑
- 来源：orchestrator 在 `_run_all_npcs` 准备 NPC kwargs 时取 `game_state.npc_intents.get(npc_name)` 透传
- 信息隔离：只传**自己的** intent，其他 NPC 的不传（详见 [`./npc.md`](./npc.md) §4）

**取舍**：拒绝了把 intent 渲染进稳定前缀——intent 每 tick 变（urgency 涨、plan_stage 推进），放前缀会破坏 prefix-cache。放可变后缀代价是每 tick prompt 后半段都不同，但段长 ~3 行可控。

### 2.5 跟 stage_summary 的联动

**问题**：自由模式没 hard ending，如何识别"现在该在 narrative 里做一次阶段总结"？光看 round_number 不够——可能 30 轮玩家什么都没搅动，世界没积累张力。

**解决**：`should_trigger_stage_summary` 综合三个条件：(1) free 模式，(2) round 距上次总结 ≥30（首次 ≥20），(3) **至少一个 NPC 的 urgency ≥ 8** 或者世界冲突非空。intent 系统的高 urgency 信号天然反映"NPC 们已经被搅动起来了"——比单看 round_number 更精准。

**实现**：
- `orchestrator.py:86-128` `should_trigger_stage_summary` + `build_stage_summary_instruction`
- 触发后 narrator instruction 会带上 urgent_goals 列表（取前 3 个）
- 详见 [`./orchestrator.md`](./orchestrator.md) §2.6

**取舍**：阈值（≥8 / ≥20 / ≥30 轮）都是凭直觉拍的。能调，但目前没有客观信号能证明"调了更好"——P3 加 LLM-as-judge 或玩家反馈再优化。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/intent_system.py` | NPCIntent / WorldEvent dataclass + IntentSystem.advance + init_npc_intents |
| `backend/engine/world_simulator.py` | tick 中调用 IntentSystem + apply_intent_effects |
| `backend/engine/state_manager.py` | GameState.npc_intents 字段持有 |
| `backend/engine/prompts.py:534-555` | "你心里在意的事" 段渲染 |
| `backend/engine/orchestrator.py:86-128` | should_trigger_stage_summary / build_stage_summary_instruction |
| `backend/engine/orchestrator.py:630-648` | 取 npc_intents 透传给 build_npc_system |
| `backend/services/game_service.py:112-123` | free 模式 init_npc_intents 调用入口 |
| `backend/services/world_creator_agent.py` | 创世期 plan_stages / initial_urgency / blocked_by 字段写入 |

## 4. 配置项

无独立 env 变量。intent 系统的所有阈值都是模块常量：
- urgency 自增 +0.5 / tick（`intent_system.py:122`）
- urgency 触发阈值 ≥8（`intent_system.py:125`）
- urgency cap 10.0（`min(10.0, ...)`）
- 默认 plan_stages = ["观望", "准备", "行动"]
- stage_summary 阈值 20 / 30（`orchestrator.py:100/102`）

## 5. 数据库 schema

无独立表。状态全部在 `GameState.npc_intents`（`game_sessions.game_state JSON.npc_intents`）中：

```json
{
  "npc_intents": {
    "王福": {
      "current_goal": "保住老爷的秘密",
      "urgency": 7.5,
      "plan_stage": 1,
      "blocked_by": "clue_count >= 3",
      "plan_stages": ["观望", "准备", "动手"]
    }
  }
}
```

每轮 `apply_state_updates` + tick 后整 `game_state` JSON 通过乐观锁原子写入（详见 [`./state-and-persistence.md`](./state-and-persistence.md)）。

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_intent_system.py` | advance 主循环 / urgency 自增 / blocked_by 解析 / urgency≥8 触发 effect |
| `tests/test_world_simulator.py` | tick 中调 IntentSystem + intent 失败被 try/except 隔离 |
| `tests/test_npc_world_awareness.py` | "你心里在意的事" 段渲染（goal / urgency / stage / blocked_by 四行） |
| `tests/test_orchestrator.py` | should_trigger_stage_summary 触发条件 / stage_summary instruction 含 urgent_goals |
| `tests/test_game_service.py` | free 模式 init_npc_intents 调用 + script 模式跳过 |

## 7. 已知短板与未来扩展

### P2

- **复合条件 blocked_by**：当前正则只支持单变量三元式 `var op int`，LLM 写 `clue_count >= 5 and met_alice` 会被静默拒绝永远卡死。改进点：换成轻量 AST 解析器或 jsonlogic-style 嵌套，但要防注入。在 NPC-3 之前不紧急——目前 world creator few-shot 引导写单条件，未观察到大规模 stuck。
- **stage_text 关键词覆盖率**：`_compute_action_effects` 只识别 5 个动词类（监视 / 威胁 / 灭口 / 准备 / 通用兜底）。LLM 写出"散播流言"、"诬陷"、"勒索"等都会退化为空 effect。改进点：加更多分类或让 Director 显式标注 effect 类型。这条不阻塞——退化路径仍然生成 event 进 Director context，narrative 上不哑火。
- **剧本模式 intent**：剧本模式不 init npc_intents → NPC prompt 永远没"在意的事"段，剧本 NPC 显得相对扁平。要做需要跟 events_data 协调，避免 intent 触发的 effect 跟 event_system 触发的 effect 双写互覆。
- **urgency 永久爬坡**：如果 NPC goal 永远完不成（玩家根本不踩它），urgency 会顶到 10 一直停留。Stage_summary 触发后没有"消耗 urgency"的反馈机制。

### P3 — NPC-3 / NPC-4

`docs/superpowers/specs/2026-05-06-npc-group-interaction.md` 中的 NPC-3 / NPC-4：

- **NPC-3 后台模拟**：玩家不在场时 world_simulator tick 让 NPC↔NPC 真互动——`NPCIntent` 加 `target_npc` / `target_action` 字段，按 deterministic 规则给两 NPC 的 trust / mood 累计变化。配 `npc_relations` 表（详见 [`./npc.md`](./npc.md) §3.11）的 `last_event_round` + `history_summary` 重写阈值。
- **NPC-4 Director 关系编辑**：DIRECTOR_TOOL 加 `npc_relation_updates` / `npc_intent_updates` 字段，让 Director 显式调整 NPC 的 plan_stage / urgency / blocked_by 或 NPC↔NPC 关系。需要平衡好"Director 能强行干预 vs 状态被乱改"。

NPC-3 / NPC-4 等 NPC-1（顺序对话）+ NPC-2（持久关系静态）上线一周后再开。trust delta 规则、history rewrite 阈值都需要真实数据调参。
