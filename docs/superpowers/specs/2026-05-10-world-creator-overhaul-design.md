# 世界 / 剧本生成 Agent 大改造 · Design Spec

> 起草：2026-05-10
> 状态：草案，等用户 review
> 配套：
> - `docs/modules/world-creator.md`（现状能力矩阵，**不替换**，本 spec 改造完后回头补 v2 章节）
> - `docs/modules/orchestrator.md` / `docs/modules/npc.md`（运行时接入面）
> - `backend/services/world_creator_agent.py`（主改造对象，2406 行）
> 单 spec 只列**改造方案 + 决策依据**，不复述现有架构。

---

## 0. 起点核对

### 0.1 现有产物结构（v1）

| 字段 | 来源阶段 | 形态 |
|---|---|---|
| `base_setting` | world_base | 散文（300-600 字） |
| `free_setting` | world_base | 3-5 条张力 |
| `locations` | world_base | 5-10 个 `{name, description}` |
| `characters / npcs` | characters | 单次 LLM 输出全部 NPC（`personality / secret / knowledge / schedule / initial_location / initial_peer_relations`） |
| `playable` | playable | characters 子集 |
| `events_data` | script 阶段 | **仅 script 模式有**，自由模式 world 没有 |
| `endings_data` | script 阶段 | 同上 |

### 0.2 五个被确认的瓶颈

| # | 瓶颈 | 后果 |
|---|---|---|
| ① | **角色规模天花板**：单次 LLM 输出 ≤4-8K token，整 schema 算下来约 8-12 个完整 NPC 顶天 | IP 复刻时支线角色丢失 |
| ② | **lore 结构化缺失**：base_setting 是散文，没结构化字段 | NPC 答"X 怎么运作"靠现编 |
| ③ | **自由世界没事件骨架**：events_data 只在 script | 玩家自由探索撞不到原作经典桥段 |
| ④ | **研究 → execution 信息保真度低**：reference_doc 在 strategy brief 阶段被压扁 | IP 细节（人名 / 地名 / 物件 / 典故 / 台词风格）丢失 |
| ⑤ | **关系网 / 知识隔离不密**：有 `initial_peer_relations` 但缺密集网络 + 共享记忆 | 戏剧张力源头薄 |

### 0.3 已经到位的（不重做）

| 能力 | 状态 |
|---|---|
| 任务持久化 + SSE 重连续看（`generation_task_events.seq`） | ✅ |
| 草稿 → 发布原子事务 | ✅ |
| 单 admin 并发限制 + advisory lock | ✅ |
| 图片 retry + placeholder 兜底 | ✅ |
| 5 层模型骨架（policy → research → strategy → execution → validation） | ✅，本次只**扩展**不重写 |
| **运行时按需召回**：NPC Agent 注入只看自己 + 同场 peer + 自己 memory（`orchestrator.py:540-657`） | ✅，本次新字段沿用同模式接入 |
| 草稿编辑器基础组件（`DraftEditorShell + EditorSection + RepeaterCard + StructuredTriggerField + ...`） | ✅，本次复用，只加新字段必要展示 |

---

## 1. 决策清单（已拍板）

| # | 决策点 | 选择 | 备注 |
|---|---|---|---|
| 1 | World 改造范围 | 三阶段全做（① ② ③ ④ ⑤） | 用户："不计成本，做完整" |
| 2 | Script 模式 | **同步升级**，不留尾巴 | 避免"world 厚 script 薄"不对称 |
| 3 | 运行时引擎消费 | **同步做**——新字段全部接入 NPC Agent / world_simulator prompt | 不做就是白做 |
| 4 | 老世界（wuyinzhen 等）兼容 | **不管**，全是测试数据 | 引擎按"字段可缺失"宽容处理即可 |
| 5 | 生成时长上限 | 不做异步通知；现有"draft 重连"已够（`DraftEditorShell` 通过 `?after_seq=N` 续看） | 用户判断 + 已观察到功能完善 |
| 6 | 草稿编辑 UI | **只加必要的**，复用现状组件 | 用户昨日刚重构，不重做 |
| 7 | 角色头像范围 | playable + admin 标记的"重要 NPC" | 不全员画 |
| 8 | lore 维度清单的人机协作 | **LLM 全自动**，admin 不介入清单 | 用户："1b" |
| 9 | shared_events 素材来源 | **优先 reference_doc 抽**，不够再 LLM 编 | 用户："2a" |
| 10 | events_data trigger 类型 | **a + b + c**：NPC intent 驱动 / 复合条件 / rumor 渗透；d（leakage 兜底）后置 | 见 §4.3 |
| 11 | Critic gate 覆盖策略 | **分级**：形状校验 / 轻 critic / 重 critic / 运行时校验 | 见 §5 |
| 12 | 失败容错 | **retry + checkpoint**，不做断点 resume | 见 §6 |

---

## 2. 数据结构变更

### 2.1 World 表新增字段（JSON）

| 字段 | schema | 来源阶段 |
|---|---|---|
| `lore_pack` | `{ dimensions: [{ key, name, content_blocks: [{ heading, body }] }], generated_at }` | 新增 lore_pack 阶段 |
| `shared_events` | `[{ id, title, summary, era, involved_npcs: [name], perceptions: { name: { knows, believes, feels } }, source_passage_ids: [string] }]` | 新增 shared_events 阶段 |
| `events_data` | `[{ id, kind, summary, trigger, effects, rumors }]`，详见 §4.3 | 新增 events 阶段（自由世界） |

