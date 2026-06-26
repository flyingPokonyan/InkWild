# 生成管线涅槃：从「一盘散沙」到「世界圣经 + 绑定契约」

> 状态：**已拍板，分相开工**。本 plan 取代 [`2026-06-25-generation-quality-loop-reopen.md`](2026-06-25-generation-quality-loop-reopen.md)（那份的诊断/证据仍有效，本份把"P0/P1/P2 三个补丁"升格成"围绕单一事实源的演进"）。
> 诊断证据见旧 plan §1（7 世界质检）；本份只讲**目标架构 + 怎么分相落地**。

---

## 0. 一句话

把生成管线从「一串各自自由发挥的 LLM 调用」改成「**所有阶段围绕一份逐步冻结的世界圣经（WorldSpec）运转**」——每个阶段读冻结的事实当硬约束、产出后写回并冻结自己那层、下游只能在冻结骨架上扩写血肉、违约就定向回炉。

**不是重写**（DAG 骨架、节点级已拆的 ~20 个坑全保留），**也不是补丁**（每一相朝同一靶子收敛、消灭的是一类 bug 不是一个实例）。

---

## 1. 为什么不是"补丁"也不是"重写"

- **过去像打补丁**：不是因为步子小，是因为**反应式**——哪疼治哪，没有统一靶子。典型反例：为治"主角消失"加的 `must_have backfill`，这个补丁**自己制造了新病**（把评分撑成恒满 → 裁判变瞎）。补丁生补丁。
- **演进 ≠ 补丁**：唯一区别 = 每次改动是否朝"声明过的目标架构"走、是否消灭一类 bug。满足这条，小步也是涅槃。
- **不重写**：历史上每个成功修复都是"节点手术 + 真实评测验证"，从无一次性大重写成功。DAG 能完整表达"绑定契约 + 有界 loop"，架构无表达天花板；重写只会把 ~20 个已拆的 production 坑清零重踩。
- **"怕不能一次到位" → 正是分相演进的理由**：每相独立可验，错了在下一相前调；大爆炸重写才是最可能"不能一次到位"的。

---

## 2. 靶子：世界圣经（WorldSpec）

核心机制一句话：**读冻结圣经当硬约束 → 只产血肉或扩未冻层 → 按契约校验 → 违约定向回炉那一个阶段。**

原则：**冻骨架，不冻血肉。**（防"世界变死板"——性格/台词/秘密/具体剧情照样自由发挥。）

| 层 | 冻结于阶段 | 内容（硬约束，下游不可改） | 现状 |
|---|---|---|---|
| **L0 前提** | 研究 / world_base | 名 / 年代 / 题材 / 核心冲突 / 语气规则 / **版本锚定(canon_note)** | IP 有雏形，原创=0 |
| **L1 地理** | world_base（+ 角色后 union-back 扩一次再冻） | **权威地点集**：下游只能从中选 | 有 locations，但不绑定 |
| **L2 阵容** | roster + 导演裁决 | 名册 + 定位 + **关系网** + `must_have` / `in_continuity` / `playable` | IP 有，原创靠自由发挥 |
| **L3 事件骨架** | shared_events | 关键节点 + 涉及谁 | 有但不回炉校验 |
| **血肉（不冻）** | 各阶段自由发挥 | 性格 / 台词 / 秘密 / 知识 / 能力 / 具体剧情 | 保持现状 |

**通用阶段契约**（治"散沙"的锁）：每个生成阶段 = `read(frozen spec) → produce(flesh / extend unfrozen layer) → validate(contract) → on fail: bounded repair(only this stage, ≤N)`。
这是把你们打赢 LLM 自由发挥的老招（best-of-N / must_have 闭环 / prune）**上升成架构**，不再每次重新发明。

---

## 3. 旧坑如何被"吸收成契约"（不是再打一遍补丁，是变成不变量）

