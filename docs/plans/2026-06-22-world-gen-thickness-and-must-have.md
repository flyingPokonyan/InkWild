# 世界生成：厚度 + must_have 闭环 优化 plan

> 2026-06-22。起因：用户生成甄嬛传（strict 严格复刻），出来只有 6 个角色 / 4 个可玩，
> 皇帝、华妃、皇后三个核心主角全丢。本 plan 定位根因、给分层方案、评估多 Agent research 的 ROI。

## 0. 一句话结论

这不是单个 bug，是三层叠加：①**roster 规划步骤关了思考 + prompt 自相矛盾** → LLM 把硬约束当耳旁风；
②**must_have 没有代码闭环** → 主角掉了没人补；③**研究层在生产只剩 grok 单源单次抓取 + 抽取地板过低**
→ 世界从源头就薄。修法要分层，最高 ROI 的不是加代码闸，而是把 grok 研究做成多角度并行 + 放开抽取目标。

---

## 1. 事故现场（甄嬛传 draft `cd54343a`，铁证）

| 环节 | 实际产出 | 应有 |
|---|---|---|
| ip_knowledge_pack | 10 角色（4 must_have：甄嬛/皇帝/华妃/皇后） | 甄嬛传应有 20-30 named |
| roster（LLM 规划） | 6 个：甄嬛、沈眉庄、安陵容、温实初、苏培盛、叶澜依 | 含全部 must_have |
| **掉的人** | **皇帝、华妃、皇后（4 个 must_have 丢了 3 个）、果亲王** | 一个都不该掉 |
| playable | 4 | 大 IP ≥ 8 |
| critic | 准确报出"皇帝/华妃/皇后缺失" | 但只是 warning，不重试不补，草稿照存 |

运行参数：`fidelity_mode=strict`，IP 识别 confidence 1.0。本该走 T8 硬约束，结果硬约束没生效。

---

## 2. 根因（三层，逐条已验证）

### 层 1 · 规划步骤关了思考 + prompt 自相矛盾（acute，主因）

- **思考被关**：roster 走 `admin_generation` 槽 → 在 `GENERATION_TEXT_SLOT_NAMES`（`model_management.py:136`）
  → `_reasoning_for_slot` 返回 `False`。roster 规划是**约束满足任务**（读 must_have、规划人数、保证主角在场、
  分配 image_target），关思考后模型退化成模式匹配。
  - 当初关思考的理由（`model_management.py:131-135`）是"慢网关上开 CoT 会截断 JSON、丢角色/事件"——
    **但那是 JSON 健壮性问题，被过度泛化套到了 roster 这种纯规划步骤上。**
- **prompt 自相矛盾**（`character_roster_builder.py`）：
  - "必含主线角色：甄嬛/皇帝/华妃/皇后" 只是淹没的一行；
  - 周围全是收缩信号："一律以本清单为准，**宁少勿编**"、image_target"约 6-12 个，**宁缺毋滥**"、
    "禁止新增任何原创"。
  - 收缩信号总音量 >> "必含"单行 → 关思考的模型权衡选"少"。
- **模型本身不弱**：deepseek-v4-pro 是 thinking-capable 强模型，问题是"会思考的模型被关了思考 + 喂了打架的 prompt"。

### 层 2 · must_have 没有代码闭环（acute，安全网缺失）

- strict 模式的"硬约束"其实是软的——只是 prompt 文字。
- `_prune_to_canon`（`character_roster_builder.py:116`）**只做减法**（删白名单外的），
  **没有任何一步保证 `must_have ⊆ roster`**。LLM 漏掉的 must_have 没人补回。
- critic 抓到了 `ip_must_have_missing`，但纯咨询：不重试、不修、草稿照样进 editing 态。

### 层 3 · 研究层生产现实 = grok 单源单次（systemic，厚度根因）

> ⚠️ 关键校正（2026-06-22，用户确认生产现实）：代码里 `_gather_passages_v3` 是 4 源并发
> （grok + 百度剧页 + 百度角色页 + wiki + tavily），但**生产只有 grok 一条腿是活的**——
> 百度 403 / tavily 没 key / wiki 抓不到，这三条在 `asyncio.gather` 里要么抛异常要么返空，
> 纯空转还拖延迟。`MAX_BAIDU_CHARACTERS=8` 这个上限因此是**死的**（百度无数据）。

- 所以甄嬛传的 10 个角色，实际来自：**grok 一次 web_search**（`grok_search.py`，单条大杂烩 query
  "主要角色 演员表 角色介绍 人物关系 剧情"，`max_chars=4000`）+ LLM 训练知识抽取。