> 现状 world 是"无 schema 的 JSON-blob 载荷"——`worlds` 表已有 `base_setting / locations / characters` 等字段，新字段以 NULLABLE JSON 加入。已发布 worlds（wuyinzhen）字段为 NULL，引擎按"缺失即跳过"处理。

### 2.2 Script 表

- 现有 `events_data / endings_data` 沿用，**事件 schema 升级**——加 `kind / rumors / effects` 字段，向前兼容（旧字段保留，新字段为 optional）。
- `shared_events` **不在 script 表存**，从其依附的 world 继承（运行时 join）。

### 2.3 GenerationTask 表

```sql
ALTER TABLE generation_tasks
  ADD COLUMN intermediate_state JSON NULL;  -- 每阶段 snapshot
```

intermediate_state 形态（增量更新，每阶段完成时 merge）：

```jsonc
{
  "research_pack": { "passages": [...], "ip_canon": {...} },
  "world_base": {...},
  "lore_dimensions": [...],
  "lore_pack": {...},
  "character_roster": [{"name": "...", "role_tag": "..."}],
  "characters_batch_1": [{...}],
  "characters_batch_2": [{...}],
  "shared_events": [...],
  "relations_pack": { ... },
  "events_data": [...]
}
```

### 2.4 Alembic 迁移

新增 1 个迁移文件：

```
backend/migrations/versions/<rev>_world_creator_v2_fields.py
- worlds: + lore_pack JSON, + shared_events JSON, + events_data JSON
- generation_tasks: + intermediate_state JSON
```

---

## 3. 研究层改造（瓶颈 ④）

### 3.1 现状

`ResearchBroker.search → _summarize` 把 Tavily 结果压成单个 `reference_doc` 字符串 → 跨阶段累积 → 在 strategy brief 阶段进一步压扁成短摘要 → execution prompt 收到的是摘要，不是原文。

### 3.2 新方案：ResearchPack（结构化保真容器）

```python
@dataclass
class ResearchPack:
    summary: str                    # 现状的 reference_doc 风格短摘要，向前兼容
    passages: list[Passage]         # 原文片段，每个带 id + tags + source
    ip_canon: IPCanon               # structured IP knowledge
    
@dataclass
class Passage:
    id: str                         # "p_001"
    text: str                       # 原文片段（200-500 字）
    tags: list[str]                 # ["character:梅长苏", "location:苏宅", "era:大梁朝"]
    source: str                     # "tavily" | "ip_probe" | "admin_note"

@dataclass
class IPCanon:
    title_guesses: list[str]        # ["琅琊榜", "麒麟才子"]
    canonical_names: list[str]      # ["梅长苏", "靖王", "霓凰郡主", ...]
    canonical_places: list[str]
    iconic_objects: list[str]       # ["麒麟才子琅琊榜首", "梅花刀", ...]
    lingo: list[str]                # 标志性台词 / 称谓 / 语气
    notable_events: list[str]       # 高强度叙事节点列表（不是完整事件，只是名字）
```

### 3.3 三路输入合并

1. **Tavily 检索路径**（现状）：拉 search results → 改为同时保留每条结果的"原文段（≤500 字）"作为 `Passage(source="tavily")`，不再一次性 summarize 掉。
2. **IP probing 路径**（新）：用 planner LLM 自查"我对这段描述里指向的题材/IP 知道什么"，输出 IPCanon JSON。`research_summarizer` slot 复用。
3. **admin description 路径**（新）：admin 在 description 里贴的长文本（剧本节选 / wiki 整理 / 设定集摘录）切片成 `Passage(source="admin_note")`，按段落切，每段 ≤500 字。

合并完成 ResearchPack 后再过一次 `_summarize` 出 `summary`（保留向前兼容）。

### 3.4 strategy + execution 注入策略

- **strategy 层**（`GenerationStrategyService.build_*_brief`）：
  - 收 `ResearchPack.summary + ip_canon`
  - 输出 brief 时，**新增**一个 `relevant_passage_ids: list[str]` 字段——告诉下游 execution 阶段"这次要 quote 哪几段原文"
- **execution 层**（`_generate_world_base / _generate_characters / ...`）：
  - 收 `ResearchPack` 完整对象 + brief
  - 按 `relevant_passage_ids` 把对应原文段直接拼进 prompt（用 `===原文片段（仅供参考，可直接引用人名/地名/物件）===\n{passage.text}\n===` 包裹）

### 3.5 token 经济 + 大小上限

- 每阶段 prompt 中原文段总量上限：8K token（约 16 段）
- 超出时按 strategy 指定的 `relevant_passage_ids` 优先级裁剪
- 单局生成 token 估算：现状约 50-80K total → 改造后约 80-120K（增长 60%，admin "不计成本"接受）

**ResearchPack 容量上限**（防 admin 贴超长素材打爆系统）：

| 维度 | 上限 | 超出时行为 |
|---|---|---|
| 单 passage 字符数 | 600 字 | 切片成多段 |
| passages 总数 | 100 | 按 source 优先级保留：admin_note > tavily > ip_probe |
| admin description 总字符 | 50K | API 层 422 拒绝 + 错误提示 admin 精简 |
| ip_canon.canonical_names | 200 | 截断 + warning |