| 历史坑（曾经的补丁） | 升格成的契约 / 不变量 | 落在 |
|---|---|---|
| IP 识别离线认不出 → grok + best-of-N | L0/L2 输入质量：识别 best-of-N（已在）；**软裁判 best-of-N**（新） | 相1 |
| world_base 坏 JSON 静默掉兜底 | 解析失败 → TransientError 重试（已在） | — |
| roster 关思考漏 must_have | 规划步 reasoning-on（已在） | — |
| must_have 无闭环 → backfill 补占位 | **真实覆盖扣 backfill**（诚实分）+ **1:1 阶段内回炉**（消灭薄 backfill） | 相1 / 相2 |
| schedule 地点悬空 | **地点 union-back 对账**（L1 冻结后并回再冻） | 相2 |
| 评分奖数量、给不出低分 | **诚实硬分**（扣 backfill/prune + 收紧 structure） | 相1 |
| 软评不进总分、触发器永不响 | **两数门控**（overall 诚实 + blocking_flags/shippable 旁路） | 相1 |
| IP 跨时代/多版本糅合（如鸢/十日终焉） | **导演裁决 + in_continuity 降级不删除**（L2 冻结） | 相2 |
| 下游与上游不一致（散沙根） | **契约绑定：validate→定向回炉**（非自主 loop） | 相3 |
| 原创世界从头自由发挥 | **原创世界圣经规划步**（L0-L2 显式产出） | 相4 |

---

## 4. 分相落地（每相：可独立上线 + 真跑一个世界验证 + 杀一类病）

| 相 | 内容 | 杀掉的病 | 真跑验证 | 状态 |
|---|---|---|---|---|
| **1 可信裁判** | 诚实硬分 + best-of-N 软裁判 + 两数门控（替 cap-to-55） | "评分瞎"（无标尺没法量后续） | 7 世界回填，十日终焉/如鸢现形红旗、甄嬛掉分 | ✅ 已落（待测试 + 真跑）|
| **2 冻结骨架** | 冻地点(union-back) + 冻阵容(导演裁决 / in_continuity / canon_characters) + roster 1:1 回炉 | 跨时代/版本糅合 + 地点漂移 + 薄 backfill | 重生如鸢（卫青/霍去病消失）/ 十日终焉（单版本） | 🟡 半落 |
| **3 契约绑定** | `validate_world_shape` 残余违约（事件引用未知 NPC 等）→ 定向回炉对应阶段（有界 ≤2，flag 后藏） | 下游与圣经不一致的残余 | 故意注入漂移 → 看它被修回 | 🔵 未开（相2 真跑后定频率再建）|
| **4 原创圣经** | 原创世界补显式 premise+阵容+地理规划步，产出 L0-L2 | 原创世界散沙（最严重、相2 未覆盖） | 重生一个原创世界 | 🔵 未开（数据驱动，可选）|

**铁律（防再变补丁）**：每相先上线 + 真跑一个世界验证过，才开下一相；任何改动若不朝"圣经+契约"靶子走就不做。

**为什么 3/4 暂不写**：契约→回炉的上限 = 裁判质量（相1 刚修好），且残余违约频率要相2 真跑后才知道；自主/无界 loop 明确不做（长结构化产物自主化反而更不一致、成本 5-20x）。原创圣经要等相2 证明"只靠裁决覆盖不了原创"。

---

## 5. 已落代码（相1 全 + 相2 前半，未 commit / 未测）

**相1（可信裁判）**
- `services/generation_rubric.py`：删 `apply_soft_floor`（cap-to-55 补丁）；`compute_hard_metrics` 诚实化（真实覆盖=覆盖−backfill；structure 分母 char×3→×1.5；prune −4/个封顶 −20）；新 `compute_blocking_flags(soft)→(flags, shippable)`。
- `services/world_critic_service.py`：`score_world_soft` 升级 **best-of-N（vote=3，逐维中位数）**。
- `services/world_quality_scorer.py`：两数门控替 cap；overall=诚实硬分；落 blocking_flags/shippable；must_have 只数 in_continuity。
- `models/world_quality_score.py` + 迁移 `c9d2e4f6a1b8`：加 `blocking_flags`(JSONB) + `shippable`(bool,index)。
- `api/admin.py` + `admin-frontend`（列表红旗 chip + 详情横幅 + types）。

