# NPC 模块技术说明

> 状态截至 2026-05-07。覆盖 Phase 0.A.3、1.A.5、1.B.2、1.B.4、Phase 2.D.3 + NPC reflection / 角色认知 / 情境感知 / Director inform_npc + **NPC-1 顺序对话 + NPC-2 持久 NPC↔NPC 关系（静态）** 全部落地后的形态。NPC-3（后台模拟）/ NPC-4（Director 关系编辑）暂未做，等 NPC-1/2 上线观察一周后再决定。

NPC 模块负责把世界中"非玩家角色"用 LLM 演活——既要按 Director 指令演戏，又要保持人格连贯、记忆合理、信息隔离、token 成本可控、并发可控。

## 1. NPC 能力矩阵

把"一个真实可信的 NPC 应该有什么"系统列出来，方便快速判断当前覆盖度。

### A. 角色认知（"我是谁"）

| 能力 | 状态 | 实现位置 |
|---|---|---|
| 名字 | ✅ | npc_name |
| 性格 | ✅ | personality |
| 秘密 | ✅ | secret，主动隐藏，逼问/高信任时透露 |
| 世界观/时代背景 | ✅ | world_setting → build_npc_system 稳定前缀 |
| 开局前的知识库 | ✅ | knowledge 字段 → build_npc_system 稳定前缀 |
| 长期内心总结 (reflection) | ✅ | 详见 §3.4 |
| 当前 intent / 目标 | ✅ | game_state.npc_intents → build_npc_system 可变后缀 |
| 角色身份/职业/年龄/外貌 | ❌ | schema 没专门字段，未来扩展 |

### B. 当前情境感知（"我在哪、什么时候"）

| 能力 | 状态 | 实现位置 |
|---|---|---|
| 当前时间 | ✅ | scene_context.current_time |
| NPC 自己当前在的地点 | ✅ | scene_context.my_location（按 schedule lookup） |
| 玩家当前在的地点 | ✅ | scene_context.player_location |
| 同场其他 NPC（公开身份） | ✅ | scene_context.peer_npcs（按 schedule 同 location 过滤；只传 personality 不传 secret） |

### C. 历史认知（"我经历过什么"）

| 能力 | 状态 | 实现位置 |
|---|---|---|
| 与玩家相关的记忆（cosine 召回） | ✅ | memory_entries + batch_query_npc_memories |
| 长期反思 reflection | ✅ | npc_reflections 表 + npc_reflection_service |
| 最近自己说过的话 (voice anchor) | ✅ | messages.npc_dialogues + get_npc_recent_utterances |
| 与其他 NPC 的关系（静态） | ✅ | npc_relations 表（A→B / B→A 各一行）+ get_npc_peer_relations |
| 与其他 NPC 的关系演变（动态） | ❌ | NPC-3 待做（玩家不在场时跑后台模拟，trust 累计变化触发 history rewrite） |
| 同场其他 NPC 本轮已说的话 | ✅ | NPC-1 顺序对话：peer_dialogues_so_far 注入 |

### D. 关系认知

| 能力 | 状态 |
|---|---|
| 与玩家 trust + mood | ✅ |
| 与其他 NPC 的初始关系（trust + label + history_summary） | ✅ NPC-2 |
| 与其他 NPC 的关系动态演变 | ❌ NPC-3 待做 |

### E. 行为约束

| 能力 | 状态 |
|---|---|
| 只输出对话和动作描写 | ✅ |
| 不替玩家做决定 | ✅ |
| 信任级别透露策略 | ✅ |
| NPC 主动行动（不只被动响应） | ❌ 产品决策待定 |
| NPC 输出能更新 game_state | ❌ 跟上一项配套 |

### F. 信息隔离（详见 §4）

| 能力 | 状态 |
|---|---|
| 不读 global recent_messages | ✅ |
| 只看 related_npc=自己 的 memory | ✅ |
| 不传 peer NPC 的 secret | ✅ |
| 同场 NPC 的 personality 截断到 60 字 | ✅ |
| 信息隔离原则系统文档化 | ✅ §4 |

### G. 性能与可观测

| 能力 | 状态 | 实现 |
|---|---|---|
| 廉价 slot | ✅ | npc_agent slot |
| 同 turn 多 NPC 调度 | ✅ | NPC-1 默认顺序（peak in-flight=1，看见前发言者）；flag 关掉退化为 asyncio.gather 并行 |
| stage.timing 埋点 | ✅ | npc_sequential / npc_parallel timing（按当前模式命名） |
| **NPC 并发信号量**（max 6） | ✅ | settings.npc_max_concurrency（仅并行 fallback 路径生效） |
| **NPC 同 turn 发言上限** | ✅ | settings.npc_max_speakers_per_turn（默认 3，控制顺序模式 wall-time） |
| **batch memory query**（修 N+1） | ✅ | batch_query_npc_memories |
| embedding 改异步（不阻塞 write） | ❌ | 全系统加固，Phase 2 处理 |
| NPC 输出质量指标 | ❌ |  |

