# 结构演化管线 + 世界一致性判官 —— 设计 spec

状态：设计已拍板（2026-06-03），转实现计划
来源：上游分析 [`2026-06-02-world-evolution-and-director-agency-design.md`](2026-06-02-world-evolution-and-director-agency-design.md)。本 spec 是其落地版，**修正了上游分期建议**（合并为一套机制一次建），并补齐了**通用性**（去宫斗化）这一上游缺失的硬要求。
一句话目标：让世界脊柱（身份/在场/权力/世界真相）能在**合法的世界内因**下持久演化，同时让导演主动推世界 + 顶回凭空断言——三者由同一条管线统一，**任何题材通用**。

---

## 0. 背景与要解决的问题

引擎当前世界态是「一层活 + 一层冻」（上游 §1 已取证）：

- **软层（活）**：关系/情绪、线索、位置、NPC 意图、已触发事件、案件板、narrative_arc——每回合持久演化、回灌 prompt。`WorldSimulator.tick()`（`engine/world_simulator.py:35`，`orchestrator.py:450` 每回合调，纯规则 <50ms）已经在推进这一层。
- **脊柱（冻）**：`base_setting`、`script_setting`、NPC 人设/身份/位份/谁活着——**每回合从 DB 种子重建，游戏中从不改写**（`build_director_system_v2` 把脊柱放进系统提示，prefix-cache 友好）。

由此暴露三个根上同源的问题：

1. **导演太被动**：玩家跑偏时导演不主动把他往 crux 拽（导演 v2 prompt `prompts.py:816` 被过校正成「舞台调度员≠编剧」的旁观者）。
2. **世界不顶假断言**：玩家塞越界断言（"我已是皇后"），世界躲进环境氛围，既不照单全收也不正面驳斥。
3. **世界吸收不了真演化**：哪怕合法挣来的结构变化（甄嬛真上位），脊柱也焊不进去。

本 spec 用一条管线统一治这三个。

---

## 1. 核心原则（已与用户逐条拍板）

1. **哲学 A —— 世界底色只通过世界自身逻辑改变。** 不存在"上帝判官说你够格了就改"。一个结构事实要提交，前提是**这个世界的既定逻辑足以、且自洽地导致它**。
2. **通用性是铁律（最高约束）。** 代码里**不准有任何题材专属逻辑**。所有概念抽象到题材无关层；宫斗/破案只是实例。判官、级联、账本、`kind` 全部题材中立。测试用例横跨 ≥3 种题材防过拟合。
3. **主动式。** 结构变更既可玩家驱动，也可**世界驱动**（导演看局势成熟、按世界逻辑主动推，哪怕玩家没明说）——顺手治问题 ①。
4. **默认休眠。** 没有结构变更被提议时管线根本不触发，世界 == 今天（只有软层）。低结构题材（日常/纯探索）不会被强行塞结构戏。要不要结构演化，由故事自己召唤。
5. **零热路径常态开销。** 99% 回合无结构提议 → 判官不跑。仅在罕见的"有结构提议"回合才多一次 cheap 判官调用。
6. **不破 prefix-cache 经济性。** 账本变更罕见，走快照叠加，一次变更只破一次缓存、下回合重新焐热。

---

## 2. 概念定义（题材无关）

### 2.1 结构事实（structural fact）
= 现在"每回合从种子重建、从不改写"的脊柱里的一条事实。抽象成 4 个**语义维度**（仅用于跨题材理解，不是代码枚举）：

| 维度 | 含义 | 宫斗 | 武侠 | 科幻/战争 | 言情/现代 | 悬疑/探索 |
|---|---|---|---|---|---|---|
| 存在/在场 | 谁活着、在场、被永久移除 | 华妃伏诛 | 某派覆灭 | 殖民地被毁 | 某人永久离开 | 关键证人之死 |
| 身份/地位 | 头衔、职位、"是什么" | 甄嬛晋贵妃 | 掌门易主 | 当选议长 | 升任 CEO | — |
| 权力/归属 | 谁掌控什么、阵营结盟、关系定性 | 后宫易主 | 两派结盟 | 叛军占领首都 | 在一起/决裂 | — |
| 重大世界真相 | 大设定翻转 | 太后崩 | 绝学重现 | AI 觉醒 | 战争结束 | "这座岛其实是艘船" |

