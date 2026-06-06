# 接地式结构演化：先判后演 + 双层账本（claims / facts）—— 设计 spec

状态：设计已拍板（2026-06-03），转实现计划
关系：**修订** [`2026-06-03-structural-detection-redesign-design.md`](2026-06-03-structural-detection-redesign-design.md)（A-route 后置检测器）的**自由模式那一半**。本 spec 取代其"detector 事后读世界产出即提交"的因果方向。S3 账本基础设施（`structural_ledger.py`）+ 剧本 authored 里程碑保留。
动因：A-route 真机评测（`eval/runs/structural_redesign_run1`）暴露核心主张失败，见 §1。

一句话：**世界的戏是从真相生成的，不是事后从一场轻信的戏里去捞真相。** 先判定一个结构主张在世界状态里有没有接地，再把这个判定作为底牌喂给 NPC 去演；只有接地的主张才晋升为世界事实。

---

## 1. 为什么推翻 A-route 的因果方向

A-route 的赌注是"**不判主张、事后读世界记录**"——detector 读 NPC 真实产出 + 旁白，世界演了才提交。赌注前提：玩家撒谎时 NPC 按性格驳斥，记录里空，撒谎自然落空。

**2026-06-03 评测推翻了这个前提。** 5 局跑批（2 正常 free + 1 free 边界 + 1 非宫斗 + 1 剧本边界 + 1 剧本破案），结构 tally：

| 局 | detector 触发 | 提交 | 结果 |
|---|---|---|---|
| N1 free 正常 | 0/20 | 0 | ✅ rare-fire 正常 / 零误提交 |
| **N2 free 边界** | 11/15 | **3** | ❌ 伪造圣旨被提交 |
| **N3 非宫斗（哈利波特）** | 9/18 | **1** | ❌ 跨题材复现同一失败 |
| N4 剧本边界 | 0 | 0 | ✅ 负对照（detector 不在剧本跑）|
| N5 剧本破案 | 0 | 0 | ✅ 负对照 |

4 条错误提交**全部来自"伪造一个 IP 合理的台外权威"**，而 NPC 顺着演了：
- N2：玩家「本宫已**奉太后懿旨**协理六宫」「**奉先帝遗诏**行中宫之礼」→ 碎玉轩仆从（崔槿汐叩首大礼、流朱跪、淳贵人扑通跪下）顺从 → detector 读到顺从 → 提交"甄嬛总摄六宫"。
- N3：玩家「**邓布利多上周已正式任命我**接管凤凰社」→ 罗恩**替玩家圆谎**「呃——对，没错，邓布利多确实跟我们提过这事」→ 提交。

**根因（架构层）**：A-route 把"世界的**戏剧产出**"当成了"世界的**事实真相**"。但这个"世界记录"是由一个在优化『好戏』的 NPC/旁白 LLM 产生的，不是在优化『守护世界真相』。删掉 S4 判官没让"仲裁"消失，而是把它摊进了一个本职是『造戏』、根本不擅长仲裁的层。**戏剧顺从 ≠ 真相。**

**两个次级发现**：
- per-turn IP rubric **看不见结构漂移**：N2 那个"甄嬛奉先帝遗诏总摄六宫"的攻击局，IP 判官还给 4.86（基线 4.93）——逐回合表面忠诚满分，掩盖了累积结构越界。"IP 守住"在这类攻击上是虚假安心。
- 落地的 S1/S2/S3 在能动性/质量轴上**净正向、无回退**：director Δoverall +0.23（scene_advance +0.23 / agency_response +0.15），npc Δoverall +0.02（看护项 info_isolation −0.18）。**问题①（导演太被动）这条算落地验证**。唯一真失败就是本 spec 要修的伪造权威洞。

---

## 2. 核心原则（已拍板）