### H. Director 协作

| 能力 | 状态 | 实现 |
|---|---|---|
| 接受 Director instruction | ✅ |  |
| **Director `inform_npc` 工具**（显式告知某事） | ✅ | DIRECTOR_TOOL.inform_npc_calls |

## 2. 整体数据流

```
玩家 action_text
     │
     ▼
Director (game_main slot)
   ├─ 决定 involved_npcs[]              ← 「卷入剧情的人」
   ├─ 决定 npc_speech_order[]           ← 「真正开口的人」（NPC-1，⊆ involved_npcs）
   ├─ 给每个 NPC 写 instruction
   ├─ 输出 memory_extracts (Director 视角的事实)
   └─ 可选：inform_npc_calls (显式植入某 NPC 的私有记忆)
     │
     ▼
Orchestrator 一次性 batch_query 所有 involved NPC 的 memory（N+1 已修）
     │
     ▼
为每个 involved NPC 准备完整上下文：
   ├─ npc_personality / npc_secret  ← world_data.npcs
   ├─ world_setting (base_setting)  ← world_data
   ├─ knowledge (开局前认知)        ← world_data.npcs[i].knowledge
   ├─ scene_context (time/location/peer_npcs) ← game_state + schedule
   ├─ current_intent (NPC 自己想做什么) ← game_state.npc_intents
   ├─ reflection (长期内心总结)     ← npc_reflections 表
   ├─ voice_anchor (最近 3 句自己的话) ← messages.npc_dialogues
   ├─ npc_memories (cosine 重排片段) ← 来自 batch_query
   ├─ peer_relations (NPC-2 跟身边人关系) ← npc_relations WHERE npc_a=self
   └─ trust / mood                  ← game_state.npc_relations
     │
     ▼
NPC Agent (npc_agent slot, 廉价档可选)
   ├─ NPC-1 顺序模式（默认）：按 npc_speech_order 串行 await
   │     每个后发言者注入 peer_dialogues_so_far=[前面所有人本轮已说的话]
   │     trim 到 settings.npc_max_speakers_per_turn（默认 3）
   │     未列入 speech_order 的 involved_npc 在场但不开口
   │  
   └─ Parallel fallback（flag 关掉时）：asyncio.gather + Semaphore(npc_max_concurrency=6)
     │
     ▼
Narrator
   └─ 把 scene_direction + npc_dialogues 织成叙事文本
     │
     ▼
GameService 写入：
   ├─ memory_entries  (Director extract → embedding → DB)
   ├─ memory_entries  (Director inform_npc_calls → director_told 类型)
   ├─ messages.npc_dialogues  (NPC 原话 → 供下轮 voice anchor)
   └─ asyncio.create_task → npc_reflection_service.maybe_reflect (新 memory ≥ 阈值时触发)

session 启动时一次性：
   GameService._seed_npc_relations
     ← world_characters.initial_peer_relations
     → npc_relations 表（双向写入；显式声明 win，未声明的反向按对称兜底）
```

## 3. 各能力详解

### 3.1 NPC 记忆隔离（Phase 0.A.3）

**问题：** 早期 NPC agent 直接拿 `recent_messages` 作为上下文，知道所有发生过的事——包括它本应不知道的（玩家私下跟其他 NPC 的对话）。

**解决：**
- NPC agent 调用时 `recent_messages=[]`
- 上下文只来自 `memory_entries WHERE related_npc=NPC名`
- `info_propagation` 系统的 `last-mile write` 给每个该知道的 NPC 各写一条 memory
- 双方互动事件通过 `write_dual_perspective_memories` 给两个 NPC 各写一条**视角不同**的记忆
- Director 可以显式 `inform_npc(npc, info)` 主动植入私有记忆（§3.8）

### 3.2 NPC 廉价 slot（Phase 1.A.5）

NPC 调用频次最高，任务相对简单（按指令演戏）。用独立 slot 绑廉价档模型，砍 ~30% cost。

`api/game.py::get_game_service` 解析 `npc_agent` slot，未绑定 fallback 到 `game_main`。

### 3.3 语义记忆召回（Phase 1.B.2 + 2.D.3 batch）

**Phase 1.B.2：** memory_entries 加 `embedding: list[float] | None` JSON 列，写入时调 OpenAI 兼容 embeddings；query 时拉 3× limit 候选 + cosine 重排。

**Phase 2.D.3 batch：** 一次 SQL 拉所有 involved NPC 的 memory（`related_npc IN (...)`），一次 embed query_text 复用给所有 NPC。彻底消除 N+1。

**配置：** `EMBEDDING_ENABLED=true` + base_url + api_key。失败统一 fallback 到 importance 排序，不阻塞游戏。

### 3.4 长期反思 / Reflection