上限值定义为 `backend/services/research_broker.py` 顶部常量，admin 改 .env 可调。

---

## 4. 阶段流改造

### 4.1 World 生成新阶段流

旧（v1）→ 新（v2）：

| 阶段 | v1 | v2 改造 |
|---|---|---|
| `research` | 1-2 次隐式 | **改 ResearchPack 路径**（§3） |
| `world_base` | 单次 LLM | 不变 |
| **`lore_dimensions`** | ❌ | 新：planner LLM 出维度清单 |
| **`lore_pack`** | ❌ | 新：每维度独立 LLM call，可并发 |
| **`character_roster`** | ❌（合并在 characters） | 新：先出 N 个名字 + role_tag + 派系 |
| `characters` | 单次 LLM 全部 | **改分批**：每批 5-6 人，并发 3-4 路；批内严格按 `character_roster` 名字 1:1 输出（roster 是 source-of-truth，禁止增删/改名/合并），批后用 `set(name)` 校验无重名 |
| **`shared_events`** | ❌ | 新：从 ResearchPack.passages 抽 + LLM 补，K=10-20 |
| **`relations_pack`** | ❌ | 新：每 NPC 反向推 important_relations + 派系兜底 |
| **`events_data`**（自由世界） | ❌ | 新：见 §4.3 |
| `playable` | 单次 LLM | 不变 |
| `critic` | 单 pass + repair | **分级**（§5） |
| `images` | 现状 | 头像范围按"playable + admin 标记重要 NPC" |
| `validating` | 形状校验 | 扩展（§5.1） |

### 4.2 Script 生成新阶段流

| 阶段 | v1 | v2 改造 |
|---|---|---|
| `research` | 1 次 | **改 ResearchPack 路径** |
| `script_base` | 单次 LLM | 不变 |
| `events` | 单次 LLM | **改分批**（多线剧情可分线生成）+ schema 升级（kind / rumors / effects） |
| `endings` | 单次 LLM | 不变 |
| `playable` | 单次 LLM | 不变 |
| `critic` | 单 pass + repair | **分级**（§5） |

> 注：script 不重出 characters / lore_pack / shared_events，从依附 world 继承。

### 4.3 events_data schema（自由世界 + script 共用）

```jsonc
{
  "id": "evt_001",
  "kind": "npc_intent_driven",  // | "conditional"
  "summary": "誉王在朝堂上发难，弹劾靖王",
  // trigger 形态因 kind 不同，二选一：
  //
  // kind="npc_intent_driven" 时：
  "trigger": {
    "npc_name": "誉王",
    "condition_dsl": "time_after('day_3') AND world_state.靖王军功 >= 2",
    "intent_payload": { "goal": "弹劾靖王", "method": "联合礼部尚书" }
  },
  // kind="conditional" 时（替代上面的 trigger）：
  // "trigger": {
  //   "condition_dsl": "time_after('day_3') AND location_is('朝堂') AND player_did('与梅长苏密谈')",
  //   "probability": 0.7
  // },
  "effects": {
    "world_state_changes": { "靖王处境": "危急" },
    "spawn_clues": ["誉王得知玩家身份"],
    "npc_mood_changes": { "靖王": "戒备" }
  },
  "rumors": [
    { "text": "听说誉王最近频繁出入礼部...", "knower_npcs": ["蒙挚", "言侯"] },
    { "text": "朝堂上要出大事了", "knower_npcs": ["市井小贩A", "茶楼掌柜"] }
  ]
}
```

**triggering 类型选择**（决策 #10）：
- ✅ a) `npc_intent_driven`：注入 NPC intent，让事件由 NPC 自驱发生（接 `intent_system`）
- ✅ b) `conditional`：复合条件 + 概率
- ✅ c) `rumors` 字段：未触发时在世界里以传闻形式渗透
- ❌ d) leakage 兜底：玩家完全错过的事件以"过去式"被某 NPC 提及——**本次不做**，需要全局事件追踪 + 衰减触发器

### 4.4 字段引用一致性约束（生成期 + 运行时）

| 引用 | 必须存在于 |
|---|---|
| `playable[].name` | `characters[].name` |
| `characters[].schedule.values()` | `locations[].name` |
| `characters[].initial_location` | `locations[].name` |
| `shared_events[].involved_npcs` | `characters[].name` |
| `events_data[].trigger.npc_name`（npc_intent_driven） | `characters[].name` |
| `events_data[].trigger.when.locations`（conditional） | `locations[].name` |
| `events_data[].rumors[].knower_npcs` | `characters[].name` |
| `events_data[].effects.npc_mood_changes` keys | `characters[].name` |

生成期违反 → 形状校验报错（§5.1），critic 阶段强制修复 / 标 quality_warnings。

---

## 5. Critic gate 分级（决策 #11）

| 档位 | 覆盖阶段 | 实现 | 成本 |
|---|---|---|---|
| **形状校验**（无 LLM） | locations / characters schedule / playable ⊆ characters / shared_events.involved_npcs ⊆ characters / events.trigger 引用 / events.rumors.knower_npcs | Python 校验 | 0 token |
| **轻 critic**（单 LLM pass，无 repair） | lore_pack（维度内部一致性，无 self-contradiction）/ shared_events（与 ResearchPack.ip_canon 是否对齐） | 1 次 critic call，发现问题写 quality_warnings，不自动修复 | ~5-10K token |
| **重 critic**（review + repair pass，保留现状） | characters / playable | 现状 `_normalize_generation_review_result` + `_build_repair_note` 不动 | ~20-40K token |
| **运行时校验** | events_data.trigger 可执行性 | 解析 condition_dsl，引用项必须存在；解析失败标 disabled | 0 token |