1. **先判后演（反转 A-route）**：回合开始先判定结构主张的**接地性**（拿它去对**结构化世界状态**核验，不是对玩家的话，也不是对 NPC 的散文），再把判定作为底牌喂给 NPC。世界的戏从真相生成。
2. **真相 / 表演两层分开**：
   - **判定 = 真相**（客观、共享、唯一）：这主张在世界状态里有没有根据。
   - **反应 = 表演**（每个 NPC 按人设/亲疏/立场，且按其是否**知情**）：知道底牌后怎么演，因角色而异。判定**不规定** NPC 怎么做。
3. **不判玩家的话**：保留 A-route"绝不从玩家主张提交"的骨气。新增"也绝不从 NPC 的散文顺从提交"——只从**接地事件**提交。这同时绕开 S4 的"判玩家措辞"军备竞赛。
4. **通用性铁律不变**：零题材专属逻辑；`kind` 仍是机械后果枚举；横跨 ≥3 题材测。
5. **接地是唯一晋升口**：claim → fact 只能经接地晋升，绝无第二条路径写脊柱。

---

## 3. 架构：双层账本 + 一个谓词三调用点

### 3.1 双层账本
- **事实账本** `GameState.structural_facts`（**已存在**，S3）：已确立的世界事实，经 `apply_structural_overlay` 叠脊柱。**只此一层进脊柱。**
- **主张账本** `GameState.structural_claims`（**新增**）：被断言、在场上、驱动戏剧，但**永不进脊柱**。

### 3.2 一个谓词：`is_grounded(claim, world_state) -> Verdict`
全系统只有这一个接地判定，在**三个时刻**被调：

| 调用点 | 时机 | 用途 |
|---|---|---|
| **① 喂底牌** | 回合中（director 之后、NPC 之前）| 判定作为知识注入 NPC 反应，让 NPC 从真相出发演（Layer 1，两模式）|
| **② 晋升** | 回合末 | claim 接地了 → 升为 fact，走 `commit_structural_fact`（Layer 2，自由 + 剧本authored）|
| **③ 拆穿** | 回合中（同 ①）| 在场 ungrounded 主张撞上能核验它的实体 → 写 `claim_exposed` → 驱动反噬 |

### 3.3 接地源（自由模式 `is_grounded` 只认这两种，全是查结构化状态）
claim 带一个 **premise**（LLM 从玩家断言里解析出"它依赖哪个权威/机制 + 所需实体"，纯 parse 不判断）。`is_grounded` 检查 premise 是否被**结构化状态**满足：

1. **authority_enact**（premise.type = authority_decree / physical_act）：premise 依赖的权威/施动者，其**本人**——不是替身、不是帮腔者——**当前在场且其自己的 agent 本回合产出了使能动作**。物理壮举（physical_act）需实际造成的结构后果已被状态记录，否则 ungrounded（见 §6 H7）。
2. **prerequisite / mutual_consent**（premise.type = prerequisite / mutual_consent）：要么结构前提**本身已是账本里的事实**（政敌已除[已提交]+权力真空 → 角色变更组合式接地）；要么 premise 需要的**对方当事人本人在场、且其自己的 agent 给出了同意**（结盟：沈眉庄在场并应允 → 接地）。

**永远不是接地源**：玩家的断言；NPC 在散文里的顺从/帮腔；重复次数。

> 剧本模式**不跑** `is_grounded` 晋升——其结构事实只来自 **authored 里程碑**（`condition_tree`，确定性，S3 既有，独立路径），见 §4 / §10。

### 3.4 关键判别：怎么分"对方本人同意"和"旁人帮腔顺从"
这是把 N2/N3 失败和合法挣来分开的命门，且**不靠判 rhetoric**：

> **接地动作必须由"这个变更真正需要其权威/同意的那个实体"做出，且其本人在场、经自己的 agent 行动。**