**问题：** 即使有记忆隔离 + 语义召回，NPC 看到的还是离散的"事实条目"——没有"我作为这个角色一路走来的整体感"。长会话中容易性格漂移。

**解决（Stanford "Generative Agents" 模式）：** 给每个 NPC 维护持久的**第一人称内心总结**，当该 NPC 累积 ≥ 阈值（默认 5）条新 memory 时由 LLM 重新提炼。

**实现：**
- 表 `npc_reflections (id, session_id, npc_name, summary, last_memory_id, reflection_count, ...)`，UNIQUE(session_id, npc_name)
- `services/npc_reflection_service.py`: `should_reflect` / `reflect` / `maybe_reflect`
- 触发：game_service `_consume_turn` done event commit 后，对每个 involved NPC `asyncio.create_task` 启动，**用独立 db session**，SSE response 立即关闭、SessionLock 立即释放
- 注入：orchestrator `get_reflection` → `npc_agent.run(reflection=...)`
- prompt 段位置：稳定前缀末尾（cache 友好）
- 复用 `conversation_compression` slot（廉价档）

### 3.5 语气锚点 / Voice Anchor（Phase 1.B.4）

**问题：** 即使有 personality + reflection，长会话中具体措辞、口头禅、说话节奏仍可能漂移。

**解决：** 每次 NPC 发言前，把它**自己最近 3 句话**重新喂给它作为"voice 参照"。

**实现：**
- `messages.npc_dialogues` JSON 列存这一轮所有 NPC 的原话
- `memory_manager.get_npc_recent_utterances` 拉最近 ≤ 12 条 message + 过滤
- prompt 段位置：可变后缀

### 3.6 角色认知（世界 + 知识 + 性格）

NPC 必须知道**自己生活在什么世界、自己作为这个角色本就清楚什么事**——否则会"忘记自己是谁"。

**新增的 prompt 段（稳定前缀）：**
- **世界设定**（base_setting）：NPC 知道自己在民国还是赛博朋克
- **开局前知识库**（npc.knowledge JSON 列）：world creator 填的"该角色本就清楚的事"，比如"王福为老爷工作 30 年"

**信息隔离边界：** `script_setting`（剧本秘密如"凶手是 X"）**不传给 NPC**，只 Director 知道；NPC 通过 Director 的 instruction 决定本轮该露多少。

### 3.7 情境感知（time / location / peer NPCs / intent）

NPC 必须知道**当下身处的场景**——时间、地点、身边有谁、自己心里想做什么。

**新增的 prompt 段（可变后缀）：**
- **当前场景**：current_time + my_location（按 NPC schedule lookup）+ player_location（如果不同位置则提示）+ peer_npcs（同场其他 NPC 的 name + 截断后的 personality，**不带 secret**）
- **当前 intent**：来自 `game_state.npc_intents[name]`（intent_system 已计算）—— current_goal + urgency + plan_stage + blocked_by

intent 段告诉 NPC "你心里此刻最想做的事"，让对话更有"目的性"。

### 3.8 Director `inform_npc` 工具（Phase 0.A.3 余项）

**用途：** Director 可以通过 `inform_npc_calls: [{npc, info, importance}]` 显式把某事写入某个 NPC 的私有记忆。适用于：
- NPC 应该意识到某事但场景里没机会自然得知（远处发生的事、有人偷偷告诉了 TA）
- Director 想强行植入一个反应触发点

**实现：**
- DIRECTOR_TOOL.input_schema 加 `inform_npc_calls` 字段
- DirectorAgent `_coerce_inform_npc_calls` 校验 + 归一化 importance
- orchestrator 把每条转成 `memory_entry(related_npc=npc, memory_type=director_told)`，加入 dual_memory_entries 走已有写入路径
- **拒绝指向不存在的 NPC**（防止 Director 幻觉造名字污染数据）

**信息隔离仍然有效：** `inform_npc(王福, info)` 只写王福一条记忆，不会泄露给其他 NPC。

### 3.9 NPC 并发信号量（Phase 2.D.3）

`settings.npc_max_concurrency`（默认 6）通过 `asyncio.Semaphore` 限制单 turn 内 NPC LLM 同时调用数。NPC 数 > 上限时排队执行，避免 provider rate limit / connection pool 爆炸。Sem 在每个 process_action 内独立，不跨 session。

### 3.10 NPC-1 顺序对话（同 turn 多 NPC 接话）

**问题：** 多 NPC 同场时之前是 `asyncio.gather` 并行调用——每个 NPC 各自独立 monologue，互相看不见对方说什么。"赵姐说茶刚泡好"和"王福说今儿话怎么少"是平行宇宙。

**解决：** Director 在 `npc_speech_order` 字段决定本轮**真正开口**的人和顺序；orchestrator 串行 await；每个后发言的 NPC 在 system prompt 里看到前面所有 NPC 本轮已说的话。