**总开销**：相对现状增加约 **50%**（不是翻倍）。形状校验 0 成本兜底，轻 critic 只在新增字段上做单 pass。

### 5.5 内容审核（moderation）

生成产物（NPC personality / shared_events.summary / events_data.summary / lore_pack content_blocks）可能含暴力 / 政治敏感 / 色情内容。在 critic 阶段后追加一个 moderation pass：

| 校验对象 | 实现 |
|---|---|
| 所有自由文本字段 | 调 `services/moderation.py` 现有接口（游戏运行时复用） |
| 命中行为 | 标 `quality_warnings: ["moderation_flag:<reason>"]`，**不阻断生成** |
| 发布前拦截 | `publish_world_draft / publish_script_draft` 在 commit 前检查 quality_warnings 含 `moderation_flag:*`，admin 必须显式确认才发布 |

> 跟运行时 moderation 的差别：生成期是抽样校验（每个新生成的字段过一次），运行时是逐轮玩家输入 + LLM 输出过一次。

---

## 6. 失败容错（决策 #12）

### 6.1 透明 retry

每个 LLM 阶段加 1-2 次 transient retry（参照 `seedream.py` 现有图片层做法）：

| 异常类型 | 行为 |
|---|---|
| `APIConnectionError / APITimeoutError / RateLimitError` / 5xx | retry，backoff 1s/3s |
| 4xx / json parse error | 立即失败 |

> JSON parse error 不 retry 是因为通常是 schema 设计问题或 prompt 不稳，retry 不解决。失败后正常 emit error 事件，admin 自己重跑或调 schema。

### 6.2 阶段 checkpoint（intermediate_state）

每阶段 `completed` 时，把产物 snapshot 到 `generation_tasks.intermediate_state`（JSON merge，不覆盖前面阶段的）。

**作用**：
- 任务失败后 admin 至少能看到"前面已完成的部分"
- workshop / draft editor 可以展示 intermediate_state（复用现有 read-only JSON 字段渲染）
- **不做"从断点 resume"**——失败要么 retry 自动救活，要么从头重跑（admin 可基于 intermediate_state 决定要不要保留生成的部分手动拼）

### 6.3 不做的事

- ❌ 任意阶段 resume（工程不小，收益不高）
- ❌ 异步通知 / 邮件（draft 重连已经覆盖此场景）
- ❌ task cancellation —— 现状未做，本次也不做

### 6.4 LLM slot 扩展规范

复用现有 9 个 slot（`backend/services/model_management.py:SLOT_DEFINITIONS`），不新增：

| 新阶段 | slot | fallback 行为 |
|---|---|---|
| `lore_dimensions`（出维度清单） | `research_planning` | 未绑定时由 model_management 自动 fallback 到 `admin_generation` |
| `lore_pack`（逐维度内容） | `admin_generation` | — |
| `character_roster` | `research_planning` | 同 lore_dimensions |
| `character_batch_*` | `admin_generation` | — |
| `shared_events_extractor` | `admin_generation` | — |
| `events_data_writer` | `admin_generation` | — |
| `lore_critic` / `shared_events_critic` | `admin_generation`（复用主，无独立 critic slot） | — |
| `ip_probe`（§3.3 新路径） | `research_summary` | 未绑定时 fallback 到 `research_planning` → `admin_generation` |
| `moderation pass`（§5.5） | `moderation_slot` | — |

**约束**：不新增 LLM provider；不新增 slot；不绑定具体 model 名。9 个 slot 沿用现状，admin 后台 UI 不变。fallback 由 model_management 服务层自动处理。

### 6.5 Feature flag

环境变量 `WORLD_CREATOR_V2_ENABLED`（默认 `false`，上线后 admin 显式打开）：

| flag 状态 | 行为 |
|---|---|
| `false` | `start_world_generation / start_script_generation` 走 v1 链路（现状），新字段不生成、运行时新接入逻辑跳过 |
| `true` | 走 v2 链路（本 spec 全部改造） |

切换以 task-level 为粒度（每个新 task 启动时取当前 flag）。已启动的 v2 task 不会因 flag 切回 v1 而中断（intermediate_state 保留）。

**目的**：上线时先全 false 部署 → admin 单独开 flag 跑测试 → 稳定后默认改 true → 一段时间后 v1 代码删除。
- ❌ task cancellation（现状未做，本次也不做）

---

## 7. 运行时引擎接入（决策 #3）

### 7.1 NPC Agent prompt 注入扩展

现状（`orchestrator.py:540-657`）NPC Agent 收：
- `npc_personality / npc_secret / knowledge / world_setting / scene_context / peer_relations / npc_memories / reflection / voice_anchor / current_intent`

新增（按 §0.3 同模式——按需召回，不全员塞）：

