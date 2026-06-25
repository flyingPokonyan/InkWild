# 生成质量：从「开环流水线」改成「导演 + 契约 + 可信裁判」

> 状态：诊断已坐实 + 设计已自审（red-team），**待拍板分期开工**。已落地的只有过渡用的 ① 软评封顶（未 commit/未部署，P0 会把它扶正替换）。
> 前置：本 plan **重启** [`2026-06-24-generation-agentic-loop.md`](2026-06-24-generation-agentic-loop.md) §9 的 backlog（当时基于「看了 2 个世界、质量已够好」搁置；本次 7 世界质检证伪该前提）。
> 相关：[`2026-06-22-world-gen-thickness-and-must-have.md`](2026-06-22-world-gen-thickness-and-must-have.md)（research/roster 层路线）。

---

## 0. 一句话结论

06-24 把「对结果负责」**只设计成事后返工闭环**，又因「质量已够好」搁置。本次质检发现两件事：
**① 质量没那么好**（7 个里 2 个有结构硬伤却拿 99 分）；**② 观察机制是瞎的**（overall 只算硬指标，唯一抓到问题的软分不进总分，「系统性低分」触发器永远不响）。

修法**不是**把整条链路改成自由 Agent（06-24 §1 已论证那是负债，CLAUDE.md 也禁止引第二套编排框架）。而是让现有 DAG 骨架不动，插三件「负责」的事：
**导演节点（事前收敛裁决）+ 契约执行（确定性对账）+ 可信裁判（评分重做）**，事后返工循环只留给长尾、且只在数据证明前三件不够时才建。

「自主」的是**结果**（该有什么、够不够好），不是**过程**（步骤顺序仍固定）——这正是 06-24「对结果自主 ≠ 对过程自主」的落地。

---

## 1. 质检证据（2026-06-25，生产 06-24 批 7 个世界）

| 世界 | overall(硬) | ip一致 | 撞车 | 张力 | warnings | backfill | 真实状况 |
|---|---|---|---|---|---|---|---|
| 十日终焉 | **99.8** | **4** | **3** | 5 | 1 | 0 | （亲核纠正）齐夏是**唯一**主角、无第二主线；真问题=两层/两版世界观（造神·神之规则 vs 虚界意志筛选）摊平糅合未取舍 + 多个重复智囊/守护者/算计者撞车 + 一堆"参与者"灌水 |
| 如鸢/代号鸢 | **99.4** | **4** | 7 | 9 | 2 | 0 | 卫青/霍去病（西汉，早 300 年）塞进汉末三国，关公战秦琼 |
| 霍格沃茨 | 92.9 | 9 | 5 | 6 | 32 | 0 | 可玩角色全挤主角团，缺灰色视角 |
| 甄嬛传 | 91.1 | 9 | 7 | 8 | 8 | **3** | 还原度高，但主角靠 backfill 补回 |
| 恋与深空 | 91 | 9 | 6 | 8 | 39 | 0 | 多个「温柔上司/冷面教官」功能撞车 |
| 道诡异仙 | 90.6 | 7 | 8 | 9 | **62** | 0 | 软评尚可，但海量 schedule 地点悬空 |
| 诡秘之主 | 85 | 10 | 9 | 9 | 55 | 0 | 复刻最忠实，硬指标却最低（被结构分拖累） |

**关键事实**：overall（硬指标）全员 85–100，**结构上给不出低分**——40 分 must_have 被 backfill 撑满、40 分只看角色/可玩数量达标、20 分结构分被 `char×3` 分母稀释。唯一抓到真问题的是**软评**（ip/collision），它 100% 不进 overall。结果 §9 的「系统性低分」触发器永远不响——观察层自己瞎了。

---

## 2. 根因：开环堆叠，缺「收敛-契约-校验」（已逐条对到代码）

链路 `A研究 → B世界底 → C角色名单 → D角色详情 → E/F事件 → 评分` 是**逐层开环堆叠**：每个下游把上游产物当「提示词软参考」后各自自由生成，唯一校验（`validate_world_shape`）在最末端**只报警、不回炉**。