**Director 的智能空间（关键，避免"无脑接力"）：**
- `involved_npcs` = 「本轮卷入剧情的人」；`npc_speech_order` = 「本轮真正开口说话的人」——**两者不一定相等**
- 想让某 NPC 在场但沉默观察，就把 TA 放进 `involved_npcs` 而**不放进** `npc_speech_order`
- Director prompt 已明确引导："默认偏好 1-2 个发言者；只在真正的群戏（多人争吵、议事、围观冲突）才让 ≥3 个开口"
- Director prompt 还引导用关系制造张力："如果 NPC A 跟 NPC B 关系紧张/暧昧，让两人对话顺序产生张力（A 先开口 → B 才表态）"

**NPC 的智能空间（避免"硬挤台词"）：**
- NPC system prompt 行为规则**明确把"沉默"列为合法选择**："如果你这个角色此刻没什么想说的（性格内向、心怀戒备、忙着别的事、被讨论的话题跟你无关），可以只输出一句动作描写（如「默默续了杯茶」），或者直接输出空字符串"
- 还明确禁止"礼貌接龙"："你的发言要符合「这个角色此刻真正会说的话」，不是「礼貌地回应每一个被提到的话题」"
- 空 dialogue 在 orchestrator 被跳过（不写入 npc_dialogues 也不污染下一个 NPC 的 peer_dialogues_so_far）

**实现：**
- `prompts.DIRECTOR_TOOL.input_schema.npc_speech_order: list[str]`：必须 ⊆ involved_npcs
- Director system prompt §「谁开口、按什么顺序」段引导 LLM 善用 speech_order
- `DirectorAgent._coerce_speech_order` 过滤掉幻觉 / 重复 / 不在 involved_npcs 的名字
- `orchestrator.process_action` 顺序 await：每次把 `peer_dialogues_so_far=[{npc_name, dialogue}]` 注入下一个 NPC；空 dialogue 不累积
- `build_npc_system` 可变后缀加段「## 本轮其他人已经说过的话」（仅非空时显示）+ 稳定前缀行为规则加「沉默是合法选择」+ 「不要为了必须接话而硬挤台词」
- `settings.npc_dialogue_sequential_enabled` flag（默认 True，关掉退化为并行 gather）
- `settings.npc_max_speakers_per_turn` 硬上限（默认 3）：Director 没 trim 时由 orchestrator 兜底，避免 wall-time 失控

**信息隔离：** peer_dialogues_so_far 只含真实说出口的台词；不传 peer 的 intent 内心、reflection、memory。

**跟 1.A.1 narrator 早流式协调：** NPC 队列整体仍跟 prelude 并行（asyncio.create_task 包整个 sequential runner），prelude 内的 NPC 文字仍然是占位 → narrator weave 阶段织入真实 dialogue，跟之前结构一致。

**已替代 1.A.2 speculative parallel**（从未实现，本次彻底废弃）。

### 3.11 NPC-2 持久 NPC↔NPC 关系（静态）

**问题：** schema 里只有"NPC 跟玩家"的 trust/mood，没有"NPC 跟 NPC"的关系。开局所有 NPC 之间都是空白页。

**解决：** 新表 `npc_relations` 存有向关系（A→B 和 B→A 各一行）；`WorldCharacter.initial_peer_relations` 由 world creator agent 在创世时填，session 启动时双向灌入；NPC system prompt 加段「## 你跟身边人的关系」。

**实现：**
- 表 `npc_relations(session_id, npc_a, npc_b, trust SMALLINT, relationship_label, history_summary, last_event_round)`，UNIQUE (session_id, npc_a, npc_b)
- `WorldCharacter.initial_peer_relations: list[{target, trust, label, history_summary}] | None`
- `world_creator_agent` CHARACTERS_TOOL.input_schema 加字段 + few-shot 引导（"0-3 条即可，不要每个都写满；trust 反映的是你怎么看 TA，不是 TA 怎么看你"）
- `services.world_creator_agent._normalize_peer_relations` 校验：trust 硬限 [-10, 10]，丢空 target / 非 dict / 数值无效条目
- `GameService._seed_npc_relations` 在 start_game commit 之后执行：
  - 显式写入：每个 NPC 的 initial_peer_relations 写一行 (npc=自己, target=对方)
  - 反向兜底：仅在对方没显式声明对应 (B, A) 时，按 (A, B) 对称复制一行 → 保证单向关系（A 暗恋 B 但 B 不知道）也能表达
  - 过滤 target 必须 ∈ NPC roster（玩家 / 幻觉 / 自指都丢）
- `MemoryManager.get_npc_peer_relations(db, sid, npc_name)` 仅返回 `npc_a == npc_name` 行（A→? 方向）
- orchestrator 为每个 involved NPC 拉一次（N+1，但 NPC 数 cap 3，可接受），传入 `peer_relations` 参数
- `build_npc_system` 稳定前缀（reflection 之前）加段「## 你跟身边人的关系（你内心如何看待他们；TA 怎么看你不一定相同，你不知道）」
- `settings.npc_peer_relations_enabled` flag（默认 True，关掉跳过整个路径）