### 2.2 `kind` —— 按"机械后果"分，不按"剧情品类"分（去宫斗化关键）
代码里的 `kind` 枚举**只回答一个问题：提交这条事实后，需要哪种一阶机械清理？** 与叙事品类无关，所以天然题材中立。初版：

| `kind` | 机械后果（一阶级联做什么） | 覆盖的语义维度 |
|---|---|---|
| `entity_removed` | 从 active/在场名单移除该实体；冻结其关系；作废涉它的待触发事件/意图 | 存在/在场 |
| `entity_role_changed` | 改写该实体脊柱描述里的身份/头衔字段 | 身份/地位 |
| `relation_redefined` | 改写两实体间的关系定性（结盟/决裂/隶属） | 权力/归属（关系型，含言情） |
| `world_fact_changed` | 改写 base_setting / 地点 / 世界真相文本 overlay | 重大世界真相、非角色挂载的权力变更 |

> `kind` 是**开放可扩展**的小集合；新增一个 kind = 定义它的一阶机械后果。叙事多样性靠 `fact_text` 自由文本承载，不靠堆 kind。

### 2.3 脊柱 = 种子 + 结构账本
脊柱不再是"纯种子"，而是"种子 + 持久结构账本叠加"。账本只接受**校验通过**的变更。

---

## 3. 架构：一条管线（镜像现有结局裁决机制）

现有结局裁决就是模板：导演在它**单次调用**里输出 `ending_triggered`，服务端 `merge_ai_ending_judgment`（`ending_system.py:184`）拿它去比对作者 `soft_conditions`——对得上才认。结构变更走**完全同形**的「LLM 提议 + 服务端校验」管线。

```
玩家输入 / 世界态
      │
      ▼
[导演] 单次调用 ── 可选输出 structural_change_proposed   (3.1 提议)
      │
      ▼
[服务端校验]  剧本模式→condition_tree;自由模式→世界一致性判官  (3.2 校验)
   ├── 通过 → 写账本 + 一阶级联 + 一次"世界反应"叙述         (3.3 提交)
   └── 否决 → 分级世界反应（角色反对 / 环境不予承认），不写账本 (3.2 reject)
```

### 3.1 提议（导演，零额外调用）
`DirectorResult`（`engine/director_agent.py:218`）新增字段：

```python
structural_change_proposed: dict | None = None
# {
#   "fact_key": str,          # 稳定键，如 "consort_huafei.alive"
#   "fact_text": str,         # 题材自由文本，叠进脊柱的人话
#   "kind": str,              # 2.2 的机械后果枚举
#   "in_world_cause": str,    # 哪个角色/事件促成（哪怕"世界驱动"也要有因）
#   "justification": str,     # 基于世界逻辑/人物性格的依据（供判官与可观测）
#   "target_ref": str | None, # entity_* 指向哪个实体；world_fact 可空
# }
```

- 触发既可**玩家驱动**也可**世界驱动**（主动式）。
- 导演 prompt 增补：何时该提议结构变更、必须给出 `in_world_cause` + `justification`、**禁止**仅凭玩家一句声称就提议（声称 ≠ 因）。

### 3.2 校验（服务端，镜像 `merge_ai_ending_judgment`）
新增 `engine/structural_arbiter.py`，对外一个入口 `evaluate_structural_change(proposal, world_data, state, game_mode, ...) -> ArbiterVerdict`。