| 症状 | 结构根因 | 代码证据 |
|---|---|---|
| 十日终焉多版本糅合 / 如鸢跨时代 | 研究层**广检索无裁决**，多版本/多层设定 + 跨时代材料全进 canon | `ip_research_pipeline.py:49` 四轴全是「多挖人」无 era 轴；`_merge_packs` 并集 + `must_have=OR`（:478）；self-check loop 只 ADD 不删（:744） |
| `_prune_to_canon` 删不掉跨时代角色 | 它只删「白名单外」，而卫青/霍去病**就在**白名单里 | `character_roster_builder.py:144` |
| **must_have 被三处无条件信任** | canon 一旦标错 must_have，下游强制注入、还设成可玩主角，roster planner 排不掉 | roster prompt `:261` + `_ensure_must_have:170`（`is_image_target=True`）+ critic `_backfill_missing_must_have:199`/`_run_critic:1867` |
| 甄嬛 backfill=3 | C→D 契约不可靠：详情批丢了 must_have 只 warn 不回炉，留给 critic 补薄数据 | `build_characters_in_batches` 对 `character_missing` 只 `logger.warning`（:663） |
| schedule 62 悬空 | 地点无单一事实源：B 产 locations、D 各角色自由编活动地点，无闭环 | `_BATCH_SYSTEM` 只 prompt 求（:386）；`validate_world_shape:51` 末端只报警 |
| 评分给不出低分 | 目标函数错：rubric 奖励数量达标，结构上无法表达质量 | `generation_rubric.py:124-128` |
| 能抓跨时代的语义闸关了 | `heavy_critic_characters`（含 `era_anachronism`/`ip_non_canon_extra`）06-24 从同步流程摘掉，现在 `_run_critic` 只剩 shape+backfill+moderation | `world_critic_service.py:188-189`（已不被调用）；`_run_critic:1860` |

---

## 3. 生成 Agent 改成什么（前后对比）

**现在：直线开环。**
```
A研究 ─▶ A+IP研究 ─▶ B世界底 ─▶ C名单 ─▶ D详情 ─▶ E/F事件 ─▶ critic(只报警) ─▶ images ─▶ 评分(瞎)
        多挖·并集·不裁决                各批自由发挥        摘掉了语义检查              只奖数量
```

**改成：同一 DAG，插三件「负责」的事（不引框架，绕现有 async DAG 写几十行）。**
```
A研究 ─▶ A+IP研究 ─★导演裁决★─▶ B ─▶ C(消费契约) ─▶ D(1:1回炉) ─★地点对账★─▶ E/F ─▶ critic ─★可信裁判★─┐
          (在 IP 研究尾部)            ·锁单一主线/版本                                  hard趋势+soft门控  │
          产出干净 canon              ·滤跨时代角色(重新打 flag)                          不过线? ──────────┘
          (重打 must_have/playable)   ·可玩视角生态位去重                                      ▼
                                                                                   ★有界修复★(P3,可选,数据驱动)
                                                                                   只重跑定位到的那一个阶段(≤N次)
```

### 对前沿 agent 模式的借鉴（借模式，不借框架）
对到 Anthropic《Building Effective Agents》的积木——**大部分已有，真正缺的就一个**：

| 模式 | 现状 |
|---|---|
| Prompt chaining / Routing / Parallelization(voting) / Orchestrator-workers | ✅ 现成（DAG / IP-原创分流 / IP 识别 best-of-N 投票 + 研究四轴 fan-out / 角色分批） |
| **Evaluator–optimizer（你说的 loop）** | ❌ 缺——但**它的上限 = 裁判质量**。我们裁判现在瞎的，所以**先修裁判（P0），再修源头（P1/P2），loop（P3）放最后且数据驱动**，否则等于拿瞎裁判去无限返工 |

可直接借的两点：**导演/planner 节点**（事前收敛）+ **结构化共享状态（黑板）**——即下面的「干净 canon」契约对象，取代「每步把松散文本往下游一塞」。

---