**相2（冻结骨架，前半）**
- `schemas/ip_knowledge_pack.py`：`IPCharacter` 加 `in_continuity`/`arbitration_note`；`IPKnowledgePack` 加 `canon_note`/`playable_archetypes` + `canon_characters()`/`canon_character_names()`；`must_have_character_names()` 过滤 in_continuity。
- `services/ip_research_pipeline.py`：`_arbitrate_canon`（导演裁决，研究层尾部、持久化前；版本锚定 + era 过滤[LLM 判+护栏] + 可玩生态位建议；**降级不删除**；fail-open）；quality gate 改数 canon。
- 消费方全改走 canon 视图：`character_roster_builder`（optional 清单 / `_prune_to_canon` 白名单 / 批次 grounding / + 注入 playable_archetypes 引导）、`shared_events_builder`、`script_roster_augmentation`、`lore_pack_builder`、`world_creator_agent_v2._backfill_missing_must_have`。
- `services/world_creator_agent_v2.py`：`_union_back_locations` helper（已写，**待接进 run()**）。

**相2 待写**：`_union_back_locations` 接进主流程（角色后，更新 `world_base["locations"]` + `locations` 变量）；`build_characters_in_batches` 的 `character_missing` 从 warn 改 **1:1 定向回炉（有界 +1 批）**；重写 `tests/test_generation_rubric.py`（旧的测 `apply_soft_floor` 已删，会 import 失败）。

---

## 6. 偏离旧 plan 的两处（已与用户确认）

1. **playable 生态位 = 软引导，不硬去重**：导演产 `playable_archetypes` → 注入 roster 规划（别全挤主角团）；**不**事后按原型删/并 playable——因为恋与深空多个"温柔上司/冷面教官"是**故意同原型的不同恋爱对象**（旧 plan R-3），硬去重会错误合并。
2. **era 过滤 LLM 判、不按 ip_type 硬开关**：prompt 给硬护栏（"宁可少判不可错杀"+"玄幻/科幻/现代的穿越·重生不算跨时代"），避免霍格沃茨/恋与深空误伤。

---

## 7. 红旗（red-team，承接旧 plan §4 仍有效项）

- **导演误删** → 降级不删除（in_continuity flag，可见可恢复），下游 key off flag、代码几乎不动。
- **导演单点故障** → fail-open，失败原样放行脏 pack（退回当前行为）。
- **裁判硬卡发布** → 只出建议分 + 红旗，**绝不硬卡**，admin 仍可发。
- **冻结过死扼杀丰富度** → 只冻骨架（地点集/名册/关系/时间线），血肉自由。
- **地点 snap 挪错角色** → 不 snap，改 union-back（把引用并回，零损失）。
- **成本/延迟** → 导演 +1 次纯推理调用、软裁判 1→3 次，**全在异步生成路径，不碰游玩 TTFT**。

---

## 8. 验证纪律

- 单测：`generation_rubric`（诚实分 + 两数门控）、`score_world_soft` 投票聚合、`_union_back_locations`、`_arbitrate_canon`（fake LLM）。
- 真跑（相验收，需 docker 栈 + 模型 + grok）：相1 回填 7 世界看分变诚实；相2 重生如鸢/十日终焉看 canon 干净；相3/4 各自真跑。
- 存量两脏草稿（十日终焉/如鸢）：相2 上线后**弃用重生成**，别留着当验证基线。

---

## 9. 落地现状（2026-06-26 收口 — 真相以此节为准）