- **剧本模式**：若世界/剧本定义了对应的"结构里程碑"（作者预写，schema 见 §3.4），跑它的 `condition_tree`（复用 `engine/condition_tree.py`，认 `world_state.<key>`，确定性）。条件满足 → 通过。**作者有界 = IP 安全。**
- **自由模式**：**世界一致性判官**——回答"**以这个世界的既定逻辑（涉及角色的人设/性格 + base_setting 的设定规则 + 已发生的因果链），此刻这个改变有没有足够且自洽的因？**"
  - 这是**独立第二意见**（不是让提议的导演自己背书 → 防 yes-man）。
  - **只在有结构提议的回合才触发**（rare-fire）→ 常态零开销。复用 cheap-LLM 模式（`engine/stance_inference.py` 是先例）。
  - 输入：`proposal` + 涉及实体的人设 + `base_setting` 设定规则 + 近况摘要。输出：`{supported: bool, reason, missing: str|None}`。
  - **角色性格是角色驱动题材的主轴，但判官 charter 不假设一定有权威角色拍板**——破案靠事件后果、生存恐怖靠威胁动力学、言情靠双方情感涌现、战争靠态势，都落在"世界既定逻辑"里。
- **否决 ≠ 死路**，发**分级世界反应**（治问题 ②，去宫斗化见 §6 破绽 2）：
  - 有该在意的角色 → 角色按性格反对/惊惧/上报；
  - 无对抗角色（独自探索/日常）→ 环境/叙事层不予承认（"这句话悬在空气里，世界没照它转"）。**这正是现在的"软架空"——它是无对抗场景下的合法反应，不是 bug；本设计是给它分级、用对地方，顺便防"门卫世界"。**
  - 反应里可带 `missing`（还差什么）作为玩法钩子。

### 3.3 提交 + 一阶级联（题材无关）
通过时：
1. 写结构账本（§4）。
2. **一阶机械级联**，按 `kind` 分流（§2.2 表），**确定性**执行：名单增删 / 改头衔字段 / 改关系定性 / 改世界真相 overlay。
3. 旁白叙述**一次**"世界反应"beat（LLM，narrator）。
4. 此后 NPC 从**更新后的脊柱**即兴反应。

**不做全量 N 阶涟漪**（上游非目标 §7）。一阶 + "让 NPC 从新状态即兴" 足够。

### 3.4 作者结构里程碑（剧本模式，schema）
通用 schema（任何题材作者可填，落在 world/script 数据里，类比 `events_data`/`endings`）：

```json
{
  "milestone_id": "huafei_fall",
  "fact_key": "consort_huafei.alive",
  "fact_text": "华妃年世兰已于本回合被赐死。",
  "kind": "entity_removed",
  "target_ref": "年世兰",
  "condition_tree": { "...": "复用现有 world_state.<key> DSL" }
}
```

> 本期**不做创作工坊自动生成结构里程碑**（下游另立，见 §12）。引擎先认这个 schema；现有种子可手填，无则该世界只在自由模式判官路径下演化。

---

## 4. 持久层：结构账本

**GameState 扩展**（`engine/state_manager.py:65`），不建新表（已持久化、已有"活软层"读写模式、零 migration churn）：

```python
structural_facts: list[dict] = field(default_factory=list)
# 每条: {fact_key, fact_text, kind, target_ref, effective_round, cause, provenance}
# provenance: "authored_milestone" | "free_arbiter" —— 供可观测/评测
```

- `to_dict`/`from_dict` 同步序列化（与现有字段一致）。
- **Overlay 应用**：新增 `apply_structural_overlay(world_data, structural_facts) -> world_data'`，在拼脊柱前把账本叠到种子上：
  - `entity_*` → 改写对应 NPC 描述（"华妃年世兰（已于第 12 回合赐死，不在人世）"）；
  - `world_fact_changed` → 改写 `base_setting` / 地点文本。
  - **覆盖面必须同时含 NPC 与 base_setting/地点**（去宫斗化见 §6 破绽 3）。
- **快照保 cache**：overlay 结果按 `(seed_version, ledger_hash)` 快照缓存；账本不变则脊柱字符串稳定 → prefix-cache 命中。
- 落点：`services/game_service.py` 拼 `world_data` 处 + `build_director_system_v2`（`prompts.py:795`）消费前套 overlay。