| 新字段 | 召回策略 | token 上限 |
|---|---|---|
| `relevant_lore` | 按当前 NPC.knowledge 关键词与 lore_pack.dimensions[].content_blocks 做 embedding 余弦匹配（复用 `services/embedding_service.py`），取 top-3 blocks | ~1K |
| `involved_shared_events` | `shared_events.filter(npc_name in involved_npcs)`，每条按该 NPC 的 perceptions 视角呈现 | ~1.5K |
| `relevant_rumors` | 当前 NPC 在 events_data[].rumors[].knower_npcs 里的所有 rumors（仅未触发的事件） | ~500 |

实现位置：`engine/orchestrator.py` 在 line 632 的 `npc_tasks.append({...})` kwargs 里加这三个字段；`engine/npc_agent.py` 的 prompt builder 按字段拼。

### 7.2 world_simulator 接入 events_data

现状 `world_simulator.tick(game_state, world_data)` 已经产 `tick_result.world_events`。

新增逻辑（`engine/world_simulator.py`）：

```python
def tick(self, game_state, world_data):
    # 现有 logic（NPC schedule / 环境事件）
    ...
    
    # NEW: 检查 world_data.events_data 的 conditional trigger
    for event in world_data.get("events_data", []):
        if event["kind"] != "conditional":
            continue
        if self._evaluate_trigger(event["trigger"], game_state):
            world_event = self._materialize_event(event)
            tick_result.world_events.append(world_event)
            # 副作用应用到 game_state
            self._apply_effects(event["effects"], game_state)
    
    # NEW: 检查 npc_intent_driven 事件，把 intent 注入 npc_intents
    for event in world_data.get("events_data", []):
        if event["kind"] != "npc_intent_driven":
            continue
        if self._evaluate_trigger(event["trigger"], game_state):
            game_state.npc_intents[event["trigger"]["npc_name"]] = event["trigger"]["intent_payload"]
```

`condition_dsl` 解析器：极简表达式（`time_after('day_3') AND world_state.X >= 2`），白名单 ops（AND/OR/NOT/比较 / `time_after / location_is / player_did`）。无引用 / 无函数调用 / 无副作用，纯计算，自带 fuzzer 测试。

### 7.3 director_agent 不动

NPC 池变大（5-8 → 20-30+），director 的 NPC 选择逻辑（`director_agent.py`）不改。理由：现状 director 按 involved_npcs（玩家话题相关）选，不是从全员 list 选；NPC 数翻倍对它的 prompt 复杂度影响很小（director prompt 里的 NPC list 是题面用，不是逐个详细描述）。

如压测发现 director prompt token 太大，再做"按 location 预过滤"。

---

## 8. 前端改动（最小必要）

### 8.1 编辑器（`components/admin/editor`）

**新增字段展示**（read-only，复用 JsonField）：
- `lore_pack`：嵌套折叠展示 dimensions × content_blocks
- `shared_events`：表格视图（id / title / involved_npcs / 展开 perceptions）
- `events_data`：表格视图（id / kind / trigger 摘要 / rumors 数）—— trigger DSL 折叠 raw 显示

**不做**：
- ❌ lore_pack / shared_events / events_data 的结构化编辑 UI（admin 不满意整体重跑）
- ❌ rumors 单独编辑 UI

### 8.2 Workshop list

**不动**——现状 `WorkshopWorldsPanel / WorkshopScriptsPanel` 显示 published + draft，draft 点击进 `DraftEditorShell` 自动重连 SSE。

### 8.3 SSE 事件名扩展 + 反馈协议

`frontend/lib/admin-sse-events.ts` 新增 phase 名（不改事件 schema 结构）：
- 主阶段：`research_pack` / `world_base` / `lore_dimensions` / `lore_pack` / `character_roster` / `characters` / `shared_events` / `relations_pack` / `events_data` / `playable` / `critic` / `images` / `validating`
- 子阶段（并发任务）：`lore_dimension_{key}` / `character_batch_{n}` / `npc_avatar_{name}` / `lore_critic` / `shared_events_critic`

`progress / warning / result / error / done` 五种事件名复用。

**每阶段强制反馈协议**（前端展示依赖）：

| 时机 | event | code | 必填 meta |
|---|---|---|---|
| 主阶段开始 | `progress` | `started` | `stage_index`, `total_stages` |
| 主阶段含并发子任务时（每个子任务开始） | `progress` | `subtask_started` | `subtask_key`, `subtask_index`, `subtask_total` |
| 主阶段含并发子任务时（每个子任务完成） | `progress` | `subtask_completed` | `subtask_key`, `subtask_index`, `subtask_total`, `payload_summary`（如 `{"npc_count": 6}`） |
| 长阶段心跳（>30s 未发事件） | `progress` | `heartbeat` | 无 |
| 主阶段完成 | `progress` | `completed` | `stage_index`, `total_stages`, `duration_ms`, `payload_summary` |
| transient retry（§6.1） | `warning` | `transient_retry` | `attempt`, `max_attempts`, `error_class` |
| 重 critic 触发修复 | `progress` | `repair_completed` 或 `review_adjusted` | `quality_warnings_count` |

**meta 标准化字段**（前端进度条 / 状态卡通用）：

```ts
type ProgressMeta = {
  // 主阶段位置
  stage_index?: number;       // 0-based, in total_stages
  total_stages?: number;
  // 子任务并发位置（仅在主阶段含并发时填）
  subtask_key?: string;       // 如 "lore_dimension:tech_levels" / "character_batch:2"
  subtask_index?: number;
  subtask_total?: number;
  // 时长
  duration_ms?: number;
  // 摘要（前端可秀的关键产出数）
  payload_summary?: Record<string, number | string>;
  // 重试
  attempt?: number;
  max_attempts?: number;
  error_class?: string;
};
```