### 各相终态
| 相 | 状态 | 说明 |
|---|---|---|
| 相1 可信裁判 | ✅ 落+部署+真跑 | 诚实硬分 / best-of-N 软裁判 / 两数门控。commit `fe58826` |
| 相2 冻结骨架 | ✅ 落+部署+真跑 | `_arbitrate_canon`（版本锚定 + era 过滤 + playable_archetypes）/ 地点 union-back / roster 1:1 回炉。`fe58826` |
| 相3 **地点冻结** | ✅ 落+真跑 | schedule 硬绑定地点集 + strict 放开 world_base 补地点。`fe58826` |
| 相3 **契约绑定（通用 validate→定向回炉）** | ❌ **未做** | 残余违约（事件引用未知 NPC 等）仍**只报警**。只有地点（union-back）和 roster（1:1）两处有确定性对账，**通用回炉机制不存在**，按"数据证明需要再建"缓着 |
| 相4 原创圣经 | ❌ **砍掉** | 真跑证伪"原创最散沙"——原创不散（撞车9>IP、阵营清晰，因 premise 已给阵营）。真原创病=**抄 IP**（灰烬纪元搬疯狂麦克斯/辐射），`b4143d2` 一行负向 prompt 解决，非新阶段 |

### 计划外新增（本不在 plan，真跑暴露后补）
- **IP 识别联网取证兜底**（`ffc4e2a`+`1f31b3c`）：发现识别器"联网识别"是假的（判断调用 `tools=[]` 从不联网），裸标题网文（十日终焉）被判 original → 相2 整条跳过。修=两遍（参数 best-of-N 快判 + original 时 grok-4.3-fast Live Search **兜底**复判，用识别器自身 llm_router）。详见 [[ip-recognizer-websearch-rescue-2026-06-26]]。
- **grok 模型配置**：识别 = grok-4.3-fast；research_summary 槽（研究 fanout web_search）= grok-4.20-multi-agent-low（实测有 Live Search，研究只用 `result.text` 故 citations=0 无害）；注册了 grok-4.3-fast。

### 现状架构（IP 路径是圣经式，原创不是）
```
[IP 路径 = 圣经式 ✅]
IP识别(L0认定,联网兜底) → 研究fanout(广抓,multi-low) → _arbitrate_canon(冻L0前提canon_note版本锚定
 + 冻L2阵容in_continuity/playable) → 写回干净pack → roster消费canon(strict prune+archetype引导)
 → 详情grounding+1:1回炉 → events/lore消费canon → union-back冻L1地点 → 评分
                          ↑ 每层读冻结canon当硬约束、范围逐层收窄

[原创路径 = 自由+约束，非圣经式（有意）]
描述premise(自带阵容纹理) → roster自由发挥+b4143d2原创性约束 → 详情/events/locations
 → 仍走 union-back地点 + roster 1:1回炉 + 诚实评分（横切一致性，与IP共用）
```

### 三处已知缺口（别再当已完成）
1. **通用契约回炉（相3）没建**——只地点/roster 两处确定性对账，其它违约只报警。
2. **原创路径无 L0-L2 冻结**——靠 premise 质量 + 横切一致性兜底（union-back/1:1/评分/原创约束都对原创生效，故咸城仍 0 backfill/0 warning/100 分）。残留风险=**用户给的原创 premise 太薄时可能散**（garbage-in，非缺机制）。
3. **识别子系统在 slot 体系之外**——`ip_recognition_model` 是 config 默认（非 slot 绑定），`build_recognizer_llm` 直构 GrokProvider。与"LLM 全走 slot"原则有出入，识别模型不可在后台 slot 管理（已手动注册 grok-4.3-fast 进 provider_models 但仍 config 驱动）。

### 验证矩阵（哪个世界验了哪一刀）
| 世界 | 验到的 | 没验到的 |
|---|---|---|
| 哈利波特(fantasy) | union-back/playable/诚实分 | **era/版本裁决**（demoted=0 不触发） |
| 十日终焉(版本糅合) | **识别兜底 + 版本锚定**（ip 4→9，canon_note 压旁支） | 跨时代删除（无此问题） |
| 如鸢(跨时代,本地) | **跨时代角色降级**（卫青/霍去病 in_continuity=False） | — |
| 咸城·潮下(原创赛博朋克) | **b4143d2 原创性约束**（27 名全原创、0 抄 IP） + 横切一致性 | IP 圣经层（原创无） |