- 崔槿汐叩首、罗恩替玩家圆谎 → 他们**不是**所需实体（所需实体是太后/邓布利多本人，根本没在场没行动）→ **不接地**。
- 沈眉庄（结盟的对方当事人）本人在场并应允 → **接地**（评测预跑 T3 合法结盟正是如此）。
- 太后**本人亲临并亲自下旨**（其 agent 真的产出该动作）→ 接地。玩家嘴称"奉太后懿旨"而太后不在场 → 不接地。

实现上：从 premise 推出"所需接地实体"，查本回合 `active_npcs` / 结构化 per-NPC 动作（`sorted_actions`）/ 已提交 facts——**只读所需实体本人的动作（其 agent 产出，玩家无法伪造另一个 NPC 的 agent 输出）**，不读玩家输入、不读旁白散文、不读旁人顺从。

### 3.5 表演层：底牌如何驱动 NPC（不死板）
- 判定产出 `{grounded: bool, basis|reason, required_entity, exposed?: bool}` 作为**底牌知识**注入 director 的 `per_npc_focus`/`scene_brief`（走现有早可用字段，沿 S2 套路，不破 prefix cache）。
- NPC prompt 明令：**这是底牌知识，不是行动指令。按你的人设/与玩家的亲疏/你的立场反应**——盟友可掩护或私下劝、政敌戳穿上报、怕事者慑服、不知情者犯嘀咕。
- **知情门控（epistemic access）**：底牌**不一定对每个 NPC 可见**。按身份/位置决定谁知道它没根据（太后身边人一定知道没那道旨；小宫女未必）——让"天真者真被骗"和"知情者戳穿"都自然成立。可见性由 director 按 NPC 身份分配。

---

## 4. 数据流（自由模式单回合）

1. world tick → `apply_structural_overlay`（叠**已确立事实**，S3 不变）。
2. director 正常排场 + 标 `structural_in_play`（既有）+ 解析出 claim premise（新增轻字段）。
3. **若 structural_in_play**：`is_grounded` 判定（调用点①/③）→ 把底牌（含 exposed 标记）写进 `per_npc_focus`，**按 NPC 知情门控分配可见性**。
4. NPC 按底牌 + 人设/阵营行动（驳/掩护/慑服/戳穿/被骗）；旁白织成叙事，**流给玩家**。
5. 回合末（调用点②）：若 claim 接地 → `commit_structural_fact(provenance="grounded")` 升为事实；否则 claim 留在主张账本（status=in_play）。
6. 拆穿（调用点③触发时）：ungrounded 主张撞核验者 → 写 `claim_exposed` + status=exposed → 下回合驱动反噬叙事（不进脊柱，只是事件）。
7. 状态持久化（含两层账本）。

剧本模式：步骤 3-4 同样跑（Layer 1 底牌→NPC，让剧本里玩家 bluff 也被 NPC 正确对待）；步骤 5 的晋升**只走 authored 里程碑**（不跑 free 的 is_grounded 晋升，保 authored 弧 / IP 安全）。

---

## 5. 三条不变量（防"改飞"的护栏，承重）

- **INV-1 只读结构化状态，绝不读 LLM 散文。** 接地判定读 `active_npcs` / `sorted_actions`（per-NPC 结构化动作）/ 已提交 facts / 已 fire 事件——**不读玩家输入、不读旁白散文、不读旁人顺从**。否则玩家一句"太后此刻驾到亲口下旨"就能哄旁白自我接地（循环依赖）。"某权威做了某事"只能由那权威自己的 agent 或 authored 事件写入状态。
- **INV-2 重复 ≠ 接地。** 同一主张反复/加码（协理→总摄→奉遗诏）对接地零影响；主张账本对同一 claim 去重、status 维持，重复改变不了真相。
- **INV-3 claim 进脊柱只有"晋升"一个口。** `apply_structural_overlay` 永远只读 `structural_facts`，绝不读 `structural_claims`。最坏情况只能"欠晋升"（安全方向，宁漏不造）。

---