**信息隔离（关键，必测）：**
- A 的 prompt 只含 A→? 方向行 — 反向 trust（B→A）**永远不返回**
- A 的 prompt 不含其他 NPC 之间的关系（B→C）
- prompt 里明确告诉 NPC「TA 怎么看你不一定相同，你不知道」，强化 LLM 行为

**NPC-3 / NPC-4 未做：** 关系是 read-only 的——session 启动后 npc_relations 永远不会变。trust 不会随事件累积，history_summary 不会重写，玩家不在场时不会跑后台模拟。这些是 NPC-3/NPC-4 的范围，先看 NPC-1+2 上线效果再开。

### 3.12 batch memory query（Phase 2.D.3）

`memory_manager.batch_query_npc_memories(db, sid, [npc_names], query_text=...)`：
- 一次 SQL `WHERE related_npc IN (...)` 拉所有候选
- Python 端按 NPC 分组（每 NPC 取 3× limit 候选）
- query_text 只 embed 一次，复用给所有 NPC 的 cosine 重排
- 返回 `{npc_name: [memory_dict]}`

orchestrator 只调一次 batch_query，N+1 消除。

## 4. 信息隔离原则（NPC 该看什么 / 不该看什么）

这一节是核心安全契约。**新增能力时必须对照这张表确认是否破坏隔离**。

### ✅ NPC 应该看到的（在 NPC system prompt 里）

| 类别 | 内容 | 来源 |
|---|---|---|
| 自己 | name, personality, secret, knowledge | world_data.npcs[self] |
| 世界 | base_setting | world_data.base_setting |
| 长期内心 | reflection (我自己的总结) | npc_reflections |
| 短期记忆 | memory_entries WHERE related_npc=self | DB (按 cosine 重排) |
| 自己的话 | voice anchor 最近 3 句自己的台词 | messages.npc_dialogues |
| 当前场景 | time, my_location, player_location, peer_npcs（仅 name + 截断 personality） | game_state + schedule |
| 自己的 intent | current_goal / urgency / plan_stage / blocked_by | game_state.npc_intents[self] |
| Director 指令 | 本轮该如何回应 | director_result.npc_instructions[self] |
| 与玩家关系 | trust + mood | game_state.npc_relations[self] |
| **跟其他 NPC 的关系**（A→B 的 trust + label + history_summary） | NPC-2 | npc_relations WHERE npc_a=self |
| **本轮其他 NPC 已说的话** | NPC-1 | peer_dialogues_so_far（顺序模式按发言顺序累积） |

### ❌ NPC 不应该看到的（必须排除）

| 类别 | 为什么 | 当前如何排除 |
|---|---|---|
| `recent_messages` 全文 | 含玩家私下跟其他 NPC 的对话 | NPC agent 调用时 `recent_messages=[]` |
| 其他 NPC 的 secret | 那是别人的私事 | scene_context.peer_npcs 只取 personality |
| 其他 NPC 的 knowledge | 角色不会先验知道别人知道什么 | 只传 self.knowledge |
| 其他 NPC 的 reflection | 那是别人的内心 | get_reflection 只查 self |
| **反向 trust**（B→A 的数值） | 角色不应通灵知道别人怎么看自己 | get_npc_peer_relations 只查 npc_a=self |
| **其他 NPC 之间的关系**（C↔D） | 旁观者不应知道别人之间的事 | 同上（query 限定 npc_a=self） |
| **其他 NPC 的 intent.current_goal** | 不能直接读他人内心 | scene_context.peer_npcs 只取 name+personality |
| script_setting（剧本核心秘密） | 上帝视角，会破坏剧情 | NPC system prompt 不包含此字段 |
| 完整 ending_conditions | 上帝视角 | 同上 |
| case_board（案件板） | 玩家工具，NPC 不该有 | 不传 |
| 玩家在它不在场时的行动 | 无法知情 | memory_entries 通过 info_propagation 控制 |
| 完整 world_data.npcs | 含所有 NPC 的 secret | 只传 self + 同场 peer 的公开 personality |

### 🟡 灰色区域 / 设计决策

| 类别 | 当前处理 | 备注 |
|---|---|---|
| 玩家 user_input 的内容 | NPC 通过 Director instruction **间接**得知 Director 想让它如何回应；不直接看 user_input | 故意如此——保持 Director 中央调度权威 |
| 同场 NPC 的"存在" | 当前传 peer_npcs (name + 截断 personality)，**不传 peer 的当前 intent** | 如果想让 NPC A 感知 NPC B 在做什么，要 Director 显式 inform |
| Director `inform_npc` 任意写入 | 当前会校验 NPC 名存在，但不校验内容真实性 | Director 可以 inform 一个错的事实——这是 by design 让 Director 有戏剧操作空间 |

### 信息隔离的"添加新 prompt 段"流程