**前端展示模型**：
- `DraftEditorShell` 维护一个 `stages: Map<phase, StageStatus>`，每个 phase 有 `pending / running / completed / failed` 四态 + 子任务进度条
- 主阶段进度 = `stage_index / total_stages`，子任务进度 = `subtask_index / subtask_total`
- heartbeat 仅用来防"看起来卡住"，不展示

**约定**：每个新增/修改的阶段都**必须** emit `started` 和 `completed`（即使瞬时完成的形状校验也要发一对）——前端依赖这俩做状态机转移。

### 8.4 角色头像范围（决策 #7）

`characters[].is_image_target`（boolean，character JSON 子字段，非表字段；生成期默认 false）：
- 所有 `playable[]` 对应 character 自动 `is_image_target=true`
- 生成期 LLM 在 `character_roster` 阶段标 N 个"重要 NPC"（按 role_tag 启发式 + 派系核心）
- 图片阶段只为 `is_image_target=true` 的角色画头像
- admin 在 editor 可勾选 / 取消（最小 UI 改动：character row 加一个 checkbox）

---

## 9. 测试覆盖

### 9.1 单元测试新增

| 测试文件 | 覆盖 |
|---|---|
| `tests/test_research_pack.py` | Tavily passages + IP probing + admin_note 三路合并；passage truncation；IPCanon schema |
| `tests/test_character_batch.py` | character_roster + 分批生成；跨批引用一致性；schedule 引用 locations 一致性 |
| `tests/test_lore_pack.py` | dimensions 生成；并发逐维度生成；维度内部一致性 critic |
| `tests/test_shared_events.py` | 从 passages 抽取；引用 NPC 名一致性；perceptions schema |
| `tests/test_events_data_dsl.py` | condition_dsl 解析；非法表达式拒绝；trigger 求值 |
| `tests/test_world_simulator_events.py` | conditional trigger 命中产生 world_event；npc_intent_driven 注入 intent |
| `tests/test_npc_agent_lore_injection.py` | NPC Agent prompt 注入 relevant_lore / involved_shared_events / rumors |

### 9.2 集成测试新增

| 测试 | 覆盖 |
|---|---|
| `tests/test_world_creator_v2_e2e.py` | mock LLM，端到端 world 生成；intermediate_state 增量正确；阶段事件顺序 |
| `tests/test_script_creator_v2_e2e.py` | 同上，script 模式 |
| `tests/test_world_creator_retry.py` | 阶段 transient 失败 retry；non-transient 立即失败；checkpoint 在失败后仍存 |

### 9.3 不专门测的（信任）

- LLM 输出质量（依赖 prompt 工程 + 真实跑数据）
- 图片生成（已有测试覆盖）
- DraftEditorShell 重连（已有功能）

---

## 10. 工作量估算

| 模块 | 估算 |
|---|---|
| ResearchPack（§3） | 4-5 天 |
| 角色分批（§4.1 character_roster + characters） | 3-4 天 |
| lore_pack（§4.1） | 4 天 |
| shared_events + relations_pack（§4.1） | 4 天 |
| events_data + condition_dsl（§4.3 + §7.2） | 5-6 天 |
| Script 模式同步升级（§4.2） | 3 天 |
| 运行时引擎接入（§7） | 4-5 天 |
| Critic 分级（§5） | 3 天 |
| 容错（retry + checkpoint，§6） | 2 天 |
| Alembic 迁移（§2.4） | 1 天 |
| 前端展示（§8） | 3 天 |
| 测试（§9） | 5-6 天 |
| 并发改造 + 反馈协议（§8.3 / §12.3） | 3-4 天 |
| **buffer** | 3-5 天 |
| **总计** | **7-8 周** |

---

## 11. 非目标（明确不做）

- ❌ 文件上传（PDF / 文档）—— 用户已排除（C 选项）
- ❌ 老世界 backfill —— 测试数据，不管
- ❌ 任意阶段 resume —— 决策 #12
- ❌ 异步邮件通知 —— draft 重连已覆盖
- ❌ events_data leakage 兜底（trigger d）—— 后置
- ❌ 草稿编辑全套结构化 UI —— 用户："只加需要的"
- ❌ Tavily fallback 链 —— 现状 P2，本次不做
- ❌ 草稿覆盖发布 UX —— 现状 P2，本次不做
- ❌ task cancellation —— 现状未做，本次也不做
- ❌ director_agent 改造 —— 当前 prompt 模式对 NPC 池扩大宽容，等压测出问题再做
- ❌ 持久化研究缓存 —— roadmap P3，等创世量上来再做

---

## 12. 风险与开放问题

