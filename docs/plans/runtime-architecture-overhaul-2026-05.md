# Runtime Architecture Overhaul — NPC Agency, Director 简化, Events 接通

> 设计 spec，2026-05-25 起草。覆盖 BUGS #19 / #21 / #22 / #25-runtime + NPC 串行性能问题 +
> "NPC 像 pipeline 不像 agent" 这个根本性产品体验问题。
>
> **本 spec 不写实现步骤**，落地用 `superpowers:writing-plans` 出 plan。
>
> **不包含**：generation pipeline 改造（#9/#16 name_critic, #23 IP, #24 semantic_review, #25-gen）→ 单独 spec；
> 任务生命周期 / LLM throttle（#17/#20）→ 单独 spec。
>
> 配套已修复：[#18 / #26 runner 局部 bug](../../experiments/local/BUGS.md)（2026-05-25 已 commit）。

---

## 1. 背景与动机

### 1.1 表面症状（来自 BUGS.md + 实测）

- **NPC sequential 性能**：3 NPC × thinking 模型串行 = 60-90s wall time / turn，占总 turn 时间 60-70%
- **#25-runtime**：NPC 持续 information-dump，玩家"细察"被 NPC"代察"
- **#19**：玩家弱输入时 NPC suggestion 默认成立，narrator 把建议描成现实
- **#21**：玩家多步意图（取匣→回大理寺→再细察）被 narrator 压成一段，最后一步被 NPC 抢做
- **#22**：剧本 events_data 形同虚设——director 不消费，20 round 0 触发，case_board 走 memory sync 通路

### 1.2 根本问题

**Director 是 god-mode 编剧，所有 agency 在 director 身上，NPC 是它的木偶。**

证据：当前 `DIRECTOR_TOOL.input_schema`（[prompts.py:6-169](../../backend/engine/prompts.py)）输出包括：

- `involved_npcs` — 谁参与
- `npc_instructions` — **每个 NPC 该做/说什么**（god-mode 关键证据）
- `npc_speech_order` — 发言顺序
- `inform_npc_calls` — **director 手动往 NPC 私有记忆塞事实**（god-mode 另一证据）

NPC 拿到 `instruction` 出 `dialogue` ——执行者，不是 agent。

这造成的连锁问题：
1. NPC 没有"决定做什么"的能力，只有"按指令说话"的能力
2. NPC 不会用工具（所有 context 被 orchestrator 预先注入到 prompt）
3. NPC 没有 loop（一次性调用：进来 → 出 dialogue → 走人）
4. **结果：玩家感觉 NPC 是"AI 写的角色"，不是"活的角色"**

### 1.3 设计目标

**首要目标**：把 agency 从 director 还给 NPC。让产品体验从"看 AI 写戏"变成"跟会自主决策的角色互动"。

**次要目标**（顺带解决）：
- NPC sequential 性能：DAG / priority 自报替全局开关
- #19/#21：玩家保护 + 多步动作切分
- #22：director 接通 events_data，剧本事件树真正起作用
- #25-runtime：NPC 不再 information-dump

**非目标**：
- 不追求 NPC 完全自主（开放沙盒 / 无监督博弈）—— 互动叙事需要叙事收束
- 不追求每个 NPC 单回合 ReAct 多调用 —— cost / latency 与产品形态不符
- 不重写 narrator / case_board / memory_manager 主体 —— 它们消费新 schema 但不动核心

---

## 2. 设计原则

### 2.1 vocabulary not rules

action enum 是 NPC 的"工具集"（类比 Claude Code 的 Read/Edit/Bash/Grep），不是 if-else 规则表。

| ✅ 允许 | ❌ 禁止 |
|---|---|
| 给 NPC 自我（goal/mood/memory/scene），让 LLM 自己判断该 act 哪个 | 写"如果场景是审讯则选 withhold"这种规则 |
| 同一场景，不同 NPC 做出不同选择 | 任何"scene_type → action_type" 查找表 |
| NPC prompt 描述 self（"你是 X，目标是 Y") | NPC prompt 写"如果...就..." |
| 结构化 payload 让下游消费（narrator / case_board / state） | 结构本身约束 NPC 决策 |

### 2.2 director 是舞台调度，不是编剧

director 描述"发生了什么"+"舞台位置"，**绝不描述"NPC 该怎么反应"**。

参考话剧舞台指示：
- ✅ "(玩家拿着账本对光看)" — 客观刺激
- ❌ "(周世安应该回避)" — 反应指导

### 2.3 B + selective depth

默认每个 active NPC 单次 LLM 调用决策（高效）；高戏剧密度回合开 selective depth（多调用 + 工具），代价是 latency。

| 阶段 | 调用数 | 触发率 |
|---|---|---|
| baseline（low/medium intensity）| 1 thinking call | ~70% turns |
| high intensity | 1 thinking + ≤3 tool calls | ~25% turns |
| climax | 2 thinking + ≤3 tool calls each | ~5% turns |

### 2.4 layered state for offstage NPCs

NPC 状态拆 3 层，offstage 时只冻结最贵的那层（LLM-driven intent）。

| 层 | offstage 时 | 谁更新 |
|---|---|---|
| L1 位置 / 日程 | 自动更新 | world_clock / world_simulator |
| L2 关于 NPC 的世界事实 | 自动累积 | info_propagation / event log |
| L3 NPC 内心（intent / mood / plan） | 冻结，再激活时 catch-up | 单次 LLM 调用补做 |

---

## 3. 架构总览

### 3.1 当前架构（要改）

```
moderation_in
  → world_tick (sync)
  → director [thinking, 20-30s]
    输出: involved_npcs + npc_instructions[per-NPC] + npc_speech_order + inform_npc_calls
  → per-NPC DB awaits (sequential)
  → NPC sequential [3 NPC × 20-30s thinking]
    每个 NPC 收 instruction，按 instruction 出 dialogue
  ‖ narrator_prelude (overlap with NPCs)
  → narrator_weave (waits NPC done)
  → moderation_out
  → ending check / state commit
```

### 3.2 新架构

```
moderation_in
  → world_tick (sync)
  → world_clock advance + L1/L2 deterministic updates
  → player_input_protection check (#19)
  → action_segmentation check (#21) → 可能拆 turn
  → director v2 [thinking, 20-30s]
    输出: active_npcs + per_npc_focus + scene_role + dramatic_intensity
        + offstage_active + event_fire_intent (#22)
        + state_updates / quick_actions / ending / memory_extracts / case_board_ops
        ❌ 不再输出 npc_instructions / npc_speech_order / inform_npc_calls
  → catch-up calls (并行, 仅 newly-active NPCs)
  → offstage_active ticks (并行, ≤3 NPC, 仅触发条件满足时)
  → active NPC calls (并行, 各自 LLM 调用, 自决 action)
    每个 NPC: 输入 scene_brief + per_npc_focus + own state → 输出结构化 action
    高 intensity 时启用 tools (recall_memory / check_relationship / ...)
    climax 时跑 reflect + act 两调用
  ‖ narrator_prelude (overlap with NPC calls)
  → narrator_weave (consume structured action list by priority)
  → moderation_out
  → ending check / state commit
```