如果以后想给 NPC 加新信息源，按这个 checklist 走：
1. **这条信息 NPC 在角色内本应知道吗？** 是 → 可以加；否 → 停。
2. **加这条会让 NPC 知道其他 NPC 的 secret / 玩家私场景 吗？** 会 → 重新设计；不会 → 继续。
3. **放稳定前缀还是可变后缀？** 不变量（性格/世界/规则/持久关系）→ 前缀；本轮才有意义（情境/记忆/指令/peer_dialogues）→ 后缀。
4. **加测试覆盖"NPC 不知道它不该知道"的反向 case**。
5. **对 NPC↔NPC 信息（关系 / 对方在场说的话），同时检查反向是否泄露**（NPC-2 加的规则：A 拉到的 peer_relations 不能包含 B→A 或 B→C）。
6. **更新本文档 §1 能力矩阵 + §4 隔离表**。

## 5. NPC system prompt 完整结构

按 cache 友好原则 [稳定前缀] + [可变后缀] 切分：

```
[稳定前缀]                    ← DeepSeek 等 provider 的 prefix-cache 命中
你是 {npc_name}…

## 你所在的世界
{base_setting}

## 你的性格
{personality}

## 你已知的事（开局前的认知）
- {knowledge item 1}
- {knowledge item 2}

## 你的秘密
{secret}                     ← 只在有 secret 时

## 你跟身边人的关系           ← NPC-2，只在有 peer_relations 时
- 赵姐（邻居）：你对 TA 信任 6/10，邻居 30 年常来借米
- 老爷（雇主）：你对 TA 信任 -3/10

## 你最近的内心总结           ← 只在有 reflection 时
{reflection.summary}

## 行为规则
- 只输出对话和动作描写
- 保持角色性格一致
- 不要替玩家做决定
- 不要输出任何状态更新或工具调用
- 如果本轮已有人发言，你必须像真的在场听见一样——可以接、回、反驳、附和、转移话题，也可以装没听见，但不要复读
- 【沉默是合法选择】此刻没什么想说的就输出一句动作描写或空字符串，不要为了"必须接话"硬挤台词
- 你的发言要符合「这个角色此刻真正会说的话」，不是「礼貌地回应每一个被提到的话题」

[可变后缀]                    ← 每轮可能变
## 当前场景
- 时间：第N天·上午
- 你目前在：茶摊
- 玩家此刻在：（如果不同位置才显示）
- 跟你在同一处的人：赵姐（热心，爱八卦）、李掌柜

## 你心里在意的事             ← 来自 npc_intents
- 你心里此刻最想做的事：把玩家试探出来（紧迫程度 7/10）
- 你正处在「准备」阶段
- 但你被「玩家拦着」挡住    ← 只在 blocked_by 非空时

## 本轮其他人已经说过的话    ← NPC-1 顺序模式，只在有 peer_dialogues_so_far 时
- 赵姐：「茶刚泡好。」
- 李掌柜：「他今儿话怎么少。」

## 你最近说过的话             ← voice anchor
- 「最新一句」
- 「上一句」
- 「再上一句」

## 你的记忆
- [第N轮] ...

## 你与玩家的关系
- 信任度：N/10
- 当前情绪：xxx
- 【信任级别行为指引】...

## 导演指令
{director instruction}
```

NPC 收到的 user message 极简：`{"role": "user", "content": f"导演指令：{instruction}"}`——**绝不传 recent_messages**（隔离原则）。

## 6. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/engine/npc_agent.py` | NPCAgent 主类 |
| `backend/engine/orchestrator.py::process_action` | NPC tasks 构造、batch query、semaphore、并行 gather |
| `backend/engine/prompts.py::build_npc_system` | NPC system prompt 构造 |
| `backend/engine/memory_manager.py` | `query_npc_memories` / `batch_query_npc_memories` / `get_npc_recent_utterances` / `attach_embeddings` |
| `backend/services/npc_reflection_service.py` | reflection 触发与生成 |
| `backend/services/embedding_service.py` | embedding 调用 + cosine |
| `backend/services/game_service.py::_consume_turn` | memory write + reflection 异步触发 + Message.npc_dialogues 写入 |
| `backend/engine/director_agent.py` | DirectorResult.inform_npc_calls + `_coerce_inform_npc_calls` |
| `backend/models/memory.py` | MemoryEntry（含 embedding 列） |
| `backend/models/npc_reflection.py` | NPCReflection |
| `backend/models/npc_relation.py` | NPCRelation（NPC-2 持久关系） |
| `backend/models/game.py::Message` | Message（含 npc_dialogues 列） |
| `backend/models/world.py::WorldCharacter` | knowledge + initial_peer_relations 字段 |
| `backend/services/game_service.py::_seed_npc_relations` | 双向灌入 npc_relations |
| `backend/services/world_creator_agent.py::_normalize_peer_relations` | LLM 输出归一化 + trust 硬限 |