### 12.1 已识别风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | NPC 数量翻倍后，director 的 prompt 仍然吃下整 list，预期 token 增长 < 30%，但**未压测** | 上线前跑一次 30+ NPC 世界做 token 统计；超阈值再做"按 location 预过滤" |
| R2 | condition_dsl 解析器是新引入的"小语言"，安全边界要严 | 白名单 ops + 无函数调用 + fuzzer 测试 + 解析失败标 disabled 不报错 |
| R3 | lore_pack 维度由 LLM 全自动出（决策 #8），可能出现"题材不需要也硬塞维度"的情况 | planner prompt 里加"如题材不需要 lore，可输出空 dimensions"的明确指令；轻 critic 兜底 |
| R4 | shared_events 优先从 reference_doc 抽（决策 #9）—— 当 reference_doc 太薄时，K=10-20 的目标可能无法达成，会触发 LLM 大量"补编造" | 设最小阈值 K_min=5（从 ref 抽到 5 条以下时强制 LLM 补到 K_min），admin 不满意整体重跑 |
| R5 | retry + checkpoint 但**不 resume**，长链路（10-12 阶段）末段失败仍要 admin 决定全跑还是手拼 | 接受。痛点真出现后再升级 resume |

### 12.2 开放问题（spec review 时确认）

- **Q1**：lore_pack 的维度数量上限——目前提议 2-6 个，是否合理？过多会让生成时间和 token 都失控。
- **Q2**：character_roster 的 N（目标人数）是否要 admin 配置（如 description 里写"我要 25 个 NPC"），还是 LLM 根据题材自决？提议 LLM 自决，admin 不介入；admin 不满意整体重跑。
- **Q3**：shared_events 的 K（目标条数）是否需要 admin 干预？提议 K=10-20 由 LLM 自决，K_min=5 兜底。
- **Q4**：condition_dsl 用现写的 mini-parser，还是借用 `simpleeval` / `pyparsing` 等库？提议**自写**——白名单 ops 总共不超过 10 个，自写 100 行可读且可控；引入库反而增加攻击面。
- **Q5**：rumors 的注入触发条件——目前提议"NPC 在话题相关时可自然提及"，但话题相关的判断交给 NPC Agent LLM。是否需要更显式的 prompt 约束（比如限定一轮最多注入 1 条 rumor）？提议先不限，观察实际跑出来效果，过密就加。

---

## 12.3 提速方案——运行时并发图

> 现状串行链路总耗时估算 50-80 分钟（§4 各阶段累加）。下面的并发图把可独立的工作并发起来，目标 **总耗时压到 25-40 分钟**（约 50% 降幅，受最慢关键路径制约）。

### 12.3.1 并发依赖图（运行时 = admin 跑一次生成）

```
┌──────────────────── Stage A: research ────────────────────┐
│  ① Tavily 检索（多 query 并发，3-5 路）                    │
│  ② IP probing（独立 LLM call）                              │ 三路并发
│  ③ admin_note 切片（同步，瞬时）                            │
└─────────────────────────┬─────────────────────────────────┘
                          ▼ 合并 ResearchPack
┌──────────────────── Stage B: world_base ───────────────────┐
│  base_setting + locations + free_setting（单 LLM）         │
└─────────────────────────┬─────────────────────────────────┘
                          ▼
┌──── Stage C1: lore_dimensions ──────┬──── Stage C2: character_roster ─────┐
│  planner LLM 出维度清单             │  planner LLM 出 N 名字 + role_tag    │  C1/C2 并发
│  （单次 LLM）                        │  （单次 LLM）                        │
└─────────────────┬───────────────────┴────────────┬────────────────────────┘
                  ▼                                ▼
┌── Stage D1: lore_pack ──────────────┬── Stage D2: characters_batch ──────┐
│  每维度独立 LLM call（M 维度）       │  每批 5-6 人独立 LLM（⌈N/6⌉ 批）    │  D1 内部并发
│  并发上限 4 路                       │  并发上限 4 路                      │  D2 内部并发
│                                      │                                     │  D1/D2 跨阶段并发
└─────────────────┬───────────────────┴────────────┬────────────────────────┘
                  │                                ▼
                  │                ┌── Stage E1: shared_events 抽取 ─────┐
                  │                │  从 ResearchPack.passages 抽事件    │
                  │                │  （单 LLM；passages 多时分 chunk）   │
                  │                └────────────┬────────────────────────┘
                  │                             ▼
                  │                ┌── Stage E2: relations_pack ─────────┐
                  │                │  反向推每 NPC important_relations   │
                  │                │  （Python 计算，无 LLM）             │
                  │                └────────────┬────────────────────────┘
                  ▼                             ▼
┌──────────────── Stage F: events_data ─────────────────────┐
│  依赖 lore_pack + characters + shared_events + locations │  
│  按 K 条件目标分批生成，并发 3 路                          │
└─────────────────────────┬─────────────────────────────────┘
                          ▼
┌──────────────── Stage G: playable ─────────────────────────┐
│  从 characters 选子集 + review_started/adjusted/completed │
└─────────────────────────┬─────────────────────────────────┘
                          ▼
┌──────────────── Stage H: critic 分级 ─────────────────────┐
│  H1 形状校验（同步，瞬时，整 payload 跑一遍）             │
│  H2 轻 critic：lore + shared_events 各一路（并发）         │  H2/H3 跨档并发
│  H3 重 critic：characters + playable 串行（保留现状）     │
└─────────────────────────┬─────────────────────────────────┘
                          ▼
┌──────────────── Stage I: images ──────────────────────────┐
│  封面（1 张）+ NPC 头像（is_image_target=true 的，K 张）   │
│  全部并发，上限 6 路（Seedream rate limit 边界）           │
└─────────────────────────┬─────────────────────────────────┘
                          ▼
                       Stage J: validating（最终一致性 + 收尾）
```

### 12.3.2 关键路径耗时估算（含并发）