## 4. 自审（red-team）：会不会暴露新问题 + 已内建的对策

> 这一节是本次重写的重点：新设计本身会引入哪些风险，逐条想清楚 + 对策落进设计，避免「治旧病添新病」。

| # | 新设计可能引入的问题 | 对策（已写进方案） |
|---|---|---|
| R-1 | **导演误删**：新增一个 LLM 步有权删 canon 角色，删错=静默退化，且没了「并集兜底」 | **降级不删除**：导演只重打 flag（`must_have=false` + 新 `in_continuity=false` + 记 `arbitration_note`），角色仍留在 pack 里、可见可恢复。下游三处 must_have 机制 key off flag，**改 flag 就够，下游代码几乎不动**（与「下架可恢复」哲学一致） |
| R-2 | **era 过滤在奇幻/现代 IP 上误伤**（霍格沃茨/恋与深空没有跨时代问题，硬过滤可能把穿越者/重生设定判错） | era 裁决**仅对历史/古装类**（`ip_type∈{tv,novel,...}` 且 `era` 非空）开；奇幻/现代只跑生态位去重，不跑 era 过滤 |
| R-3 | **生态位去重把本就刻意雷同的角色合并/降级**（恋与深空多个「温柔上司」是不同恋爱对象，故意同原型） | 去重只作用于 **playable 集合的原型覆盖**（别给玩家 5 个近乎一样的可玩视角），**不动全量 cast**——多余的降级成 NPC（`playable=false`），不删 |
| R-4 | **导演成单点故障**：LLM 报错/坏 JSON 时若 fail-closed → 空世界 | **fail-open**：导演失败 → log warning + 原样放行脏 canon（退回当前行为）。它是增强层，不是硬依赖 |
| R-5 | **地点冻结 snap 把角色挪错位**：B 只产 4 个地点，30 角色全 snap 到那 4 个点；或把角色从自然居所挪走 | **不 snap-away，改 union-back 对账**：把 D 引用到的地点**并回** locations 规范列表（按 `_norm_name` 去重），而不是把角色硬拽到已有地点。保证「每个被引用地点都存在」（校验通过）、零损失 richness、不需要 B 完美。B 仍给宽裕地点集 |
| R-6 | **可信裁判硬卡发布**：噪声 LLM judge 把正常世界拦死 | **裁判只出建议分 + 红旗，绝不硬卡发布**（admin 仍可发）。门控阈值保守（ip/collision ≤4 才触），只抓灾难级。`cap-to-55` 这个 band-aid 退役，换成**两个数**（见 R-7） |
| R-7 | `cap-to-55` 本身是补丁（把两个轴塞进一个被压扁的数，丢信息），用户明确「不要补丁」 | overall = **诚实 hard 分**（进趋势）；另出独立 `blocking_flags` + `shippable` 布尔；admin 列表显示 hard 分 + 红旗 chip。不再混压一个数 |
| R-8 | **hard 公式的数量同义反复**：must_have 40 分被 backfill 撑成恒满 → 改公式前数据层就是满的，公式看不出来 | hard 分**按 backfill_count/prune_count 扣分**（这俩信号现已埋点、现成可用）——「靠安全网救回来的」就该低分；同时收紧 structure 的 `char×3` 稀释。**这步独立于 P1/P2 就能让分变诚实** |
| R-9 | **有界修复循环是真管线活**：现 DAG 各阶段靠局部变量串数据，不支持「只重跑某阶段」 | P3 **暂缓**、最后做、flag 后藏、**只在 P0-P2 数据证明不够时才建**；大概率只需「重跑一个阶段」的薄能力，不需要完整 loop |
| R-10 | **裁决可能选错/掏空世界**（多版本糅合的 IP 如十日终焉，自动选一个版本可能选错；真·多路线 IP 若强选一条会丢内容） | 导演锚定一个版本/主线 + **把选择记成可见 `arbitration_note`**，admin 看到不对可换参数重生成；**用户选路线的 UI 旋钮仅为真·多路线 IP 预留、本期不建**（当前 7 世界无一属于此类，见 §7） |
| R-11 | **原创世界（非 IP）跳过整条导演路径**，拿不到收敛红利 | 原创世界本就无 era/continuity 问题；它的撞车病由 **roster planner 自己做生态位规划**（prompt + 后置去重）覆盖——该能力 IP/原创共用。R2 地点对账、P0 评分对原创同样生效 |
| R-12 | **成本/延迟**：新增导演调用在生成关键路径上 | 导演**复用已抓到的研究材料、不发新网络请求、纯推理**（≈ roster planner 量级）；全在异步生成路径，**不碰游玩 TTFT**。roster 1:1 回炉是条件触发的有界 +1 批 |