## 7. 配置项汇总

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `NPC_REFLECTION_ENABLED` | `true` | 是否启用长期反思 |
| `NPC_REFLECTION_THRESHOLD` | `5` | 累积多少条新 memory 触发反思 |
| `NPC_MAX_CONCURRENCY` | `6` | 单 turn 内 NPC LLM 同时调用上限（仅并行 fallback 路径） |
| `NPC_DIALOGUE_SEQUENTIAL_ENABLED` | `true` | NPC-1 顺序对话总开关，关掉退化为并行 gather |
| `NPC_MAX_SPEAKERS_PER_TURN` | `3` | NPC-1 单 turn 发言上限，超出由 orchestrator 兜底 trim |
| `NPC_PEER_RELATIONS_ENABLED` | `true` | NPC-2 总开关，关掉跳过 seed/query/prompt 注入 |
| `EMBEDDING_ENABLED` | `false` | 是否启用语义召回 |
| `EMBEDDING_BASE_URL` | `""` | OpenAI 兼容 embeddings 端点 |
| `EMBEDDING_API_KEY` | `""` | embedding 服务 API key |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | embedding 模型名 |
| `EMBEDDING_DIM` | `1536` | embedding 向量维度（仅文档用） |
| `EMBEDDING_TIMEOUT_SECONDS` | `5.0` | 单次 embedding 调用超时 |

| Slot | 模型档位 | 用途 |
|---|---|---|
| `npc_agent` | 廉价档（可选） | NPC 对话；未绑定 fallback 到 `game_main` |
| `conversation_compression` | 廉价档 | 同时被 reflection 复用 |

## 8. 数据库 schema（NPC 相关）

```sql
-- Phase 0.A.3 / 1.B.2
memory_entries (
  id, session_id, memory_type, content, round_number, importance,
  related_npc,                -- 0.A.3: 隔离锚点
  embedding JSON,             -- 1.B.2: nullable，semantic 召回
  created_at
)
INDEX (session_id, related_npc)

-- Phase 1.B.4
messages (
  ...,
  npc_dialogues JSON,         -- {npc_name: dialogue}，仅 assistant 消息
  ...
)

-- Reflection
npc_reflections (
  id, session_id, npc_name, summary,
  last_memory_id,             -- 上次反思覆盖到的最大 memory_entries.id
  reflection_count,
  created_at, updated_at
)
UNIQUE (session_id, npc_name)

-- NPC-2 — 持久 NPC↔NPC 关系（有向；A→B 跟 B→A 各一行）
npc_relations (
  id, session_id, npc_a, npc_b,
  trust SMALLINT,             -- [-10, 10]，硬限
  relationship_label,         -- 「邻居」「上司下属」「情敌」...
  history_summary,            -- 一句话过去摘要，nullable
  last_event_round,           -- NPC-3 用，NPC-2 起步永远 0
  created_at, updated_at
)
UNIQUE (session_id, npc_a, npc_b)
INDEX (session_id, npc_a)

-- 已有但本次接入了 prompt 的字段
world_characters.knowledge JSON                -- 开局前角色本就清楚的事
world_characters.initial_peer_relations JSON   -- NPC-2，session 启动时灌入 npc_relations
```

## 9. 已知短板与未来扩展

### NPC 群像 NPC-3 / NPC-4 待观察后再做

**`docs/superpowers/specs/2026-05-06-npc-group-interaction.md`** —— NPC-1（顺序对话）+ NPC-2（持久 NPC↔NPC 关系静态部分）已落地 2026-05-07。剩余：

- **NPC-3** 后台模拟：NPCIntent.target_npc / target_action + world_simulator tick 在玩家不在场时生成 NPC↔NPC 事件、按 deterministic 规则 (+1/-2/-5/+5) 累积 trust、阈值触发 LLM 重写 history_summary
- **NPC-4** Director 关系编辑：DIRECTOR_TOOL.npc_relation_updates 让 Director 显式调整关系

**为什么暂不做：** trust delta 规则、history rewrite 阈值都是凭直觉拍的——在 NPC-1+2 上线一周后看真实数据再调参更靠谱。本身工作量 4h，等观察期满后单次会话连做。

### P2 其他待做

- **NPC 主动行动 / 能更新 game_state**：当前 NPC 只被动响应 Director instruction。需要新机制 + 重新设计 Director 中央调度边界
- **embedding 异步 + race 处理**：当前写入时同步阻塞 5s；改异步要解决"写没完读就来"的 race
- **角色身份/外貌字段扩展**：schema + 创作工坊 + 前端显示
- **NPC 输出质量指标**：多少 NPC 实际有 dialogue / 多少返回空 / reflection 触发率

### P3 长期愿景

- **跨 session 的"角色档案"**：同一 NPC 在不同玩家的不同局里有性格延续性（user_id × npc_id 维度持久档案）
- **LLM-as-judge 自动评估 NPC 表演质量**