**关键变化**：
1. Director 输出 schema 大改：删 3 字段，加 8 字段（见 §5）
2. NPC LLM 调用从 sequential 变 parallel（NPC 之间默认无依赖，需要时通过 priority 表达）
3. NPC 输出从 `dialogue: str` 变结构化 action
4. 新增 catch-up call 机制（NPC 重新进入 active 时）
5. 新增 offstage_active 调度（关键 NPC 在背景持续活跃）
6. 引入 selective depth（基于 dramatic_intensity）

### 3.3 紧密耦合的上下游

新架构动到的文件：

- **改写**：`engine/director_agent.py`、`engine/npc_agent.py`、`engine/orchestrator.py`、`engine/prompts.py`、`engine/narrator_agent.py`
- **新增**：`engine/npc_action.py`（action schema 定义 + 校验）、`engine/npc_tools.py`（4 个工具实现）、`engine/npc_catchup.py`（catch-up call）、`engine/offstage_scheduler.py`（offstage_active 调度）、`engine/player_input_guard.py`（#19 守卫）、`engine/action_segmentation.py`（#21 拆分）、`engine/event_progress.py`（#22 trigger progress 计算）、`engine/director_validator.py`（#19 directive-leak 守卫）
- **改适配**：`engine/intent_system.py`（rule-based advance 废弃，保留 dataclass 给兼容）、`engine/case_board.py`（消费新 action 的 case_board hints）、`engine/memory_manager.py`（catch-up 时 batch 写背景 memory）
- **state schema**：`engine/state_manager.py`（NPC state 增加 `last_active_round` / `pending_player_segments` / `offstage_event_log` JSON 字段，无 Alembic migration）

---

## 4. NPC Action Schema

### 4.1 完整 schema

每个 active NPC 单次 LLM 调用输出一个 action object：

```jsonc
{
  // —— 必填 ——
  "action_type": "speak" | "withhold" | "act" | "observe" | "scheme" | "interject",
  "priority": 1-10,  // 自报本回合戏份重要性，narrator weave 用来排序

  // —— 半必填（按 action_type 不同必填字段不同，见 §4.3）——
  "dialogue": "...",          // speak / withhold / interject 必填
  "physical": "...",          // act 必填，其它可选
  "tone": "sincere" | "deceptive" | "evasive" | "aggressive" | "vulnerable" | "neutral",
  // 注：observe / scheme 不需要 tone（无 visible output）；
  // tone "silent" 不在 enum，沉默通过 action_type=withhold 表达

  // —— 选填（通用，所有 action 都可带）——
  "target_npc": "NPC名",       // 行动针对某 NPC 时填
  "target": "物/地点/话题",     // 行动针对非 NPC 对象时填
  "intent_update": {           // NPC 自我汇报目标推进；为空表示无变化
    "progress": "advance" | "stuck" | "pivot" | "complete",
    "new_goal": "...",         // pivot 时必填
    "blocked_by": "条件描述",   // stuck 时建议填
    "stage_index_delta": 0-2   // 推进 plan_stages 的步数
  },
  "mood_shift": {              // 情绪变化；为空表示无变化
    "from": "原情绪",
    "to": "新情绪",
    "reason": "≤30字"
  },
  "hidden_note": "...",        // 只 NPC 自己未来回合能看到的备注；≤80字
  "wait_for": "NPC名",         // 想"接话"时，声明想等 X 说完再说（影响 orchestrator 排序）
  "reason": "..."              // interject 时建议填："为什么我要插话"
}
```

### 4.2 6 个 action 的语义

| action | 含义 | 主要 payload | 典型用途 |
|---|---|---|---|
| **speak** | 主动发言 | `dialogue` + `tone` + `target_npc?` | 70%+ 回合的默认 |
| **withhold** | 被期待发言但拒绝/敷衍/回避 | `dialogue` (敷衍话术) + `hidden_note` (拒绝真原因) | NPC 自我保护，玩家逼问时 |
| **act** | 物理行动（移动/给物/抓/攻击）| `physical` + `target?` | 关键转折——抢凶器、翻脸、跑路 |
| **observe** | 静默观察 | `hidden_note` (NPC 学到什么) | 不发言但影响下回合；常见低戏剧密度 |
| **scheme** | 纯内部行动（策划/记仇/动摇）| `intent_update` + `mood_shift` + `hidden_note` | 看不见但持久；替死板的规则 intent |
| **interject** | director 没主推但 NPC 主动插话 | `dialogue` + `reason` + `priority` (建议 ≥8) | agent feel 的关键体现，只有 active_npcs 内 NPC 可用 |

### 4.3 schema 校验规则

每个 action 走 `engine/npc_action.py::validate_action(npc_name, raw_dict, scene_role)`：

校验失败统一称作"omitted 占位"——该 NPC 该回合**不进 narrator weave**（既无 dialogue 也无 physical），相当于"NPC 在场但本回合无可见行动"。这不是 6 个 action_type 之一，仅是降级标记。

| 规则 | 失败时 |
|---|---|
| `action_type` 必须在 enum 内 | drop 整个 action → omitted 占位 + structlog warn |
| `action_type=speak/withhold/interject` 必须有 `dialogue` 非空 | 同上 |
| `action_type=act` 必须有 `physical` 非空 | 同上 |
| `dialogue` 长度 ≤ 400 字 | 截断 + warn |
| `physical` 长度 ≤ 200 字 | 截断 + warn |
| `hidden_note` 长度 ≤ 80 字 | 截断 + warn |
| `target_npc` 必须在 world 的 npcs 列表内 | drop target_npc 字段 + warn |
| `priority` 不在 1-10 | clamp 到 [1, 10] |
| `wait_for` 必须在本回合 active_npcs 内 | drop + warn |
| `scene_role=background` 但 `action_type=interject` 或 `priority>=8` | clamp priority 到 5 + warn（background NPC 不能抢戏） |
| `action_type=scheme/observe` 但 `dialogue` 非空 | 删 dialogue + warn（这些 action 不该有 visible output） |

### 4.4 universal field：`intent_update`

替掉当前规则驱动的 `IntentSystem.advance()`。NPC 每回合**自己**报告 intent 进度。

- `progress: advance` → orchestrator 把 `plan_stage += stage_index_delta`（默认 1）
- `progress: stuck` → 记录 `blocked_by`，下回合 director 看到可能引入帮助 NPC 推进
- `progress: pivot` → 替换 `current_goal = new_goal`，stage 重置 0
- `progress: complete` → goal 标完成；下次 catch-up 时 LLM 决定新 goal

老 `intent_system.py::IntentSystem.advance()` 完全废弃（不再每 tick `urgency += 0.5`）。`NPCIntent` dataclass 保留用作 state container。

---

## 5. Director Schema v2

### 5.1 删除字段