**自审净结论**：风险全部可控，且关键一招让改动**远比初看小**——
> 导演的杠杆是**改 canon 的 flag**（`must_have`/`playable`/`in_continuity`），不是删数据、也不重写下游。现有 must_have 机制会自动消费干净 flag，做对的事。这把「重构」收敛成「在 IP 研究尾部加一道裁决 + 给 schema 加一个 flag + 评分诚实化」，可控、可回滚、可独立验证。

---

## 5. 方案（落点已对到代码）

### P0 — 评分诚实化（先做：没有可信的数，后面什么都没法量）
- `generation_rubric.compute_hard_metrics`：overall 按 `backfill_count`/`prune_count` **扣分**；收紧 structure 的 `char×3` 稀释（让海量 warning 真压低）。这是诚实的 hard 分，进趋势。
- 把已落地的 `apply_soft_floor`（cap-to-55）**换成两个数**：`overall=hard`、独立 `blocking_flags`（ip/collision ≤ 阈值）、`shippable=bool`。落库 + admin 列表/详情显示红旗。
- **不是补丁**：度量的是我们已采集的真实失败信号（backfill/prune/软评触底），不是硬塞一个封顶。
- 验收：7 世界回填后，十日终焉/如鸢落到不及格 + 红旗；甄嬛因 backfill=3 明显掉分。

### P1 — Canon 收敛裁决（最大杠杆）
位置：**`ip_research_pipeline.build_ip_knowledge_pack` 尾部**（`_consolidate_characters` 之后、quality gate 之前）。这样**持久化到 DB 的 pack 本身就干净**（同时治了 DB 污染），`_last_ip_pack` 下游自动干净，**world_creator_agent_v2 编排零改动**。
- 一次 LLM 裁决（吃已抓材料 + `ip_type`/`era`/`description`）：
  - **版本/continuity 锚定**：多版本/多层设定糅合的 IP（如十日终焉：造神 vs 虚界意志两层被摊平）锚定**一个自洽版本**、其余降级，落 `arbitration_note`（可见）。这是「收敛到一个版本」，**不是**给用户多条路线选——真·多路线 IP（乙女/多结局 VN）是另一类，见 §7。
  - **era 过滤**（仅历史/古装开）：跨时代角色重打 `in_continuity=false`、`must_have=false`。
  - **playable 生态位规划**：标注可玩视角应覆盖哪几类原型。
- schema：`IPCharacter` 加 `in_continuity: bool = True`（+ 可选 `arbitration_note`）。`_ensure_must_have`/`_backfill`/roster prompt 跳过 `in_continuity=false`。**降级不删除**。
- fail-open：裁决失败原样放行。
- 验收：重跑如鸢（卫青/霍去病消失，ip 回升）、十日终焉（单主线，角色不再两套拼接）。

### P2 — 契约执行（消灭 backfill / 地点漂移 / 撞车）
- **地点 union-back 对账**（D 之后一道确定性 pass）：把角色 schedule/initial_location 引用到的地点并回 locations（去重）。源头消灭 `schedule_unknown_location`，richness 零损失。
- **roster 1:1 阶段内回炉**：`build_characters_in_batches` 对 `character_missing` 从「只 warn」改「只重跑缺失的那几个名字一批」（有界 +1 批），干掉 critic 的薄 backfill。
- **playable 生态位去重**（IP 消费 P1 的规划；原创在 roster planner 内做）：playable 集合按原型去重，多余降级成 NPC（不删）。