| 阶段 | 串行版 | 并发版（含上限） | 备注 |
|---|---|---|---|
| A research | 5-8 min | **3-4 min** | Tavily 查询 + IP probe 并发 |
| B world_base | 1-2 min | 1-2 min | 单 LLM，不并发 |
| C lore_dimensions + character_roster | 2-3 min | **1-1.5 min** | 跨阶段并发 |
| D lore_pack（M=4 维度）+ characters（5 批） | 15-20 min | **5-7 min** | 每阶段内 4 路并发，跨阶段并发 |
| E shared_events + relations_pack | 5-8 min | 4-5 min | E2 是 Python，瞬时 |
| F events_data | 5-8 min | **2-3 min** | 3 路并发 |
| G playable | 2-3 min | 2-3 min | review pass 不并发 |
| H critic | 5-10 min | **3-5 min** | 轻 critic 并发；重 critic 保留串行 |
| I images（30 张） | 5-10 min | **2-3 min** | 6 路并发，受 Seedream rate limit |
| J validating | <1 min | <1 min | 同步 |
| **总** | **50-80 min** | **25-35 min** | 关键路径主导 |

### 12.3.3 并发实现规范

- **统一并发原语**：`asyncio.gather(*[...])` + `asyncio.Semaphore(N)` 控并发上限。**禁止**用 `asyncio.create_task` 不收尾的 fire-and-forget（除生成任务本身，§2.1 文档已规定）。
- **每路并发任务必须**：
  - 入口 emit `subtask_started`（§8.3 协议）
  - 出口 emit `subtask_completed`（带 payload_summary）
  - transient 失败 retry 由该路自身 own，不汇总到外层
- **失败传播**：`asyncio.gather(..., return_exceptions=True)` 收集所有结果，同步阶段尾部统一处理——单路失败标 quality_warnings（不致命的）或 raise（致命的，整阶段失败）
- **并发上限**（防 LLM rate limit / Seedream 配额）：
  - LLM call：每 slot 上限 **4 并发**
  - Seedream image：上限 **6 并发**
  - Tavily：上限 **5 并发**
  - 上限值放 `backend/services/world_creator_agent.py` 顶部常量，admin 改 .env 可调

### 12.3.4 反馈给前端

每路并发任务在 §8.3 协议下 emit `subtask_started` / `subtask_completed`。前端 `DraftEditorShell` 看到 `subtask_total > 1` 的主阶段，渲染**子任务并行进度条**（M/N 已完成）。

---

## 13. 验收标准（高层）

| # | 标准 | 验证方式 |
|---|---|---|
| AC1 | 用一段 IP 复刻描述（指定影视剧 + 期望 25 个角色）跑 world 生成，产出 ≥ 20 个完整 NPC，名字/称谓/iconic 物件命中率 ≥ 70% | 人工抽查 + IP fan 对照清单 |
| AC2 | 玩家进入生成的世界，向 NPC 提问"X 怎么运作"（X = lore_pack 的某维度），NPC 回答内容不与 lore_pack 矛盾 | 集成测试 + 人工跑测 |
| AC3 | 玩家在自由世界游玩 30 分钟内，至少撞到 1 个 events_data 触发的 world_event 或 1 条 rumor 出现在 NPC 对话里 | 人工跑测 |
| AC4 | shared_events 中至少 60% 条目包含 ≥1 个 `source_passage_ids`（即"不是 LLM 大量编"） | 自动统计 `source_passage_ids` 非空率 |
| AC5 | 任意 LLM 阶段 transient 失败 → retry 自动救活，不影响最终产出 | 集成测试 mock 注入 timeout |
| AC6 | 任务失败时，`generation_tasks.intermediate_state` 含已完成阶段产物 | 集成测试 |
| AC7 | NPC Agent 运行时 token 较 v1 增长 < 50%（30 NPC 世界） | 压测脚本 |
| AC8 | Script 模式生成产出 events_data 含 ≥ 3 条 `kind="rumors"` 注入的 rumors | 测试 |
| AC9 | 单局 world 生成总耗时（30 NPC 规模）≤ 35 min P50、≤ 50 min P95 | 压测 5 次取分位数 |
| AC10 | 每个新增 / 修改的阶段都 emit `started` 和 `completed` 事件；含并发的主阶段额外发 `subtask_started` / `subtask_completed` | 端到端测试断言事件序列 |

---

## 14. 落地顺序（编码侧 hint，非 plan）

> 详细 plan 由 writing-plans skill 后续产出，本节只列依赖图。

```
   [Alembic 迁移]
         │
         ▼
   [ResearchPack §3] ────────────┐
         │                        │
         ▼                        ▼
   [character_roster + 分批] [lore_pack]
         │                        │
         └──────────┬─────────────┘
                    ▼
            [shared_events + relations_pack]
                    │
                    ▼
            [events_data + condition_dsl]
                    │
                    ▼
            [Critic 分级 + retry/checkpoint]
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   [Script v2]  [运行时接入]  [前端展示]
        │           │           │
        └───────────┴─────┬─────┘
                          ▼
                      [集成测试]
```

并行机会：
- ResearchPack / character_roster / lore_pack 可重叠开发（互独立）
- 运行时接入与前端展示并行
- Critic / retry 是横切关注，每个阶段开发时顺手织入

---

> Spec 完。下一步：writing-plans 产出实施 plan。