## 10. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_npc_agent.py` | NPCAgent 基础 streaming |
| `tests/test_orchestrator.py` | NPC 不收 global recent_messages（信息隔离回归） |
| `tests/test_orchestrator_npc_slot.py` | 廉价 slot 路由 + fallback |
| `tests/test_memory_semantic_recall.py` | cosine 重排 + fallback 路径 |
| `tests/test_memory_batch_query.py` | batch query 分组、单次 embed、limit |
| `tests/test_embedding_service.py` | embedding service 失败兜底、cosine 数学 |
| `tests/test_npc_reflection.py` | should_reflect 阈值、reflect 创建/更新、LLM 失败兜底 |
| `tests/test_npc_voice_anchor.py` | get_npc_recent_utterances + prompt 注入 |
| `tests/test_npc_world_awareness.py` | world/knowledge/scene/intent 4 段渲染 + stable prefix 分层 |
| `tests/test_npc_concurrency_semaphore.py` | semaphore 限制并发 peak（顺序模式下显式关 sequential flag） |
| `tests/test_director_inform_npc.py` | inform_npc_calls 写 director_told memory + 拒绝未知 NPC |
| `tests/test_npc_sequential_dialogue.py` | NPC-1：speech_order 驱动调用顺序；后发言看见前发言；peak in-flight=1；max_speakers cap；flag 关闭回退并行；coerce 过滤幻觉 |
| `tests/test_npc_peer_relations.py` | NPC-2：双向 seed + 显式不对称 + trust clamp + 非法 target 丢；get_npc_peer_relations 信息隔离（不暴露反向 / C↔D）；prompt 段渲染 |

## 11. 故障排查

| 现象 | 可能原因 | 排查 |
|---|---|---|
| NPC 总是说类似的话 / 角色感弱 | reflection / voice anchor 没生效 | 查 structlog `npc_reflection.updated`；查 `messages.npc_dialogues` 是否有数据 |
| NPC 说出穿越年代的话（民国说"app"） | world_setting 没传 | 确认 `world_data.base_setting` 非空；prompt 里有 "你所在的世界" 段 |
| NPC 不知道身边谁在 | scene_context 没传 / NPC schedule 没配 | 确认 npc.schedule[time_slot] 有值；orchestrator 计算 my_location 正确 |
| NPC 召回的记忆与玩家话题不相关 | embedding 没启用 | `EMBEDDING_ENABLED=true` + 配置 API；查 `embedding.failed` / `embedding.timeout` |
| reflection 从来不触发 | 阈值偏高 / 没新 memory | 查 `npc_reflection.updated` 日志；调低 `NPC_REFLECTION_THRESHOLD` |
| done 事件后 SSE 卡住 | reflection 阻塞主流程 | 确认是 `asyncio.create_task` + `async_session()`；查 `npc_reflection.background_task_failed` |
| NPC 知道了它不该知道的事 | 信息隔离漏洞 | 检查是否在某处把 `recent_messages` 传给了 NPC；按 §4 表对照 |
| 多 NPC 场景 LLM rate limit 超 | 信号量没生效 | 检查 `NPC_MAX_CONCURRENCY` 配置；测试 `test_npc_concurrency_semaphore.py` 是否仍 PASS |
| Director inform_npc 没写入 | 指向不存在的 NPC 名 | 查 `director_inform_npc_unknown` warning 日志 |
| NPC 不知道自己刚才在做什么 | npc_intents 为空 | 确认 intent_system 在 init 时填充；free 模式下可能空 |
| 多 NPC 场景轮流刷屏，每人一句没意义台词 | Director 没用 npc_speech_order 筛人 / NPC prompt 没生效 | 查 Director 输出的 speech_order 是否短于 involved_npcs；查 NPC prompt 是否含「沉默是合法选择」段 |
| 后发言的 NPC 看不见前发言者的话 | NPC-1 flag 关了 / 走了并行 fallback | 查 `stage.timing` 的 stage 是 `npc_sequential` 还是 `npc_parallel`；查 `settings.npc_dialogue_sequential_enabled` |
| NPC 不知道跟某个 NPC 的过去关系 | initial_peer_relations 没填 / seed 失败 / 隔离过严 | 查 world_characters.initial_peer_relations；查 npc_relations 表 session_id 是否有行；prompt 里有「你跟身边人的关系」段吗 |
| Director 列了 5 个 NPC 但只有 3 个出现 | orchestrator 兜底 trim 到 npc_max_speakers_per_turn | 默认行为；如果想多发言改 `NPC_MAX_SPEAKERS_PER_TURN` 或让 Director 自己 trim |
| NPC 接话像礼貌接龙、性格不鲜明 | 廉价 slot 模型表达力不够 / Director instruction 太泛 | 试试把 `npc_agent` slot 升档；Director instruction 给具体行为指引（不是「回应玩家」而是「冷淡敷衍想结束话题」） |