---

## 5. 导演能动性（治问题 ①，纯软层，独立于结构管线）

问题 ① 不需要任何结构机制——导演**已有**杠杆（`DirectorResult`：`narrative_pressure` 默认 `"advance"`、`dramatic_intensity`、剧本模式 `event_fire_intent`，见 `director_agent.py:250-253`），只是 prompt 把它的手绑住了。

- **解开 prompt 的手**：允许导演在玩家跑偏/弱输入时**主动推进**（软层：上线索、让 NPC 主动靠近、抬 `dramatic_intensity`、剧本模式催 `event_fire_intent`）——**推世界但不替玩家行动**（"中间档"，区别于 railroad）。
- **弱输入 nudge**：玩家连续 N 回合弱输入（已有 `player_input_weak` 信号，`prompts.py:799`）→ 确定性地提升推进力度。
- **明确区分两种"推"**：
  - *软层 steering*（本节）：常态、低风险、不改脊柱；
  - *结构提议*（§3）：罕见、走判官闸、可改脊柱。
  二者都让世界"动"，但量级与把关完全不同。

---

## 6. 通用性铁律：4 个破绽与修正（用户核心顾虑，单列）

设计自审跑过非宫斗题材后揪出 4 处"偷偷按宫斗塑形"，均已并入上文，此处汇总以备实现时核对：

| # | 破绽（宫斗味） | 修正（题材中立） | 落在 |
|---|---|---|---|
| 1 | 判官只问"角色愿不愿意"（宫斗靠权威拍板） | charter 放大到"世界既定逻辑（角色+设定+因果）是否足以自洽导致"；角色性格只是角色驱动题材的主轴 | §3.2 |
| 2 | 顶假断言只让"角色反对"，无对抗角色题材空转 | 分级反应：有该在意角色→角色反对；无→环境/叙事不予承认（即"软架空"，合法保留） | §3.2 |
| 3 | 级联/overlay 默认事实挂在某 NPC 上 | overlay 同等覆盖 base_setting/地点/世界真相；级联按机械后果分流不假设挂角色 | §2.2 §4 |
| 4 | `kind` 按剧情品类分会过拟合，言情关系型无家 | `kind` 按"需要哪种一阶机械清理"分；关系型归 `relation_redefined` | §2.2 |

**去宫斗化一句话内核**：结构变更提交的前提是"这个世界的既定逻辑（角色 + 设定 + 已发生因果）足以、且自洽地导致它"——角色驱动题材里它表现为"人物性格支不支持"，但机制不假设一定有权威角色拍板。

---

## 7. 与现有系统的关系（不重建）

- **`WorldSimulator.tick()`（软层运动）已有**：每回合推进 NPC 意图、触发作者事件、生成世界/环境事件。**不重建**，结构层叠在它之上。
- **`merge_ai_ending_judgment`（结局裁决）**：结构管线与它同形，复用其"提议+校验"经验与代码形状；`_resolve_ending`（`orchestrator.py:180`）旁边并入结构提交点。
- **`condition_tree.py`**：剧本模式结构里程碑直接复用（认 `world_state.<key>`）。
- **`stance_inference.py`**：自由模式判官复用其 cheap-LLM rare-fire 模式。

---

## 8. 落地顺序（一套机制一次建，分段验证）

"一次到位"指**一次性建完整套机制**；落地按可验证增量分段，每段带测试、跑通再下一段。**不是分期砍功能。**

| 段 | 内容 | 验证 |
|---|---|---|
| **S1 导演 steering** | §5：解开 prompt + 弱输入 nudge（纯软层，无新数据） | 跑偏玩家被温和拽回；非 railroad |
| **S2 否决+分级反应** | §3.2 reject 半边 + §3.1 提议字段（检出结构断言→分级反应）。**不需账本。** | 假断言被顶回（角色反对/环境不认），≥3 题材 |
| **S3 结构账本+剧本里程碑** | §4 账本 + overlay + §3.4 作者里程碑（condition_tree，确定性，无 LLM） | 作者弧真结构演化；脊柱叠账本；cache 只破一次 |
| **S4 自由模式判官** | §3.2 自由模式判官（rare-fire 第二段）+ 提交+一阶级联 | 挣来的结构变化提交；凭空的被否；≥3 题材 |