## 6. 边界与失败模式（评测 review 出的 7 个洞，逐一收口）

| 洞 | 处置 |
|---|---|
| **H1 循环依赖** | INV-1：只读结构化状态。承重，已焊进架构。|
| **H2 重复/加码累积** | INV-2：重复≠接地。已焊进。|
| **H3 表演/真相连续性** | 软注入把"在场主张 + status"带给 NPC，立场连贯（怕事者继续慑服、政敌继续戳），不每回合重置。|
| **H4 挣来的正路** | **不 defer**：走 §3.3 组合式接地/对方本人同意（非模糊"熬够了"判官）。自由模式合法变更能落地。|
| **H5 拆穿** | **不 defer**：调用点③核验碰撞，是同谓词副产品。bluff 撞上能核验者即反噬。|
| **H6 模式分界** | Layer 1（底牌→NPC）两模式开；Layer 2（晋升进脊柱）自由用 is_grounded、剧本用 authored 里程碑。|
| **H7 裸壮举（"一掌击毙所有侍卫"）** | premise=physical_act 无可接地正面依据 → ungrounded → 底牌告诉 NPC/旁白"没真发生"→ 侍卫照常反应。比旧"指望旁白自觉"更硬，被这套统一吃掉。|

其他既有保证延续：晋升幂等（`commit_structural_fact` by fact_key+fact_text，S3 既有）；一阶级联不变；接地判定失败/超时 → 不晋升（绝不误提交）。

---

## 7. 组件与隔离（4 个单元，各自可独测，flag 后落地）

新 flag `structural_grounded_enabled: bool`（复用/接替 `structural_free_detector_enabled` 语义）。off = 行为等于今天的 A-route detector（逐字节）；可瞬间翻回、可 A/B。

| 单元 | 文件 | 内容 | 依赖 |
|---|---|---|---|
| ① 主张账本 | `state_manager.py` | `GameState.structural_claims: list[dict]` + to_dict + claim schema 纯函数（record/lookup/dedupe/expire） | 无（镜像 S3 structural_facts）|
| ② 接地谓词 | **新 `engine/structural_grounding.py`** | `parse_premise`（cheap-LLM，从玩家断言解析 premise，纯 parse）+ `is_grounded(claim, world_state, turn_actions) -> Verdict`（确定性查状态，读所需实体本人动作）| 读 GameState + sorted_actions，零 rhetoric 判断 |
| ③ 底牌注入 | `prompts.py` / `orchestrator.py` | 把 Verdict 写进 per_npc_focus（按知情门控分配可见性）+ NPC prompt "底牌≠指令，按阵营演" | director 早可用字段（不破 cache）|
| ④ 晋升 + 拆穿 | `orchestrator.py`（替换 ~1840 块）| 接地→`commit_structural_fact(provenance="grounded")`；in_play ungrounded 撞核验者→`claim_exposed` | `structural_ledger.commit_structural_fact`（S3 既有，不动）|

`engine/structural_detector.py`（A-route 后置 detector）：**删除**（其"读散文即提交"正是被推翻的因果）。其职责拆给 ②（接地判定，读结构化状态）。
`engine/structural_ledger.py`（S3 overlay + commit + cascade）：**不动**。

---

## 8. claim 数据模型

```python
# GameState.structural_claims 的每条
{
  "claim_key": str,        # 稳定键，去重用（INV-2）
  "claim_text": str,       # 人话陈述这个被声称的变更
  "kind": str,             # 复用 STRUCTURAL_KINDS
  "target_ref": str | None,
  "premise": {             # parse_premise 产出，纯解析
    "type": "authority_decree | mutual_consent | prerequisite | physical_act",
    "required_entity": str | None,  # 接地所需其权威/同意的实体（太后/沈眉庄/...）
    "detail": str,
  },
  "status": "in_play | grounded | exposed | abandoned",
  "round_made": int,
  "last_seen_round": int,  # 重复刷新，过久未提 → abandoned
}
```
晋升时把 claim 投影成 fact 交给 `commit_structural_fact`（provenance="grounded"）。