- 抽取地板过低（`ip_research_pipeline.py`）：
  - `MIN_PACK_CHARACTERS = 3`（抽到 3 个就算合格放行，离谱）
  - 抽取 prompt 写"characters 至少 8 个，must_have 3~5 个"——大 IP 小 IP 一个地板，不随规模缩放。
  - `MAX_REFETCH_ROUNDS = 2` 自检补抓有限，且自检只查"已有的缺没缺"，不向目标数量推进。

---

## 3. 方案（分层，按 ROI 排序）

### 阶段 A · 规划步骤开思考（层 1 修复，高杠杆/低成本）

**决策（用户授权"生成时思考开关我定"，游戏时保持关）**：
- **规划类**步骤开思考：`build_character_roster`、ip 研究的 `_pre_extract_canon` / `_ground_and_augment` /
  `_self_check_missing`。这些是约束满足/规划任务，CoT 直接提升约束遵守。
- **批量 JSON 生成类**步骤保持关：`build_characters_in_batches`、`build_events_data`、`build_lore_pack`。
  这些是大块结构化输出，截断风险真实，维持 reasoning=False。
- **游戏槽**（game_main/npc_agent/intermission）保持关，不动。

实现路径（二选一，B 更干净）：
- A) 新建一个 `planning` slot（reasoning=None/默认开），让规划步骤用它，而非 admin_generation。
- B) 让 router 支持 per-call reasoning override，规划步骤显式传 `reasoning=True`。
  —— 倾向 B：不增加 slot 绑定负担，改动局部。

**验证（必做）**：本地用官方 DeepSeek 重跑甄嬛传，对比开/关思考下 roster 人数、must_have 命中、
JSON 截断率。确认截断不回归——若回归，规划步骤可单独配更长超时/更大 max_tokens。

### 阶段 B · prompt 去矛盾 + must_have 代码闭环（层 1+2，零风险，必做）

- **重写 roster prompt**：
  - must_have 提到最高优先级、单独成块、措辞强硬（"以下角色必须全部出现，缺一即不合格"）。
  - 删掉/弱化"宁少勿编""宁缺毋滥"对必含约束的污染；数量目标按 IP 规模给（见阶段 C）。
  - 产品取向校正：大 IP 世界**不是"少而精"**，可玩角色给随 roster 规模浮动的真实下限。
- **must_have 强制注入闭环**（安全网，与 prompt 是否生效无关）：
  - roster 产出后加 `_ensure_must_have`：`must_have − roster = 缺失集` → 强制注入（带 role_tag/faction），
    后续 character-detail 阶段补全。和 `_prune_to_canon` 配成"删多余 + 补必含"闭环。
  - critic 报 `ip_must_have_missing` 这类 P0 → 触发一次 roster 重抽/修复；修不掉则草稿不得进入可发布态
    （质量闸要有牙齿）。

### 阶段 C · grok 多角度并行研究 + 放开抽取目标（层 3，这就是"多 Agent research"）

> ROI 论证：生产只有 grok 活，单次单 query 是真瓶颈。把它做成**多角度并行**是唯一活源上的最大杠杆，
> 且不需要新框架——复用现有 `fetch_via_grok_search`，并发跑多条聚焦 query 再 merge 即可。
>
> **定稿（2026-06-22 用户确认）**：grok 对项目方免费、四路并发 wall-time≈一路 → **走满四路 fan-out，不收窄**。
> 唯一增量成本是抽取 LLM（deepseek）×4，便宜短文本且并发，单次生成成本增量很小；用户侧收小额固定生成费覆盖。
> **边界**：全局并发信号量 `llm_global_concurrency=8`，四路在界内 → 四路是上限，不再往上加。

**轴设计：固定结构 + 题材参数化措辞**（"主角/反派"字面轴不通用——推理无明面反派、武侠是门派、群像无单主角、
原创世界无 canon 可搜）。固定 4 类 coverage role 保证 merge 稳定，措辞按 genre/ip_type 填：

| 固定轴 | 作用 | 措辞随题材变 |
|---|---|---|
| 1 核心人物 | 中心视角 | 宫斗=主角妃嫔；推理=侦探+受害者；群像=多主视角 |
| 2 对立/竞争方 | 冲突驱动 | 宫斗=反派妃嫔；武侠=敌对门派；推理=嫌疑人/凶手 |
| 3 外围 & 功能角色 | **最易丢的厚度层** | 太医/太监/宫女/低位嫔妃/随从，明确"穷举次要角色别只给名角" |
| 4 世界设定 | 喂 lore/places/events | 地点/事件/势力/规矩黑话器物 |

前 3 路人物研究（并集→roster），第 4 路设定研究（喂 lore_pack）。题材映射一张小表，不熟题材回退通用措辞。
**原创（非 IP）世界整条 C 跳过**，回退 world_base LLM 生成。