**Flag**：`structural_evolution_free_mode`（仅 S4 自由模式判官路径）——**只作 dev/评测对照旋钮**（A/B"开了后像不像原著掉没掉"），非上线闸门（用户已确认未上线、不设安全顾虑）。S1–S3 默认开。

---

## 9. 错误处理与边界

- **判官调用失败/超时** → 默认**否决** + 软层环境不予承认（绝不默认放行写脊柱）。
- **提议字段缺 `in_world_cause`/`justification`** → 视为无效提议，丢弃（类比 `merge_ai_ending_judgment` 对不匹配 ending_type 的处理：surface 日志 + 不写）。
- **级联部分失败**（如 `target_ref` 找不到实体）→ structlog warning，跳过该实体清理，不阻断回合（参考 `events_data_unknown_kind` 既有处理）。
- **账本与种子冲突**（罕见）→ 账本优先（它是"后发生的事实"）。
- **`fact_key` 重复提议** → 幂等：已存在相同终态则忽略；状态推进（如 alive→dead）则更新 `effective_round`。

---

## 10. 测试策略（轻量 + 通用性硬核对）

- **单元**：`structural_arbiter`（剧本 condition_tree 路径 + 自由判官 verdict 解析 + 失败默认否决）、`apply_structural_overlay`（NPC + base_setting 两类）、一阶级联（4 个 kind 各一）、否决分级反应（有/无对抗角色两型）。
- **通用性硬核对（铁律）**：判官/级联/overlay 的测试用例**必须横跨 ≥3 题材**（如：宫斗位份、悬疑关键人物之死、科幻阵营结盟/言情决裂），证明无题材专属分支。
- **in-process 管线**：构造"玩家凭空声称"→否决+反应；"作者条件满足"→提交+脊柱变化；不依赖真 LLM（判官用 fake verdict）。
- 不追覆盖率；边角不补大量测试（项目原则）。

---

## 11. 数据流（单回合，含结构管线）

1. 玩家输入 → `WorldSimulator.tick()`（软层推进，已有）。
2. 拼 `world_data` 时套 `apply_structural_overlay`（脊柱=种子+账本）。
3. 导演单次调用：输出常规字段 + 可选 `structural_change_proposed`（§3.1）+ 软层 steering（§5）。
4. **若有结构提议** → `evaluate_structural_change`（§3.2，rare-fire）：
   - 通过 → 写账本（§4）+ 一阶级联（§3.3）+ narrator 一次世界反应 beat；
   - 否决 → 分级世界反应，不写账本。
5. NPC 从（可能已更新的）脊柱即兴反应。
6. `_resolve_ending` 等照旧。

---

## 12. 非目标（明确不做）

- ❌ yes-man（玩家说什么世界就变什么）。
- ❌ 全量 N 阶级联涟漪；只做一阶 + NPC 即兴。
- ❌ 任何题材专属代码分支（铁律）。
- ❌ 本期不做创作工坊**自动生成**结构里程碑（引擎先认 schema，生成端下游另立）。
- ❌ 不为结构变更加独立前端 UI；变更以世界内 narrator beat 呈现（YAGNI）。
- ❌ 不在常态回合引入额外 LLM 调用（判官 rare-fire）。
- ❌ 不重建 `WorldSimulator`。

---

## 13. 留给实现计划（writing-plans）细化

- `DirectorResult` 字段解析/校验的具体位置与 normalize 规则。
- `structural_arbiter.py` 的 prompt 与 cheap-LLM slot 绑定（走 `LLMRouter` + 模型后台 slot，不硬编码）。
- overlay 快照缓存键与失效。
- 导演 v2 prompt 的 steering 与结构提议增补文案（中文）。
- S1–S4 各段的 TDD 任务拆分。