| 字段 | 删除理由 |
|---|---|
| `npc_instructions: {NPC: instruction}` | god-mode 写台词指令——agent 死硬源头 |
| `npc_speech_order: [NPC]` | 顺序不再由 director 决定（priority 自报 + DAG） |
| `inform_npc_calls: [{npc, info, importance}]` | director 手动往 NPC 脑子塞事实，违背 agency；用 info_propagation 自然扩散 + NPC observe action |

### 5.2 新增字段

| 字段 | 类型 | 用途 |
|---|---|---|
| `scene_brief` | `string`（≤300字）| 客观描述本回合发生了什么——玩家做了什么、环境变化、谁出现了。喂给 NPC 看。**禁止写 NPC 应该如何反应** |
| `active_npcs` | `string[]`（≤4）| 本回合可以行动的 NPC，**只点名，绝不写指令** |
| `per_npc_focus` | `{NPC: string}` | 每个 active NPC 收到的"场景刺激"描述（客观事实，禁止指导反应）|
| `scene_role` | `{NPC: "primary"\|"secondary"\|"background"}` | 戏份位置——舞台调度，不是行为指令 |
| `dramatic_intensity` | `"low"\|"medium"\|"high"\|"climax"` | 触发 selective depth 的开关 |
| `offstage_active` | `string[]`（≤3）| 不在 active_npcs 但 director 认为 offstage 也在动的 NPC |
| `event_fire_intent` | `string[]` | (#22) 本回合 director 想 fire 的 event id 列表（必须 ⊆ 未 fire events） |
| `narrative_pressure` | `"advance"\|"build_tension"\|"breathing_room"` | 给 narrator 的节奏提示，不传给 NPC。director 判断本回合是推进剧情、积累张力还是给玩家喘息 |

### 5.3 保留字段（不变）

- `scene_direction` —— 给 narrator 的场景指引（不涉及 NPC 行为）
- `state_updates` —— location / time_advance / new_clues / npc_updates / inventory_changes
- `quick_actions` —— UI 建议
- `ending_triggered` —— 结局判定
- `memory_extracts` —— 本回合记忆摘录
- `case_board_ops` —— script 模式案件板增量
- `player_action` —— 1.B.5 typed 玩家行动

### 5.4 完整 v2 JSON Schema 草案

```jsonc
{
  "name": "director_decision",
  "input_schema": {
    "type": "object",
    "properties": {
      // —— scene framing ——
      "scene_brief": {
        "type": "string",
        "description": "客观描述本回合发生了什么（玩家做了什么、环境变化、谁出现了）。禁止写 NPC 应该如何反应。≤300 字。"
      },
      "active_npcs": {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 4,
        "description": "本回合可以行动的 NPC。只点名，绝不写指令。"
      },
      "per_npc_focus": {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "description": "每个 active NPC 收到的场景刺激：他/她看到/听到/被针对了什么。每条 ≤120 字。客观事实，禁止暗示反应。"
      },
      "scene_role": {
        "type": "object",
        "additionalProperties": {
          "type": "string",
          "enum": ["primary", "secondary", "background"]
        },
        "description": "每个 active NPC 的戏份位置。primary=焦点；secondary=参与；background=在场靠边。NPC 看到这个能自决该不该抢戏。"
      },
      "dramatic_intensity": {
        "type": "string",
        "enum": ["low", "medium", "high", "climax"],
        "description": "本回合戏剧张力。high → NPC 启用工具；climax → NPC 跑 reflect + act 两步。"
      },
      "offstage_active": {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 3,
        "description": "不在 active_npcs 但 offstage 仍在策划的 NPC。这些 NPC 的 L3 内心也会被更新（不冻结）。"
      },
      "narrative_pressure": {
        "type": "string",
        "enum": ["advance", "build_tension", "breathing_room"],
        "description": "narrator 节奏提示。不是 NPC 看的。"
      },
      "scene_direction": {
        "type": "string",
        "description": "给 narrator 的场景描写指引（环境/氛围/节奏）。不涉及 NPC 行为。"
      },

      // —— events 接通 (#22) ——
      "event_fire_intent": {
        "type": "array",
        "items": {"type": "string"},
        "description": "本回合想 fire 的 script event id 列表。必须 ⊆ 未 fire 列表。orchestrator 会校验 trigger 条件，不通过的 silent drop。"
      },

      // —— 保留 ——
      "state_updates": { /* 同 v1 */ },
      "quick_actions": { "type": "array", "items": {"type": "string"} },
      "ending_triggered": { /* 同 v1 */ },
      "memory_extracts": { /* 同 v1 */ },
      "case_board_ops": { /* 同 v1，script 模式注入 */ },
      "player_action": { /* 同 v1 */ }
    },
    "required": [
      "scene_brief", "active_npcs", "per_npc_focus", "scene_role",
      "dramatic_intensity", "scene_direction", "state_updates",
      "quick_actions", "player_action"
    ]
  }
}
```

### 5.5 director system prompt 改造要点

新 prompt 必须明确：

1. **你不再为 NPC 写指令、写台词、决定他们的态度**
2. **你的工作是描述场景刺激（客观）+ 选 active 名单 + 给 NPC 标戏份位置**
3. **NPC 自己会决定怎么反应——你不应该预设他们的选择**
4. **场景刺激（per_npc_focus）必须是客观事实**，违例样例：
   - ❌ "你应该感到紧张" / "现在是你出手的时机" / "保持冷静"
   - ✅ "玩家直接对你说话" / "玩家拿走了你桌上的木匣"
5. **dramatic_intensity 标准**（给 LLM 几个例子，不写死规则）：
   - climax：玩家直面凶手 / 关键证据揭露 / 结局触发条件接近
   - high：玩家逼问 / NPC 受压 / 关键决策点
   - medium：常规调查 / 信息交换
   - low：闲聊 / 移动 / 旁观

### 5.6 per_npc_focus validator（防 pipeline 倒退）

新增 `engine/director_validator.py::check_focus_objectivity(focus_text)`：

扫 per_npc_focus 内容里出现指导性词汇即 warn + log（不阻塞）：

- 警示词列表：`["应该", "需要", "可以", "不要", "记得", "小心", "保持", "试图", "建议", "最好"]`
- log: `structlog.warn("director.per_npc_focus.directive_leak", npc=X, focus=Y, words=[...])`
- 跑批量后看 director 是不是稳定守住这条线；不稳定时考虑 retry director 调用

---

## 6. Selective Depth & NPC Tools

### 6.1 触发逻辑

| dramatic_intensity | NPC 调用方式 | 工具可用 | cap |
|---|---|---|---|
| low / medium | single thinking call | ❌ | — |
| high | single thinking call | ✅ | ≤3 tool calls |
| climax | reflect call → act call | ✅ 两步都可 | 每步 ≤3 tool calls |

### 6.2 NPC 工具集（4 个，全 sub-100ms 非 LLM）

定义在 `engine/npc_tools.py`：

```python
@dataclass
class NPCTool:
    name: str
    description: str
    handler: Callable[[str, dict, ToolContext], dict]  # (query, npc_state, ctx) → result
    max_calls_per_turn: int = 1
```

| 工具 | 描述 | 实现 |
|---|---|---|
| `recall_memory(query: str)` | 语义/关键字搜 NPC 自己的记忆 | `memory_manager.search_npc_memory(npc_name, query, top_k=3)` |
| `check_relationship(other_npc: str)` | 当前对 X 的 trust / mood / 最近一次互动 | 读 `game_state.npc_relations[other]` + voice anchor |
| `consider_intent_progress()` | 自己当前 goal / plan_stage / blocked_by / 最近 advance 时间 | 读 `game_state.npc_intents[self]` |
| `look_at(detail: str)` | 仔细观察场上某 NPC/物/地点的细节 | 读 `world_data.npcs/items/locations`，**但过滤"NPC 在场能合理察觉"** |

### 6.3 工具调用机制

走 LLM provider 的 native tool_use（同 director 现状）：

- NPC LLM call 启用时携带 4 个工具 + 1 个 sentinel `finalize_action(action: ...)`
- LLM 可以连续调几个工具，最后调 `finalize_action` 提交最终 action
- 单次 NPC 调用 cap：≤3 个 query 工具 + 1 个 finalize；超出强制 finalize
- 工具返回必须 terse（≤150 字 JSON），避免 context 膨胀

### 6.4 climax 模式：reflect + act 两步

```
step 1 reflect call:
  输入: scene_brief + per_npc_focus[self] + own state + 工具
  输出 (structured):
    {
      "stakes_analysis": "我面临什么 stake，最坏后果是什么",
      "options_considered": [
        {"action_type": "speak", "rationale": "..."},
        {"action_type": "act", "rationale": "..."},
        {"action_type": "withhold", "rationale": "..."}
      ],
      "chosen_strategy": "..."  // 不是具体 action，是策略描述
    }

step 2 act call:
  输入: step 1 的 chosen_strategy + 同上的 context + 工具
  输出: 标准 action object（§4.1）
```

step 1 失败（timeout / parse error）→ 直接走 step 2 baseline，跳过 reflect。
step 2 失败 → fallback 到 silent 占位 + warn。

### 6.5 cost / latency 预估

| 强度 | NPC 调用数 | 延迟增量 | cost 增量 |
|---|---|---|---|
| low/medium | 1 thinking | 0 | 1× |
| high | 1 thinking + ~2 tool | +5-10s（tool 是查询，cheap）| 1.1-1.3× |
| climax | 2 thinking + ~3 tool/each | +25-35s | 2.5-3× |

加权平均（70/25/5）：cost ≈ **1.15×** baseline，wall time ≈ **+5s** 平均。

---

## 7. Background NPC（L3 懒加载 + offstage_active）

### 7.1 3 层状态再申明

| 层 | offstage 时 | 触发机制 |
|---|---|---|
| **L1** 位置/日程 | 自动 | `world_clock.advance()` + npc.schedule lookup |
| **L2** 关于 NPC 的世界事实 | 自动累积 | info_propagation 规则 / event log / 别 NPC 的 dialogue 提及 |
| **L3** NPC 内心（intent/mood/plan） | 冻结（普通 NPC）或 实时（offstage_active） | catch-up call 或 offstage tick |

### 7.2 普通 NPC：懒加载（lazy catch-up）

NPC 再次进入 `active_npcs` 列表的回合，**先**跑 catch-up call **再**跑 action call：

```
catch-up call:
  输入:
    - last_active_round（NPC 上次活跃回合）
    - 当前 round
    - L2 累积事实摘要（自上次活跃后 info_items + event log 中提及该 NPC 的全部）
    - 该 NPC 上次活跃时的 L3 snapshot
    - 该 NPC 的 personality / secret / current_goal
  输出 (structured):
    {
      "what_i_did_offstage": "...",  // ≤80 字，narrator 可以选取作为"NPC 上次见后做了什么"的提示
      "intent_update": {...},        // §4.4 schema
      "mood_shift": {...},
      "knowledge_acquired": [        // 这段时间 NPC 学到的事
        {"content": "...", "source": "..."}
      ]
    }
  写入:
    - game_state.npc_intents[npc] update
    - game_state.npc_relations[npc].mood update
    - memory_entries 加 `knowledge_acquired` 条目（importance=medium，related_npc=self）
```

catch-up call cost: 单 thinking call。每个 session 平均估 3-5 次（NPC 重新激活次数）。

### 7.3 offstage_active：实时反应 + 定期 tick

director 输出的 `offstage_active: [C, D, ...]` 列表（≤3）：

- **事件触发**：以下事件 fire 时，list 内 NPC 立即各自跑一次单 NPC LLM update（不阻塞主 turn）：
  - 该 NPC 被 active NPC dialogue 中提及（"周世安做了 X"）
  - 该 NPC 关联的 event fire（"信件被发现"，落款=该 NPC）
  - 玩家 action 中提及该 NPC（玩家 `target_npc` 是该 NPC）
- **定期 tick**：每 5-8 轮（配置）跑一次单 NPC update，即使无事件
- **更新内容同 catch-up call schema**，但只覆盖自上次 update 以来的窗口

调度逻辑在 `engine/offstage_scheduler.py`，主 turn 流不等待 offstage update（fire-and-forget + 写 state）。

---

## 8. Orchestrator changes — DAG / priority / per-turn concurrency

### 8.1 全局 `npc_dialogue_sequential_enabled` 废弃

`config.py:104` 删除。NPC 之间的依赖每回合自决。

### 8.2 NPC 调用编排

```
1. director.run() → 拿到 active_npcs + scene_role + dramatic_intensity
2. 识别 newly_active = active_npcs - 上回合 active_npcs（差集）
   并行: catch-up calls for newly_active
3. 识别 needs_offstage_update = offstage_active 中触发条件命中的
   并行 + 不阻塞: offstage_active updates
4. 并行: active NPC action calls
   - 默认全部 asyncio.gather
   - DAG 解决"接话"需求：NPC 调用是 streaming，先到的 NPC dialogue 写入
     共享 buffer；后启动的 NPC 的 prompt 注入 `peer_dialogues_so_far`（已完成
     的 NPC 列表）。LLM 自己决定要不要"接话"——不需要显式 wait_for 声明
   - NPC action 输出的 `wait_for: X` 字段在**本回合**仅用于 narrator weave 排序
     提示（"我希望 narrator 把我放在 X 之后写"），不影响调用顺序；下回合 director
     可读到该字段作为该 NPC 想跟 X 互动的信号
   - 整体仍受 `npc_max_concurrency` (default 6) 上限
5. wait_all 完成
6. 校验每个 action（§4.3）+ 收集到 list
7. 按 priority 降序排序 → 传给 narrator weave
```

### 8.3 narrator weave 排序逻辑

```
sorted_actions = sorted(npc_actions, key=lambda a: a.priority, reverse=True)
```

narrator prompt 描述："以下 NPC actions 按重要性排序。weave 进 narrative 时，priority 高的更突出/更长篇幅；priority 低的可一句带过。observe / scheme 的 NPC 不渲染 hidden_note；observe 允许一句环境描写暗示在场，scheme 完全不出现（详见 §9.2）"。

### 8.4 取消 `npc_max_speakers_per_turn`

由 director 通过 `active_npcs` 自然限制（≤4）。不再砍 speakers cap。

### 8.5 narrator prelude 行为不变

继续与 NPC calls 并行（`narrator_early_stream_enabled = True`），减 TTFB。

---

## 9. Narrator Weave Changes

### 9.1 输入 schema 变化

| v1 | v2 |
|---|---|
| `npc_dialogues: {NPC: "对话内容"}` 简单 dict | `npc_actions: [Action]` 排序列表 |

每个 Action 已经按 priority 降序。

### 9.2 narrator prompt 改造要点

1. **消费 priority**：高 priority NPC 给更多 narrative 篇幅 + 更精细描写；低 priority 一句带过
2. **消费 action_type**：
   - `speak` → 直接引用 dialogue
   - `withhold` → 描写 NPC 沉默/敷衍/转移话题，可以引用敷衍 surface_reply
   - `act` → 描写 physical 动作，可加感官细节
   - `observe` → 不直接渲染 hidden_note 内容，但 narrator 可以用一句环境描写暗示 NPC 在场关注（"X 的目光扫过桌面"）；不能透露 NPC 学到了什么
   - `scheme` → 完全不在 visible narrative 出现；NPC 仿佛"未参与"本回合
   - `interject` → 描写"突然" / "打断"，priority 应高于被 interject 的 NPC
3. **消费 tone**：影响描写氛围（deceptive → "他平静地说，但眼神没看你"；vulnerable → "她的声音有些颤"）
4. **绝不"代写"玩家未做的动作**（#19/#25 关键规则）
5. **多步动作切分**（见 §11）

### 9.3 hidden_note / intent_update 不进 narrator

这些是 NPC internal state，narrator 只能看到 visible 部分（dialogue / physical / tone / target）。

---

## 10. Director ↔ Events_data 接通（#22）

### 10.1 当前问题

`script.events_data` 定义 5 个 event，每个有 trigger（如 `{"all_of": [...]}`）。当前 director 不消费这些 event，case_board 走 memory sync 通路，**events_data 形同虚设**。

### 10.2 改造

#### A. Director input 加 events progress

orchestrator 拼装 director input 时加：

```
script_events:
  fired: [event_id, ...]      # 已 fire 列表
  active: [                   # 未 fire 且 trigger 部分条件已满足的 event 摘要
    {
      "id": "evt_001",
      "name": "...",
      "description": "...",   # 简短
      "trigger_summary": "需要发现 X 物证 + NPC Y 进入 Z 地点",
      "progress": 0.6         # 触发条件命中度 0-1
    }
  ]
```

事件进度计算（`engine/event_progress.py`）：

- 解析 `event.trigger`（已有 `condition_tree.py` DSL）
- 对每个 leaf condition，查 GameState 当前是否 satisfied
- progress = satisfied_leaves / total_leaves

#### B. Director output 加 `event_fire_intent`

```jsonc
"event_fire_intent": ["evt_001", "evt_003"]
```

director prompt 加规则：

> 当前 script_events.active 列表里有事件接近触发（progress ≥ 0.7）时，**优先**把 active_npcs / per_npc_focus / scene_brief 写成能让这些 event 自然 fire 的样子。不要硬塞，要看玩家行动是否引向这里。
>
> 如果你判断本回合应该 fire 某 event，把 event_id 填进 event_fire_intent。orchestrator 会校验 trigger，不通过会 silent drop（你不会被罚）。

#### C. orchestrator 校验 + fire

```
for event_id in director.event_fire_intent:
    event = script_events[event_id]
    if event_id in fired:
        continue  # 已 fire
    if event.trigger evaluates True under current state:
        fire(event)  # 走现有 event_system path
    else:
        log "director_event_fire_rejected" + reason
```

#### D. director 主动比对 trigger（high-level）

director system prompt 末尾加一节：

> ## Script event tree 推进意识（仅 script 模式）
> 你不仅是场景调度，也是叙事弧线推进者。每回合扫一眼 script_events.active，
> 判断："这个 event 离触发还差什么？玩家的当前 action 是否让它接近触发？"
> 如果 case_board / 玩家行动正在朝某 event 触发条件汇聚，把 active_npcs /
> scene_brief 写成支持这个走向的方式（仍然客观描述场景刺激，不写指令）。

### 10.3 已有 event_system / condition_tree 复用

不重写。`event_system.check_events()` 继续负责"deterministic fire based on state"；新加的 `event_fire_intent` 只是"director 主动建议 fire"路径。两条路径并存：

- deterministic：state 满足 → 自动 fire
- intent-driven：director 建议 → 校验通过 → fire

---

## 11. 多步动作处理（#21）

### 11.1 问题

玩家输入"潜入工棚取木匣 → 藏入怀中携出工地 → 回大理寺再细察"3 步，narrator 把 3 步压成一段 montage，第 3 步被 NPC 抢做。

### 11.2 改造：`engine/action_segmentation.py`

```python
def segment_player_action(text: str) -> list[str]:
    """检测多步动作，返回拆分列表。

    检测规则（任一命中即视为多步）：
    - 出现 →/⇒ 箭头
    - "X 之后 Y" / "X 然后 Y" / "X 再 Y" 结构
    - 数字标号 "1. X 2. Y 3. Z"
    - 分号分隔且每段 ≥4 字

    返回:
        - 单步：[原文本]
        - 多步：[step1, step2, ..., stepN]
    """
```

### 11.3 orchestrator 处理多步

```
segments = segment_player_action(player_input)
if len(segments) == 1:
    走单步正常 turn
elif len(segments) > 1:
    本回合只执行 segments[0]
    剩余 segments[1:] 写入 game_state.pending_player_segments
    narrator weave 加规则: "玩家的后续动作（X / Y）尚未发生，本回合只演到 segments[0] 完成"
    director input 加 hint: "玩家声明了多步意图，本回合先演前 1 步，后续步骤由玩家在下回合主动推进"
```

下回合开始时：

- 如果玩家输入是空 / "继续"  / "下一步" → orchestrator pop `segments[1]` 作为本回合 player_input
- 如果玩家输入是新的实质内容 → 视为玩家放弃 pending segments，清空 + 走新 input

### 11.4 narrator prompt 加多步规则

> 如果玩家声明了 N>1 个动作（director input 会有 `multi_step: true` 标记），本回合**只演完玩家声明的第 1 个动作**。后续动作必须留给玩家在下个回合主动决定是否继续。绝不把后续步骤压成 montage 一次叙完，绝不让 NPC 替玩家完成后续步骤。

---

## 12. 玩家输入保护（#19 兜底）

### 12.1 问题

玩家弱输入（"环顾"/"再看看"，<12 字 / 无明确动作目标）时，NPC 的反向 suggestion 被 narrator 默认描成现实 → AI 代写玩家。

### 12.2 改造：`engine/player_input_guard.py`

```python
def assess_input_strength(text: str) -> dict:
    """返回:
        {
          "char_count": int,
          "is_weak": bool,           # char_count < 12
          "has_explicit_target": bool,  # 是否含具体名词目标
          "is_pure_observation": bool,  # 仅"看/环顾/观察" 等
        }
    """
```

### 12.3 弱输入时的连锁规则

`assess_input_strength().is_weak == True` 时：

1. **director input 加 hint**：`player_input_weak: true`
2. **director prompt 规则**：弱输入时——
   - `dramatic_intensity` clamp 到 ≤ medium（不能 high/climax）
   - `active_npcs` clamp 到 ≤ 1
   - `per_npc_focus` 里禁止暗示"NPC 主动行动"
3. **narrator prompt 规则**：弱输入时——
   - 主要描写环境 + 玩家 POV 感官细节
   - 可以反问玩家（"你想看什么？"）
   - 禁止描写 NPC 重大动作（说话/移动/给物等可以，重大转折不行）
   - 长度 cap 250 字

### 12.4 实施

`engine/player_input_guard.py::assess_input_strength()` 在 orchestrator `process_action` 第一步跑（moderation 之后、director 之前）；结果通过 `effective_memory_context` 注入 director + narrator。

---

## 13. Failure Modes & Validators

### 13.1 NPC 调用失败

| 失败 | 处理 |
|---|---|
| NPC LLM call 超时 / 流式中断 | 该 NPC 降级为 omitted 占位（参 §4.3，不进 narrator weave）+ structlog warn |
| NPC LLM 输出非法 JSON / 非法 action_type | 1 次 retry（同 #1 director 处理模式）；仍失败 → omitted + warn |
| NPC tool call 抛异常 | 该 tool 返回 `{"error": "..."}` + warn；NPC 可以继续决策 |
| NPC tool call 总数超 cap | 强制 finalize；如果 NPC 没主动 finalize → 走 baseline single-call |
| climax reflect call 失败 | 跳过 reflect，直接走 act baseline + warn |
| climax act call 失败 | omitted + warn（reflect 的 strategy 丢失） |
| catch-up call 失败 | NPC 用上次活跃时的 L3 snapshot 进 action call + warn |
| offstage_active update 失败 | silent log + warn，下次 tick 再补 |

### 13.2 Director 输出 validators

| 校验 | 失败 |
|---|---|
| `active_npcs` 含不存在的 NPC | drop 该名字 + warn |
| `active_npcs.length > 4` | 截到前 4 + warn |
| `per_npc_focus` 含 active_npcs 外的 key | drop + warn |
| `per_npc_focus` 缺 active_npcs 内的 NPC | 该 NPC focus 用默认值"在场" + warn |
| `scene_role` 同上 | 同上，默认 secondary |
| `event_fire_intent` 含 fired / 不存在 event | drop + warn |
| `offstage_active` 含 active_npcs 内 NPC | drop + warn（互斥） |
| `per_npc_focus` 出现指导性词汇（§5.6）| warn only，不阻塞 |

### 13.3 整 turn fallback

如果 director 完全 parse failure（现有 `DirectorParseError` 路径），orchestrator 走现有 #1 fix 的处理：yield SSE `llm_parse` error，让 UI 提示 "重试该回合"。

新架构**不引入新的整 turn 失败模式**——所有新机制（catch-up / offstage / tools / climax）失败都是局部降级。

---

## 14. Cost & Latency Budget

### 14.1 单回合 LLM 调用数预估

单位：`thinking` = 重模型调用（director / NPC / catch-up，~15-30s/call）；`cheap` = 轻模型调用（narrator / moderation，~3-10s/call）；`tool` = 工具查询（DB/state lookup，~50-200ms）。

| 阶段 | low/medium | high | climax |
|---|---|---|---|
| director (thinking) | 1 | 1 | 1 |
| catch-up (thinking, 若有 newly active NPC) | 0-2 平均 0.5 | 同 | 同 |
| active NPC action (thinking) | 3（3 NPC × 1 call）| 3 × 1 + 0-9 tool | 3 × 2 + 0-9 tool |
| offstage_active (thinking, fire-and-forget) | 0-3 平均 0.3 | 同 | 同 |
| narrator prelude (cheap) | 1 | 1 | 1 |
| narrator weave (cheap) | 1 | 1 | 1 |
| moderation in/out (cheap) | 2 | 2 | 2 |
| **thinking 小计** | ~4.8 | ~4.8 | ~7.8 |
| **cheap 小计** | 4 | 4 | 4 |
| **tool 小计** | 0 | ~6 | ~9 |
| **wall time 估算** | 80-100s | 90-110s | 130-160s |

加权（70/25/5）：avg ≈ **95s**（基本不变 vs 当前 97s），但**关键回合体验上升**。

主要节省来自：
- NPC 并行替 sequential：-30~60s/turn（高 intensity 抵消一部分，但平均仍省）
- 砍掉 npc_speech_order 协调开销：-1-2s/turn

主要新增：
- catch-up call: 平均 +0.5 thinking call/turn ≈ +10s
- offstage_active: fire-and-forget 不算 wall time

### 14.2 cost 预估

加权平均：
- 总 thinking calls 从 ~4.8/turn 升到 ~5.5/turn（+15%）
- 总 cheap tool calls：+2/turn 平均（每个 < $0.001 量级）

**当前真实成本未知**：dogfood 报告显示 $0.36/session 是因为多数 model 的价格表未填，`token_usage.cost_cents=0`（参 BUGS.md #26.1 的 root cause）。先填齐价格表（独立小工作）拿到真实 baseline，再外推 v2 cost。

**约束**：单 session 必须 ≤ `game_session_hard_cap_cost_cents=600` cents（$6）。如果 baseline 已经接近 $5，v2 +15% 会突破——届时需要：
- 降 climax 触发率（director prompt 调）
- 或 NPC 默认 baseline 不带 tool（仅 climax 用 tool）
- 或 catch-up 用便宜 slot（参 §16.1）

### 14.3 硬上限

- 单 turn LLM thinking calls 硬 cap = **15**（超过 → 强制 finalize + warn）
- 单 turn wall time 硬 cap = **180s**（超过 → SSE timeout error）
- 单 NPC 单 turn tool calls 硬 cap = **3**（已在 §6.3）
- single climax 调用预算 = **45s/调用**（超过 → 走 baseline fallback）

---

## 15. Migration & Rollout

### 15.1 老 session 兼容

`game_sessions.game_state` 是 JSON 列，新增字段全部由 `state_manager` 处理默认值，无 Alembic migration。

| 字段 | v1 状态 | v2 处理 |
|---|---|---|
| `npc_intents[npc]: NPCIntent dict` | 已存在 | 兼容，新 LLM 路径覆盖；rule-based advance 不再跑 |
| `npc_relations[npc]: {trust, mood, ...}` | 已存在 | 兼容不变 |
| `npc_locations` | 已存在 | 兼容不变（L1 层继续由 world_simulator 维护） |
| `last_active_round[npc]` | **新增** | 默认 `round_number - 1`（视为刚活跃，第一次 active 不跑 catch-up）|
| `pending_player_segments` | **新增** | 默认 `[]` |
| `offstage_event_log[npc]` | **新增** | 默认 `[]` |

→ **不需要 Alembic migration**，state schema 是 JSON，缺字段默认值在 `state_manager.GameState.from_dict()` 处理。

### 15.2 灰度切换

后端引入 feature flag：

```python
# config.py
runtime_architecture_v2_enabled: bool = False
```

- `False` → 走老 orchestrator / director / npc_agent
- `True` → 走新路径

灰度策略：
1. dev 环境先 `True` 跑 4-6 个 source × 3-5 round 验证不崩
2. dogfood batch 跑 3-5 session 看 Tier1/Tier2 分数 + 体感
3. VPS 灰度 50/50 跑 1 周，对比 metrics
4. 全切 + 删老路径（保留 1-2 周回滚窗口）+ 最终删除老代码

### 15.3 admin-frontend 影响

NPC schema 改了但 admin 不直接展示 NPC dialogue raw structure（admin 看的是 game session 的 message log 文本）。**admin-frontend 无需改动**。

### 15.4 frontend 影响

- play 页 narrator stream 不变（仍是 SSE text_delta）
- case_board / state_update SSE schema 不变（state_updates 字段没动）
- 唯一可能影响：弱输入回合 narrator 长度 cap 250 字，可能改变玩家长度预期——非破坏性

---

## 16. Open Questions & Deferred

### 16.1 设计阶段未拍板

| 项 | 推迟到 plan 阶段 |
|---|---|
| catch-up call 用什么 slot binding（复用 `npc_agent` slot 还是新开 `npc_catchup` 用便宜模型）| plan 阶段先用 `npc_agent` slot；如果 cost 显著，再考虑独立 slot |
| offstage_active 定期 tick 间隔（5/8/10/动态）| plan 阶段默认 7 轮，可调 |
| `wait_for` DAG 解析的死锁检测 | plan 阶段实现时加 cycle detect，命中 fallback 全并行 |
| narrator weave 的 priority 阈值（什么 priority 算"突出"）| 写 prompt 时跑批量 tuning，spec 不定死 |

### 16.2 后续 spec（不在本 spec 范围）

| 主题 | 单独 spec |
|---|---|
| Generation pipeline overhaul：name_critic / IP knowledge pack endings 重激活 / semantic_review / character builder prompt | TBD（#9/#16/#23/#24/#25-gen）|
| Task lifecycle / LLM throttle | TBD（#17/#20）|
| NPC LLM call 跨 session 全局限流（防 #20 throughput collapse 重现）| TBD |
| reflect call 输出 schema 是否进一步结构化（chain-of-thought 模板）| 看 dogfood 数据再说 |

---

## 17. 明确不在范围（防 scope 蔓延）

| 不做 | 理由 |
|---|---|
| 重写 narrator agent 整体 | 只改 weave 输入消费方式 + 多步规则；其它保留 |
| 重写 memory_manager / case_board / event_system | 这些消费新 schema 但内部不动 |
| Generation 工坊侧任何改动 | 独立 spec |
| 任务生命周期 reaper / LLM 全局 throttle | 独立 spec |
| NPC ReAct 多回合规划（如 NPC 跨 5 turn 实现一个阴谋的多步骤）| 当前 `intent_update.stage_index_delta` 已够用；后续看体感再加 |
| 改 game_session 表 schema | 新增的 NPC state 字段全在 game_state JSON 里，不需 Alembic migration |
| 改 frontend 主体 | 不需要 |
| A/B test framework | 用 feature flag + 手动跑批对比即可，不引入 A/B 平台 |

---

## 18. 验收标准（acceptance criteria）

写 plan 时按这些标准设计验证步骤：

### 18.1 功能验收

- [ ] director 不再输出 `npc_instructions` / `npc_speech_order` / `inform_npc_calls`，输出 v2 的 6 个新字段
- [ ] NPC 单次调用输出符合 §4.1 action schema，6 个 action_type 全可达
- [ ] 至少 1 个 dogfood session 出现 NPC 主动 `withhold`、1 个出现 `interject`、1 个出现 `scheme` + 后续回合该 scheme 兑现
- [ ] 串行模式开关 `npc_dialogue_sequential_enabled` 已删，NPC 默认并行
- [ ] 多步玩家输入触发 segmentation，连续 2 回合演完 2 步而非 montage
- [ ] 弱输入回合 dramatic_intensity ≤ medium 且 active_npcs.length ≤ 1
- [ ] script 模式 dogfood session 20 round 内至少有 2 个 event 通过 `event_fire_intent` 被 fire（替代当前 0 触发）
- [ ] offstage_active 名单内 NPC 在被 active NPC 指认后，下回合 catch-up（或 offstage tick）反映态度变化

### 18.2 质量验收（对比）

| 维度 | baseline（当前）| 目标 |
|---|---|---|
| Tier2 角色一致性平均分 | 4.5（5 sessions 估）| ≥ 4.5（不降） |
| Tier2 玩家选择影响平均分 | 3.0（#19 拖累）| ≥ 4.0 |
| BUGS #25 information-dump 实例 | 平均 3-4 次/20 round | ≤ 1 次/20 round |
| script 模式 director_outcomes event fire 次数 | 0/20 round | ≥ 2/20 round |
| avg turn wall time | 97s | ≤ 100s（基本不变） |

### 18.3 性能 / 稳定性验收

- [ ] dogfood 3 session × 20 round，0 个 turn 超 180s 硬 cap
- [ ] 0 个 turn 因新机制（catch-up / offstage / tools / climax）整 turn 失败
- [ ] cost 单 session ≤ $0.60（`game_session_hard_cap_cost_cents=600`）
- [ ] feature flag false 时老路径完全可用（回归测试）

---

## Appendix A — 关键文件改动清单

详细行级改动放到 plan，这里给文件层面 overview。

### 改写

- `backend/engine/director_agent.py` — DirectorResult dataclass 大改；`_coerce_*` 新增 active_npcs / per_npc_focus / scene_role / dramatic_intensity / offstage_active / event_fire_intent；删 npc_instructions / npc_speech_order / inform_npc_calls 字段处理
- `backend/engine/npc_agent.py` — 重写 `NPCAgent.run`：返回结构化 NPCAction 而非 NPCResult；支持 tools / climax 两步
- `backend/engine/orchestrator.py` — `process_action` 主流程重排：catch-up phase / offstage phase / parallel NPC phase / weave 输入改 list；删 sequential / parallel 分支
- `backend/engine/prompts.py` — DIRECTOR_TOOL v2 schema；build_npc_system 改成不接 instruction；新增 build_npc_action_tool（with tools）；build_narrator_weave_prompt v2
- `backend/engine/narrator_agent.py` — `stream` 接受 `npc_actions: list` 替 `npc_dialogues: dict`；多步规则注入
- `backend/engine/intent_system.py` — 废弃 `IntentSystem.advance()`；保留 NPCIntent dataclass

### 新增

- `backend/engine/npc_action.py` — NPCAction dataclass + validate_action()
- `backend/engine/npc_tools.py` — 4 个 tool 实现 + ToolContext + 注册表
- `backend/engine/npc_catchup.py` — catch-up call 实现（含 prompt 构建）
- `backend/engine/offstage_scheduler.py` — offstage_active fire-and-forget update 调度
- `backend/engine/player_input_guard.py` — assess_input_strength + apply guard hints
- `backend/engine/action_segmentation.py` — segment_player_action + pending segments helpers
- `backend/engine/event_progress.py` — compute_event_progress() for director input
- `backend/engine/director_validator.py` — per_npc_focus directive-leak check

### 测试

- `backend/tests/test_npc_action_schema.py` — 6 action_type 各自合法/非法 case
- `backend/tests/test_npc_action_validator.py` — §4.3 全部规则
- `backend/tests/test_director_v2_schema.py` — v2 字段解析 + validators
- `backend/tests/test_npc_catchup.py` — catch-up prompt 构建 + 输出消费
- `backend/tests/test_offstage_scheduler.py` — fire 触发条件 / 定期 tick
- `backend/tests/test_player_input_guard.py` — 弱输入识别 + clamp 行为
- `backend/tests/test_action_segmentation.py` — 多步识别 / 单步直通
- `backend/tests/test_event_fire_intent.py` — director intent → orchestrator 校验 → fire / drop
- `backend/tests/test_runtime_v2_e2e.py` — flag true 下跑通 mini turn（mock LLM）

### 配置

- `backend/config.py`:
  - 新增 `runtime_architecture_v2_enabled: bool = False`
  - 新增 `npc_offstage_tick_rounds: int = 7`
  - 新增 `npc_action_max_tools_per_call: int = 3`
  - 新增 `npc_climax_step_timeout_seconds: float = 45.0`
  - 删除 `npc_dialogue_sequential_enabled` / `npc_max_speakers_per_turn`（v2 启用后）

---

## Appendix B — 决策对照表

| 设计选择 | 选了什么 | 拒绝了什么 | 理由 |
|---|---|---|---|
| 顶层架构 | B（NPC 自决 + director 调度）+ selective depth | A（director 仍编剧）/ C（NPC ReAct 多 call）| A 不改 pipeline 本质，C 在叙事游戏延迟/cost 站不住 |
| action 空间 | 6 个枚举 + 通用字段 | 自由文本 / 多 action per turn | 枚举可校验 + 单 action 保证 narrator weave 可控 |
| director 简化 | 删 3 + 加 8（schema 更明确）| 完全保留 director 控制 / 完全砍 director | god mode 是问题根源；但 NPC 自决需要"舞台调度员"兜底 |
| selective depth 触发 | director 输出 dramatic_intensity | 自动检测（关键词 / arc 位置） | LLM 判断比规则灵活；不准确就 director prompt 调 |
| NPC 工具 | 4 个 cheap 查询 + 1 finalize | LLM-based 工具 / 更多工具（≥8）| cheap 工具是 agent feel 的高 ROI；多了 LLM 容易乱用 |
| 背景 NPC | 3 层 + 懒加载 + offstage_active | 定期批量 tick（A）/ 完全冻结（B）| 批量稀释质量；完全冻结违背 free 模式定位 |
| ordering | priority 自报 + wait_for DAG | director 决定顺序 / 全部并行 | director 决定违背 agency；全并行损失 NPC 接话 |
| intent_system | LLM 化 + dataclass 保留 | 完全删 / 保留 rule-based | rule-based 跟 agentic 调性矛盾；dataclass 还有用 |
| events 接通 | director event_fire_intent + 校验 | event 自动 fire / 不动 | 自动 fire trigger 太僵；director 判断更智能 |
| 多步动作 | 拆 turn + pending segments | narrator 内部分段 | 拆 turn 才能保证下一步玩家可以改主意 |
| 玩家保护 | input_guard clamp intensity / active_npcs / narrator 长度 | 完全禁 NPC 行动 / 不管 | clamp 保留弱输入回合的"反问/喘息"价值 |
| 灰度 | feature flag 50/50 灰度 | 全切 / 多阶段灰度 | 不上线，灰度只是为了对比 metrics，简单即可 |

---

## Appendix C — BUGS.md 更新协议（实施时遵守）

本 spec 覆盖的 BUG（#19 / #21 / #22 / #25-runtime）在实施中被修复时，**必须**回写 `experiments/local/BUGS.md`，方便日后追溯"这个 bug 是哪个 spec 的哪个改动解的"。

### C.1 流程

每修完一个 BUG（或一个 BUG 的某一子部分），同一个 commit 里一起：

1. **更新顶部索引表**：状态符号从 🟡 / 🔄 改成 ✅
2. **在该 BUG 的详细记录段末尾追加一节 `## 修复（YYYY-MM-DD）`**，内容用以下模板（保持精炼，3-6 行）：

   ```markdown
   ## 修复（2026-05-XX）

   **由 [spec §X.Y](../../docs/plans/runtime-architecture-overhaul-2026-05.md) 解。**

   关键改动：
   - `backend/engine/director_agent.py` 删 `npc_instructions` 字段（commit XXXXXXX）
   - `backend/engine/npc_agent.py` 重写 NPCAgent.run 输出结构化 action（commit XXXXXXX）

   验证：
   - 单测：`backend/tests/test_npc_action_schema.py`
   - dogfood：`runs/2026-05-XX_v2-validation/...` Tier2 玩家选择影响 score 4.2（vs baseline 3.0）
   ```

3. **不要删除原 BUG 描述**——后人需要"症状 + 根因 + 修复"完整链路

### C.2 跨 spec 的 BUG（部分修在本 spec、部分留给后续）

例：`#22 events_data 接通`本 spec §10 解了"director 主动 fire"路径；如果未来又出"trigger 条件 DSL 太严"的衍生 bug，新 spec 再加一节，**不修改本 spec 的 §10**，但在 BUGS.md 里追加新 `## 修复（YYYY-MM-DD, 增量）` 节。

### C.3 灰度期间 BUG 状态

灰度期间（feature flag 50/50）BUG 不算"已解"，因为老路径仍可能命中。索引表保持 🟡，详细记录追加 `## 灰度中（YYYY-MM-DD）` 节说明进展。全切（feature flag 默认 true 后老路径删除）后才标 ✅。

### C.4 写 plan 时把"更新 BUGS.md"列为 acceptance step

每个 task 完成后的 checklist 加一条：

```
- [ ] 同 commit 更新 experiments/local/BUGS.md 对应 BUG 的状态 + 追加修复节
```

未加这一条的 PR 不应该 merge。

---

**End of spec.** 写 plan 用 `superpowers:writing-plans`，覆盖 §18 验收标准 + Appendix C 协议。