**merge：按轴各自抽取 → 实体级并集去重 → 一轮自检补缺**（不要四路 passage 拼一起塞单次抽取，那会回到
"只吐最有名几个"的老瓶颈）：
```
4 路 grok query 并发 → 每路各自 _pre_extract（聚焦自己那片）→ 4 个 partial pack
  → merge：_norm_name 规范化人名并集去重；同名取信息最全记录；must_have=OR 合并
  → 对 merge 后 pack 跑一轮 self_check 补抓（按"目标数"推进而非只补已知缺口）
  → 质量闸（按 IP 规模，大 IP ≥12）→ 厚 pack
```
合并是实体级（结构化角色对象）非文本级，去重/冲突解决干净可测。

- **grok fan-out（按角色维度并行）**：把一条大杂烩 query 拆成多条聚焦 web_search，`asyncio.gather` 并发：
  - 主角阵营（核心人物谱系/动机/弧光）
  - 反派/对立阵营（势力/手段/关系）
  - 配角 & 工具人 NPC（太医/太监/宫女/低位嫔妃——**正是这次全丢的那批**）
  - 地点 / 事件 / 规矩黑话器物（lore）
  - 各 query 结果 → 候选名并集去重 → 一个厚 pack。
- **按 IP 规模缩放目标**：从 `ip_recognition`（ip_type=tv/movie/novel…）推导目标 named 数
  （长篇电视剧 25-30 / 电影 12-15 / 短篇 8-12），写进抽取 prompt 与质量闸，替掉"至少 8"一刀切。
- **抬质量闸**：`MIN_PACK_CHARACTERS` 按规模抬（大 IP ≥ 12）；must_have 目标按主要角色实际数（甄嬛传 ≥ 6）。
- **退场死源**：百度/wiki/tavily 这三条空转腿退役或 flag 默认关，pipeline 诚实地以 grok 为唯一源
  （省掉每次 gather 的异常等待 + 误导性日志）。

### 阶段 D · 可玩性机制解耦（层 3 配套，结构性）

- 现状：`is_image_target` 一个字段同时管"可玩"和"画头像"（images 阶段同一 flag）→ 可玩被画图额度成本压制。
- 拆成两个维度：`playable_role`（玩法）/ `portrait_target`（成本）。可玩给随 roster 浮动的真实下限，
  头像额度单独控。这样"世界大但可玩少"不再因省图额度误伤。
- 改动面较大（schema + images 阶段 + playable 阶段 + 前端消费），可搭阶段 C 一起，也可单独排。

---

## 4. 落地顺序 & ROI

| 阶段 | 内容 | 成本 | 风险 | ROI | 建议 |
|---|---|---|---|---|---|
| A | 规划步骤开思考 + 实测 | 低 | 中（截断回归，需验证） | 高 | 先做 |
| B | prompt 去矛盾 + must_have 闭环 + critic 闸 | 低 | 零 | 高 | 与 A 同批 |
| C | grok 多角度并行 + 放开目标 + 退死源 | 中 | 低 | 高 | **合并进本轮**（用户已认可 ROI 合适就一起做） |
| D | 可玩/头像解耦 | 中-高 | 低 | 中 | 可搭 C，或下一轮 |

A+B 一批先落（当天可验，立刻把甄嬛传坏草稿重生成）；C 紧接着做（这是真正变厚的主菜）；D 视精力搭 C 或单排。

---

## 5. 验证清单

- [ ] 本地官方 DeepSeek 重跑甄嬛传 strict：roster 含全部 must_have，named ≥ 目标，可玩 ≥ 8。
- [ ] 开思考前后对比：JSON 截断率不回归（重点看 characters/events 批量步骤未受影响）。
- [ ] must_have 闭环单测：故意让 fake LLM 漏掉 must_have，断言 `_ensure_must_have` 补回。
- [ ] critic P0 触发重抽：构造缺主角的 roster，断言走修复而非静默放行。
- [ ] grok fan-out：对比单 query vs 多 query 的候选名总数 / 最终 pack 厚度。
- [ ] 成本核账：多 query grok + 开思考后的单世界生成 token/费用，确认可接受。
- [ ] 把这把坏草稿 `cd54343a` 重生成验证。

---

## 6. 涉及文件（备查）

- `backend/services/character_roster_builder.py` — roster prompt / `_prune_to_canon` / `_ensure_must_have`(新)
- `backend/services/world_creator_agent_v2.py` — `_run_playable` / 阶段编排 / critic 闸
- `backend/services/ip_research_pipeline.py` — `_gather_passages_v3` / 抽取 prompt / 阈值 / 退死源
- `backend/services/ip_pack_extractors/grok_search.py` — grok fan-out（多 query 并发）
- `backend/services/model_management.py` — 规划 slot 思考开关 / `_reasoning_for_slot`
- `backend/llm/router.py` — per-call reasoning override（方案 B）
- `backend/services/world_critic_service.py` — `ip_must_have_missing` → 触发重抽