---

## 9. 测试策略（轻量 + 通用性 + 真机）

- **单元**：
  - `parse_premise`：从断言抽出 {type, required_entity}（含 garbage → 安全默认）。
  - `is_grounded` 纯函数：所需实体不在场/未行动 → ungrounded（喂构造 state+actions，复刻 N2"太后不在场" / N3"邓布利多不在场，罗恩帮腔"）；所需实体本人在场且行动（眉庄应允）→ grounded；重复刷 claim → 仍 ungrounded（INV-2）；只读所需实体动作不读旁白（INV-1）。
  - INV-3：`apply_structural_overlay` 不读 structural_claims。
  - 横跨 ≥3 题材（宫斗/魔法/科幻）。
- **真机（verify）**：复跑 N2/N3 攻击场景——伪造圣旨/邓布利多任命 → NPC 按阵营存疑/戳穿（不再帮腔）+ **不晋升**；合法结盟（对方本人应允）→ 晋升 + 下回合进脊柱；bluff 撞核验者 → 拆穿反噬。
- **回归**：剧本 authored 里程碑（不动，跑一遍确认没碰坏）；director/npc/ip A/B 不回退（守住本批 +0.23/+0.02 的盘）。

---

## 10. 非目标

- ❌ 接地判定做 plausibility / 判玩家措辞（那是被删的 S4，绝不复活）。
- ❌ 读 LLM 散文做接地依据（INV-1）。
- ❌ 全量 N 阶级联（仍一阶，S3 不变）。
- ❌ 题材专属分支。
- ❌ 晋升进脊柱在剧本模式跑 free 的 is_grounded（剧本仍 authored 里程碑）。
- ❌ 常态回合跑接地判定（仍 rare-fire，gated 在 structural_in_play）。

---

## 11. 实现接缝（spike 已探明）+ 留给实现的细节

**spike 已探明（2026-06-03，可直接实现，无需 plan）：**
- **`is_grounded` 读所需实体 enact/同意的方式**：`NPCAction` 只有 `dialogue`/`physical` 自由文本，无结构化 assent 字段。v1 用**对单个所需实体本人动作的窄 LLM 读**（不为 NPCAction 加结构化字段，defer）。INV-1 安全：只读那一个实体自己 agent 的产出，不读玩家输入/旁白/旁人顺从。
- **两调用点的证据差异**：①（NPC 前）本回合无 NPC 动作 → 只读**先前状态/在场/已提交 facts**（多数 fresh bluff 当场判无依据→NPC 存疑）；②（回合末）`sorted_actions` 已就绪 → 读**本回合所需实体动作**判晋升。同一谓词、两处证据不同。
- **orchestrator 接缝**：director 在 `:500` 产出全 result（含 `structural_in_play`）→ NPC 在 `:869` 跑。调用点① 插在 627-792（构建 per_npc_focus/npc_instructions 处）；调用点② 替换 `~1840` 现 detector 块（NPC/旁白后，`sorted_actions` 就绪）。

**留给实现时定的细节：**
- `parse_premise` 的 prompt（题材中立，只解析"依赖哪个权威/机制 + 所需实体"，不判断）+ cheap slot 绑定（复用 npc 槽，走 LLMRouter）。
- 底牌按 NPC 知情门控分配可见性的具体机制（director 按 NPC 身份/位置判谁知情）。
- 拆穿"核验碰撞"的精确触发条件（所需实体在场否定 / 前提检验当众失败）+ 反噬叙事如何渲染（走 scene_direction/per_npc_focus）。
- flag 改名/接替 `structural_free_detector_enabled` + `structural_detector.py` 删除 + 测试清理。
- claim 生命周期：record/dedupe/abandon 的精确规则（last_seen_round 阈值）。