### P3 — 有界修复循环（事后，可选，数据驱动）
仅当 P0-P2 跑完仍有可观长尾才建。Verdict 含软评维度 → 修复编排器带 fix **有界**重跑对应**单个**阶段（放 images 之前，零图片返工）→ 预算守卫（max 2 轮 + 收敛检测）。flag 后藏，默认 off。

---

## 6. 分期与依赖

| 期 | 内容 | 投入 | 依赖 | 收益 |
|---|---|---|---|---|
| **P0** | 评分诚实化（hard 扣分 + 两数门控替 cap） | 小 | 无 | **先决**：拿到能信的数去量后续 |
| **P1** | Canon 收敛裁决（IP 研究尾部 + `in_continuity` flag） | 中 | 无 | **最大**：治十日终焉/如鸢/跨时代 |
| **P2** | 契约执行（地点对账 + roster 1:1 + playable 去重） | 中 | P1（playable 规划） | 消灭 backfill + schedule 漂移 + 撞车 |
| **P3** | 有界修复循环 | 大 | P0 裁判 | 兜长尾；前三期把触发频率压很低，**没必要别建** |

**建议顺序：P0 → P1 → P2 →（看数据）P3。** P0/P1 可并行起步（互不依赖），但 P0 先有产出，才能客观验 P1。

---

## 7. 待拍板（真正需要你定的）

1. **总方向**：认不认同「导演 + 契约 + 可信裁判，事前收敛优先于事后返工 loop」？（对应 §3/§4）
2. **路线旋钮（R-10，已降级）**：亲核发现十日终焉**不是**多主线（齐夏唯一主角），它走 P1 版本锚定即可、无需用户选。路线旋钮只对**真·多路线 IP**（乙女/galgame/多结局 VN，路线干净互斥，命名 `IP·主线名`）有意义——但**当前 7 世界无一属于此类**。建议：**概念保留、本期不建，待真出现这类 IP 再做**（IP 识别步可顺带探测「该 IP 是否有命名路线」）。你的「让用户选 + IP+主线名」想法对，只是暂无现成对象。
3. **开工点**：先开 **P0（评分诚实化，最快见效、零依赖）**，还是直接 **P1（导演裁决，最大杠杆）**？（我建议 P0 先落、P1 紧随）
4. **两个脏草稿**：十日终焉 / 如鸢——建议**弃用重生成**（canon 已脏在 DB，回填分只是止血，留着污染验证基线）。

---

## 8. 涉及文件（备查）

- `services/ip_research_pipeline.py` — **P1 主战场**：`build_ip_knowledge_pack` 尾部加裁决步；`_RESEARCH_AXES` 不动
- `schemas/ip_knowledge_pack.py` — P1：`IPCharacter` 加 `in_continuity`（+ 可选 `arbitration_note`）
- `services/character_roster_builder.py` — P1：`_ensure_must_have`/`_prune_to_canon` 跳过 `in_continuity=false`；P2：1:1 回炉 + 原创世界生态位规划
- `services/world_creator_agent_v2.py` — P2：D 后地点 union-back 对账；`_backfill_missing_must_have` 跳过 `in_continuity=false`
- `services/generation_rubric.py` / `world_quality_scorer.py` — **P0**：hard 扣分 + 两数门控替 cap（`apply_soft_floor` 退役/改写）
- `services/world_critic_service.py` — P3：`score_world_soft` 升级成 Verdict（含 target_stage 的 fix 指令）

## 9. 已落地（过渡步，P0 会替换）

- **① 软评封顶**：`generation_rubric.apply_soft_floor()`（ip/collision ≤4 → overall 封顶 55）。**未 commit、未部署。** 定位：让你现在就有能信的分，P0 落地后用「两数门控」替换它（不再压扁成一个数）。
- **存量回填**：生产 `world_quality_scores` 把十日终焉/如鸢 99→55（可逆，原值在 `detail.hard.overall_score`）。已执行。
