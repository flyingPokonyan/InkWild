# IP 复刻引擎 Phase 2：复刻深度 + 底色密度（2026-05-14）

## 范围

Phase 1 已交付：Stage 0 IP 识别 + IP Research 子流水线（Tavily+维基）+ IP Pack 落表 + world_base/character_roster/characters 三个 stage 硬约束 + 中介卡片 UX。逐玉实测：男女主复刻 ✅，但 NPC 复刻度只有 14%（2/14 是原作角色），地点全编，lore_pack 真空，schema 单薄。

**Phase 2 目标**：把"逐玉这种新剧 + 用户输入 4 个字"做到 NPC 复刻度 ≥80%、地点 ≥70% 来自原作、世界纹理饱满（lore/relations/shared_events 不为空）、字段写满率 ≥90%。

**核心设计哲学**：不能只靠 prompt 措辞约束 LLM，要工程化的 4 道防线（structured output / two-step / 分层 prompt / 双轨 critic）+ 6 层协同架构。

**Out of scope**（明确不做）：
- IP 知识库长期存储 / 缓存复用 / 人工预校对
- Embedding 长尾召回（运行时 NPC 提问检索 — 另一条产品线）
- 玩家端运行时改动（Phase 2 只动创建管线）
- 历史已发布 5 个世界批量重生成（雾隐镇等是原创不影响；逐玉单独再做一份样板）
- 国际化（海外 IP 留 Phase 3）

---

## 1. Phase 1 实测复盘（数据驱动设计）

逐玉·风雪缘（draft `2cb896c2`）实测数据：

| 维度 | Phase 1 后 | 期望 | Gap |
|---|---|---|---|
| IP 识别 | ✅ kind=known_ip 0.85 | ✅ | 0 |
| IP Pack characters | 2 个（樊长玉/谢征）| 8-10 个核心 | -75% |
| IP Pack places | 0 个 | 5+ 个 | -100% |
| IP Pack factions | 0 个 | 3+ 个 | -100% |
| 最终 NPCs | 14 个 / 2 原作 = 14% | ≥80% 原作命中 | -66pp |
| Locations 来自原作 | 0/7 = 0% | ≥70% | -70pp |
| NPC schema 字段数 | 5 字段 | 9 字段 | -4 |
| Location schema 字段数 | 2 字段 | 8 字段 | -6 |
| lore_pack.dimensions | 0（真 bug） | 5+ | -100% |
| shared_events | 0 | 5+ | -100% |
| relations_pack | null | 持久化 | 缺失 |

**根因再总结**：
1. Tavily + 维基对中文新剧覆盖弱（Phase 1 未引入 Grok / 百度）
2. lore_pack stage 跑过子任务但 final.dimensions=[] 落地丢（pipeline 序列化 bug）
3. NPC/Location schema 设计偏简，prompt 也没要求写满
4. 下游 lore_dimensions / shared_events / events_data 没接 IP Pack（Phase 1 只接 world_base/character_roster/characters 三个）
5. critic 只查"达到发布线"泛泛，无 IP 命中硬卡口
6. LLM 即使被 strict prompt 约束仍可能"挑着用"——纯 prompt 约束力不够

---

## 2. 总体架构（6 层）

```
┌────────────────────────────────────────────────────────────────────┐
│ 层 6：SSE 进度反馈完善（横切）                                       │
│ - 新增子事件覆盖 Grok 搜索 / 百度抓取 / two-step / critic 回炉      │
│ - 前端 GenerationLoadingScreen 子事件折叠区                          │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────┐
│ 层 5：质量控制（横切贯穿所有 stage）                                 │
│ - 防线 1：JSON schema enum（structured output）                      │
│ - 防线 2：two-step 生成（先选 names → 再写 details）                 │
│ - 防线 3：分层 prompt（HARD CONSTRAINT / STYLE / FIELD INSTRUCTION）│
│ - 防线 4：双轨 critic（IP 命中 + 字段质量）                          │
└────────────────────────────────────────────────────────────────────┘
              ↑                                          ↑
┌─────────────┴────────────┐                ┌─────────────┴───────────┐
│ 层 4：Schema 扩展         │                │ 层 3：世界纹理修复       │
│ - location: 2 → 8 字段    │ ←── 用 lore  │ - 修 lore_pack.dim=0 bug │
│ - NPC: 5 → 9 字段         │     维度做    │ - lore_pack 接 IP Pack   │
│ - golden examples 防生硬  │     grounding│ - shared_events / relations│
│                           │                │   pack 持久化            │
└─────────────┬────────────┘                └─────────────┬───────────┘
              ↑                                            ↑
              └─────────── 用 IP Pack ─────┬───────────────┘
                          作硬约束源        │
                                            ▼
                            ┌────────────────────────────────────┐
                            │ 层 2：IP 知识层（Phase 2 核心）     │
                            │ - Grok web_search 主搜索源          │
                            │ - 百度百科直抓 RAG 补强             │
                            │ - 完整性自检 4 维度                 │
                            │ - IP Pack 落表（Phase 1 已有）      │
                            └─────────────────┬──────────────────┘
                                              ↑
                            ┌─────────────────┴──────────────────┐
                            │ 层 1：Phase 1 已交付                │
                            │ Stage 0 IP 识别 + 流水线两阶段     │
                            └────────────────────────────────────┘
```

---

## 3. 层 5：4 道防线（横切贯穿，最先讲）

### 防线 1：物理约束（structured output）

**问题**：prompt 说"必须用樊长玉"，LLM 仍可能写"长玉"或"樊女"或"那位屠户女"。

**方案**：用 JSON schema enum 让 LLM 物理上无法编。

```json
{
  "type": "object",
  "properties": {
    "characters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "enum": ["樊长玉", "谢征", "李怀安", "贺敬元", ...]
          },
          ...
        },
        "required": ["name"]
      }
    }
  }
}
```

实现路径：
- 复用 `LLMRouter.stream_with_tools` 已有的 tool calling 能力（每个 provider 已实装）
- 把 stage 输出从"自由文本 + JSON 提取"改成"tool with strict schema"
- enum 来源：当 fidelity_mode=strict，从 `IPKnowledgePack.must_have_character_names() + character names with must_have=False` 拼出全 names；strict 时 enum 强制，loose 时仅 `examples` 引导

**适用 stage**：character_roster (names 选择) / characters (per-character schema 填充) / world_base (location names)

**provider 兼容**：Claude / OpenAI 兼容 / Gemini 都支持 enum；Grok 通过 tool calling 也支持；DeepSeek 是 OpenAI 兼容也 OK。Phase 1 现有 LLMRouter 抽象层不需要改。

### 防线 2：分步生成（two-step）

**问题**：character_roster 现在让 LLM 一次输出 14 个角色 + 每个 5-9 字段 = 4000+ token 输出，容易截断（Phase 1 已踩坑：max_tokens=2048 截断 bug，临时改 4096，治标不治本）。

**方案**：拆 2 步：

**Step A：选 names**（< 200 token 输出）  
LLM 输入：world_base / IP Pack / lore_pack 上下文  
LLM 输出：`{"names": ["樊长玉","谢征","李怀安",...], "rationale": "..."}` （受 enum 约束）

**Step B：per-character 详细字段**（每个 < 800 token 输出）  
对 Step A 输出的每个 name 跑独立 LLM call，concurrent 4 路：
- 输入：name + IP Pack 该角色条目 + lore_pack culture + role context
- 输出：完整 IPCharacter 字段（personality / secret / knowledge / schedule / relations / voice / values / appearance / mannerisms）

优点：
- 单 call 输出小 → 永不截断
- 单 character 失败不拖累整批
- 并发跑（4 路）→ 总时长可能不增反减
- 每个 character 单独可 critic / retry

缺点：
- LLM 调用次数从 1 涨到 1+N（N=8-15）
- system prompt 重复 → 用 prompt caching（Anthropic / OpenAI 都支持）抵消

**适用 stage**：characters（最大收益）  
**不适用**：world_base（LLM 一次出框架更连贯）/ events_data（已经是 sub-task 并发了）

### 防线 3：分层 prompt（核心约束顶在前）

**问题**：现有 prompt 把"必须用 X"和"建议风格 Y"和"字段填充指引 Z"混在一起，LLM attention 分散。

**方案**：模板化分 3 层：

```
==== CRITICAL HARD CONSTRAINTS (MUST follow, no exceptions) ====
{若 fidelity_mode=strict 且 ip_pack 非空}
- characters[].name MUST be one of: <enum values>
- locations[].name MUST be one of: <enum values>
- 缺漏 must_have 必触发回炉

==== WORLD CONTEXT (background) ====
- 原作摘要: {ip_pack.summary[:1500]}
- 文化背景: {lore_pack.dim_culture}
- 政治格局: {lore_pack.dim_politics}

==== STYLE GUIDANCE (借鉴，可发挥) ====
- 原作风格词: {ip_pack.tone_lingo}
- 关键意象: {ip_pack.iconic_objects}

==== FIELD INSTRUCTIONS (字段写满指引) ====
{每个字段单独 instruction，附 1 例好/坏}
voice: 一句典型台词，要带个人语气词
  好例: "诶哟我说，你这小子..."
  坏例: "他/她说话很有礼貌"

==== TASK ====
请输出 JSON...
```

LLM attention 偏前段，硬约束顶在最前——比当前 flat list 风格强约束力更高。

### 防线 4：双轨 critic

**当前**：critic stage 只跑一次"达到发布线"的 LLM 泛检查（已有但弱）。

**升级为两条并行 check**：

#### 4a. IP 命中 critic（机器规则，零 LLM 成本）

```python
must_have_chars = ip_pack.must_have_character_names()
generated_chars = [c.name for c in result.characters]
hit = sum(1 for n in must_have_chars if n in generated_chars) / max(1, len(must_have_chars))

if fidelity_mode == "strict":
  if hit < 0.9: → retry character_roster + characters
elif fidelity_mode == "loose":
  if hit < 0.6: → retry character_roster

# 同理 locations / factions
```

回炉最多 1 次（防无限循环），第 2 次仍未达标则记 warning publish。

#### 4b. 字段质量 critic（LLM 检查，单次 ~$0.01）

针对每个 character / location 字段跑 1 次 LLM call：
- 字段写满率（非空 / 非 placeholder） ≥ 80% pass
- 通用模板词检测：voice 含"礼貌"/"友善"/appearance 含"美若天仙"/"清秀脱俗"等通用词 → warning
- 不回炉，只标记 warning，admin 决定是否手动改

记录到 `world_drafts.payload.quality_warnings`，admin UI 显示。

---

## 4. 层 2：IP 知识层升级（Phase 2 核心，最高 ROI）

### 4.1 Grok web_search 作主搜索源

**实测验证**（2026-05-14 用 grok-4.20-0309-reasoning 跑 query "电视剧《逐玉》主要角色 演员表 田曦薇 张凌赫 任豪 角色介绍 关系"）：
- 单次返回 2293 字结构化中文清单
- 9 个有名有姓角色 + 演员 + 字号 + 角色定位（主/男二/反派）
- 完整关系拓扑（包括魏严舅甥仇怨、单恋三角）
- 4 个 citations（wiki + baike + tvmao + hk01 cross-check）
- 重要细节：樊长玉真名魏长玉、字山君、原型秦良玉式女将军，妹妹叫樊长宁

**实现**：
- 新增 `services/ip_pack_extractors/grok_search.py`
- 包 `GrokProvider.web_search(query, max_tokens=2048)`，输出转 `list[Passage]`
- query 模板：`"电视剧/小说《{ip_name}》 主要角色 演员表 主演 关系 介绍 剧情"`（5-7 个关键词增强 search 召回）
- 把 Grok summary 作 1 条大 Passage（source="grok_search"），Grok citations 作 metadata tags
- 失败兜底：若 Grok API 不可用或 web_search disabled → fallback 用 wiki+tavily（Phase 1 路径）

### 4.2 百度百科直抓 RAG 补强

**实测验证**：
- baike `/item/逐玉`：802KB, 樊长玉 308 次 / 谢征 356 / 李怀安 58 / 贺敬元 22
- baike `/item/谢征/(角色页)`：126KB, 武安侯 8 次 / 《逐玉》19 次
- 各角色页直接 `/item/<name>` 都通（百度自动消歧）
- 实测一次成功，无反爬

**实现**：
- 新增 `services/ip_pack_extractors/baidu_baike.py`
- 函数 1：`fetch_baike_show(ip_name) -> list[Passage]` 抓剧主页，提取演员表段落 + 角色介绍段落
- 函数 2：`fetch_baike_character(name) -> Passage | None` 抓角色页（用 `/item/<urlencoded_name>` 直拉），返回单 Passage
- 反爬策略：UA + 8s timeout + 失败兜底（warning + 空结果）
- 限速：单局抓取 ≤ 10 个角色页，每页间 sleep 0.3s（避免触发限制）

### 4.3 IP Research Pipeline 流程升级

```
Step 0 (Phase 1 已有): Stage 0 IP 识别
   ↓ 输出 IPRecognition (kind, confidence, ip_name, ip_type)

Step 1 (新): Grok 主搜索
   ↓ 输出 grok_summary (high-quality structured Chinese)
   ↓ 输出 candidate_names (从 Grok summary 解析出角色清单)

Step 2 (改): 多源并发深度抓取
   - 主路：百度百科剧主页 + 候选角色页（top 8 by Grok 排序）
   - 辅路：维基百科（Phase 1 已有，保留作 fallback）
   - 辅路：Tavily site:douban.com 等（Phase 1 已有）
   ↓ 输出 list[Passage]（30 条上限）

Step 3 (改): RAG 抽取 IPKnowledgePack
   - context = grok_summary（核心）+ baike passages（细节）
   - prompt 升级：要求 characters ≥ 8 / places ≥ 5 / factions ≥ 3 / events ≥ 5
   - structured output (防线 1) 强制结构

Step 4 (升级): 完整性自检 4 维度
   - 检查 characters / places / factions / key_events 是否各自 ≥ 阈值
   - 缺哪一类 → 单独 query 补抓（如 "电视剧《X》主要地点 城市 战场"）
   - 至多 2 轮补抓（升级自 1 轮）
   ↓ 最终 IPKnowledgePack 落表
```

### 4.4 IPKnowledgePack schema 微调

新增可选字段（向后兼容，不破坏 Phase 1 数据）：
- `IPCharacter.voice_style: str | None`（一句典型台词或语气描述，从 Grok summary 提取）
- `IPCharacter.story_arc: str | None`（在原作的成长弧线，简短）
- `IPPlace.faction_owner: str | None`（属于哪个势力 — 跨字段引用）
- `IPKnowledgePack.timeline: list[dict]`（关键事件时间线，含相对时间锚 "17 年前 / 序幕 / 中段 / 结局"）

这些字段下游层 4 NPC schema 扩展时会用作 grounding。

---

## 5. 层 3：世界纹理层（lore_pack 修 bug + IP-aware）

### 5.1 修 lore_pack.dimensions=0 真空 bug

**症状**：`generation_task_events` 里能看到 `lore_pack stage subtask_completed × 4 (dim:power_structure / cultivation_system / historical_background / geography)`，但 `intermediate_state.lore_pack.dimensions = []`。

**根因猜测**（待 Phase 2 implementer 实地查）：
- `services/lore_pack_builder.py:build_lore_pack` 可能在 dimensions 子任务异常时静默丢弃，最终 LorePack(dimensions=[]) 落地
- 或者 v2 agent 的 `_run_lore_pack` 错把空 list 当成 result

修复：
- 实测时打开 debug log 看每个子任务返回值
- 不论哪一层丢，加 assertion 让丢失早早 fail loudly
- 必要时把 dimensions 子任务结果写入 intermediate_state（每个 dim 落一个 key），final aggregation 再读

### 5.2 lore_pack 接 IP Pack

`services/lore_pack_builder.py:build_lore_pack` 修改：
- 新增参数 `ip_pack: IPKnowledgePack | None`
- 每个 dimension 的 LLM prompt 注入对应 IP Pack 字段：
  - dim:politics → ip_pack.factions（必须从这些势力选用，不可编"大晟王朝"）
  - dim:culture → ip_pack.tone_lingo + ip_pack.summary 文化部分
  - dim:geography → ip_pack.places（必须包含，可扩展）
  - dim:historical → ip_pack.timeline + ip_pack.key_events
- 应用防线 3 分层 prompt 模板

### 5.3 shared_events / relations_pack 持久化

**当前**：shared_events 生成出来但落 0；relations_pack=null 完全没有。

**修复**：
- `services/shared_events_builder.py`：检查为何 0 —— 可能是 LLM 输出格式不对没解析到。改 prompt + 加 structured output
- `_run_relations_pack` (`world_creator_agent_v2.py:_run_relations_pack`)：检查为何不持久化到 intermediate_state
- 同时让这两个 stage 都接 IP Pack（用 ip_pack.characters relations_to_protagonist 作 grounding）

### 5.4 events_data 接 IP Pack

events_data 已经是亮点（8 个事件 + 详细 trigger/rumor/effect），但事件**主题来源**还可以更 IP-aware：
- 新增 prompt 块：`重点考虑围绕原作 key_events ({ip_pack.key_events}) 设计 conditional 事件`
- 例如逐玉应该有"event:十七年前血案揭示"、"event:战场重逢"这种与原作主线呼应的 conditional event

---

## 6. 层 4：Schema 扩展（NPC + Location 底色饱满）

### 6.1 Location schema 从 2 → 8 字段

#### 现状
```python
# 在 worlds.locations_data JSON 数组里，每个元素：
{"name": str, "description": str}
```

#### 升级
```python
# schemas/world.py 新增 Pydantic LocationDetail（向后兼容：旧字段保留，新字段都 optional）
class LocationDetail(BaseModel):
    name: str
    description: str  # 仍是 50-100 字总览
    atmosphere_day: str | None      # 白天氛围 30-60 字
    atmosphere_night: str | None    # 夜晚氛围 30-60 字
    sensory: list[str] = []         # 3-5 条感官细节（声 / 香 / 光 / 触）
    interactions: list[str] = []    # 3-6 条玩家可做的事 ("买肉" / "打听消息" / "暗中观察")
    items: list[dict] = []          # 可拾取/可见物 [{name, description, hidden: bool}]
    npcs_present: list[str] = []    # 该地点常驻 NPC names（从 schedule 反向索引自动算出）
    notes: str | None               # 隐藏内容、密道、特殊机制（admin 可读）
```

数据库层：`worlds.locations_data` 当前 JSON 字段已可承载，**不需要 schema migration**。但 Pydantic schema 升级 + builder 改造。

#### Builder 改造
- `services/lore_pack_builder.py` 或新建 `services/locations_detail_builder.py`：负责为 world_base 输出的每个 location 跑 1 次 LLM call 写满 8 字段
- 应用防线 1（structured output 用 LocationDetail schema）+ 防线 3（分层 prompt + golden examples）
- 并发 4 路（一次跑 4 个 location）
- 时间影响：单 location ~3s × 7 location / 4 路 = ~6s，可接受

### 6.2 NPC schema 从 5 → 9 字段

#### 现状
```python
# npcs 表：
class NPC:
    name: str
    personality: str
    secret: str | None
    knowledge: list[dict]
    schedule: dict  # {morning/afternoon/evening/night: location}
    initial_location: str
    # 还有 abilities/starting_inventory（在 characters 表）/ initial_peer_relations
```

#### 升级（新增 4 字段）
```python
class NPCDetail:
    # ... 现有字段
    voice_style: str         # 一句典型台词，含语气词（new）
    values: list[str]        # 2-3 条核心价值观/信念锚点（new）
    appearance: str          # 50-80 字身体细节，含 1-2 个让人记得住的点（new）
    mannerisms: list[str]    # 2-4 条习惯动作/口癖 ("紧张时摸刀柄" / "皱眉前先抿嘴")（new）
```

数据库层：`npcs` 表加 4 个 nullable 列 + Alembic migration。

#### Builder 改造
- `services/world_creator_agent_v2.py:_run_characters` 和 `services/character_roster_builder.py:_build_batch_prompt` 都改
- two-step 模式（防线 2）：Step A 用现有 build_character_roster 选 names → Step B per-character 跑 1 次 LLM call 写完整 9 字段
- voice_style / appearance / mannerisms 的 prompt 块用防线 3 golden examples（好例 / 坏例对比）
- 用 IP Pack 该角色的 voice_style + lore_pack culture 作 grounding（樊长玉的 voice 应该带北境屠户语气，不能写成京城贵女腔）

### 6.3 Golden examples 库

新建 `backend/services/prompt_examples.py`，集中放各字段的 golden examples：

```python
VOICE_EXAMPLES = {
    "good": [
        "诶哟我说，你这病秧子还想跟我抢饭碗？",      # 北境市井
        "侯爷..此事还需从长计议。",                   # 朝堂大臣
    ],
    "bad": [
        "他说话很有礼貌",                             # 描述而非台词
        "你好",                                       # 通用
    ]
}

APPEARANCE_EXAMPLES = {
    "good": [
        "左手虎口有杀猪割的旧疤，常年系着深蓝粗布围裙，眉毛粗黑，笑起来左颊有道刀疤。",
        "白皙得过分，太阳穴有处淡青色印记，习惯把袖子拢在手心。",
    ],
    "bad": [
        "貌美如花，气质出众",
        "身材高大，相貌堂堂",
    ]
}
# 同理 ATMOSPHERE_EXAMPLES, INTERACTION_EXAMPLES, ...
```

每个 builder 在拼 prompt 时按字段类型注入对应 golden examples（2 好 + 2 坏），LLM 看了对比知道写什么算"好"。

---

## 7. 层 6：SSE 进度反馈完善

### 新增子事件

`frontend/lib/admin-sse-events.ts` 扩展 ProgressEventData，覆盖 Phase 2 新阶段：

| phase | code | meta 关键字段 | 触发时 |
|---|---|---|---|
| ip_research | source_started | source: "grok"/"baidu"/"wiki"/"tavily_site" | 开始单源抓取 |
| ip_research | source_completed | source, passages_count | 单源结束 |
| ip_research | extract_started | passages_total | 开始 RAG 抽取 |
| ip_research | extract_completed | characters/places/factions/events 各 count | 抽取完成 |
| ip_research | self_check_started | dimension_count | 自检开始 |
| ip_research | self_check_completed | missing_count, will_refetch: bool | 自检结束 |
| ip_research | refetch_round | round, targets: [...] | 触发补抓时 |
| characters | step_a_started | - | two-step 第 1 步 |
| characters | step_a_completed | name_count, names: [...] | 第 1 步完成 |
| characters | step_b_subtask_started | name | 单 character 详细生成开始 |
| characters | step_b_subtask_completed | name, fields_filled: int, fields_total: int | 单 character 完成 |
| critic | ip_match_check | must_have_hit_rate, decision: "pass"/"retry" | IP 命中 critic |
| critic | field_quality_check | warnings_count, decision: "pass"/"warn" | 字段质量 critic |
| critic | retry_triggered | retry_stage: str, reason: str | 触发回炉 |

### 前端展示

`frontend/components/admin/GenerationLoadingScreen.tsx` 改造：
- 当前 stage 自动展开 sub-events 折叠区，其他 stage 折叠
- sub-event 展示成 timeline list（缩进列在 stage 下）
- critic retry 高亮（黄色 / 红色）+ 显示原因
- 抓取源单独一栏显示 "Grok ✅ 1.2s | 百度 ✅ 4.8s | 维基 ⚠️ 8s 超时 | Tavily ✅ 2.1s"

文案规范：
- "正在调用 Grok 搜索原作演员表..."
- "Grok 返回 9 个候选角色，开始百度百科深抓..."
- "正在抓取百度百科：李怀安 (3/8)..."
- "IP 一致性命中率 100%（5/5），进入字段质量检查..."
- "字段质量检查发现 2 处通用模板词，已标记 warning（可在 admin 修改）"

### Admin Pack 查看页

新增 `frontend/app/admin/ip-packs/[id]/page.tsx`：
- 只读展示某个 IP Pack 的完整 JSON（characters / places / factions / events / passages）
- 提供"复制为 prompt 上下文"按钮（用于调试）
- 半小时工作量，调 bug 用

---

## 8. 数据流总图

```
用户输入 "影视剧 逐玉"
    ↓
[Stage 0] IP 识别 → IPRecognition(kind=known_ip, ip_name=逐玉)
    ↓ user 选 strict
[Stage A] IP Research:
    ├─ Grok web_search → 2293 字结构化清单 + 4 citations
    ├─ 解析候选角色 names: [樊长玉, 谢征, 李怀安, 俞浅浅, 齐旻, 魏严, 公孙鄞, 齐姝, ...]
    ├─ 并发抓取:
    │   ├─ 百度百科剧主页 (1 page)
    │   ├─ 百度百科角色页 (top 8 by Grok importance)
    │   ├─ 维基百科剧页 (fallback)
    │   └─ Tavily site:douban.com (fallback)
    ├─ RAG 抽取 IPKnowledgePack (structured output)
    │   - characters ≥ 8 个 with must_have flag
    │   - places ≥ 5 个 (含 临安镇 / 北境 / 京城 / 霁州)
    │   - factions ≥ 3 个 (武安侯府 / 魏家 / 长信王)
    │   - key_events ≥ 5 个
    │   - voice_style / story_arc / faction_owner / timeline 等扩展字段
    └─ 完整性自检 → 必要时补抓
    ↓
[Stage 1] world_base
    - 防线 3 分层 prompt
    - location names from IP Pack places (enum)
    - 输出世界框架 + 7-10 个 location names
    ↓
[Stage 2] lore_dimensions + character_roster (并发)
    ↓
[Stage 3] lore_pack
    - 修 dimensions=0 bug
    - 5 个维度都接 IP Pack
    - 输出 culture / politics / geography / historical / cultivation 详细 lore
    ↓
[Stage 4 NEW] location_details
    - 对每个 location 跑 1 次 LLM call 写满 8 字段
    - 用 lore_pack culture/atmosphere 作 grounding
    - 并发 4 路
    ↓
[Stage 5] characters (two-step + per-NPC enrichment)
    - Step A: 选 names from IP Pack must_have (enum 强约束)
    - Step B: per-character 写满 9 字段（含 voice/values/appearance/mannerisms）
    - 用 ip_pack 该角色 + lore_pack culture 作 grounding
    - 并发 4 路
    ↓
[Stage 6] shared_events / relations_pack / events_data (修持久化 + 接 IP Pack)
    ↓
[Stage 7] critic
    - 双轨：IP 命中（机器规则）+ 字段质量（LLM）
    - 命中率 < 阈值触发回炉（最多 1 次）
    ↓
[Stage 8] images / validating
    ↓
draft 完成 → admin publish → worlds 表
```

---

## 9. 验收标准

### 量化目标（拿逐玉做基准）

| 指标 | Phase 1 后 | Phase 2 目标 | 验收方式 |
|---|---|---|---|
| IP Pack characters 数 | 2 | ≥ 8 | DB 查询 |
| IP Pack places 数 | 0 | ≥ 5 | DB 查询 |
| IP Pack factions 数 | 0 | ≥ 3 | DB 查询 |
| 最终 NPCs 中原作命中率 | 14% (2/14) | ≥ 80% | 跑测试集脚本 |
| 最终 locations 中原作命中率 | 0% (0/7) | ≥ 70% | 跑测试集脚本 |
| NPC schema 字段写满率 | 5/5 = 100%（旧字段）| ≥ 90% (9 字段) | 字段非空非 placeholder |
| Location schema 字段写满率 | 2/2 = 100%（旧字段）| ≥ 85% (8 字段) | 字段非空 |
| lore_pack.dimensions 数 | 0 | ≥ 5 | DB 查询 |
| shared_events 数 | 0 | ≥ 5 | DB 查询 |
| relations_pack 边数 | null | ≥ 15 | DB 查询 |
| critic 字段质量 warning 数 | 不查 | < 5 / 单局 | critic stage meta |
| 单局生成时长 | ~90s | ≤ 240s | SSE timing |
| 单局 LLM 成本 | ~$0.05 | ≤ $0.30 | token_usage 表 |

### 质量目标（人工评审）

样本：用 5 个 IP 跑（逐玉 / 红楼梦 / 沙丘 / 诡秘之主 / 雾隐镇原创）

> 注：这是 Phase 2 一次性人工验收，跟 Phase 1 spec 第 8 节规划的"Phase 3 自动化金标准测试集"是两件事——后者是 CI 周跑、自动算命中率、跨 PR 回归用。Phase 2 这次手动跑 5 IP 是为了交付前 sanity check；Phase 3 时再把它做成 pytest+脚本化的回归套件。

5 项 admin 主观评分（1-5 分）：
- IP 复刻度：原作核心人物 / 地名 / 标志元素
- NPC 立体度：性格 / voice / 关系 是否避免模板化
- 地点真实度：能否想象成可探索空间
- 世界纹理：lore / 历史 / 文化是否有"活气"
- 整体可玩性：作为剧本 / 自由模式起点是否扎实

合格线：5 个 IP 平均每项 ≥ 4 分。

---

## 10. 实施 Phase 拆分

### Phase 2.0：基础设施（1 天）
- 修 lore_pack.dimensions=0 bug（独立可单测）
- shared_events / relations_pack 持久化修复
- 跑一次逐玉验证 lore/relations 不再是空

### Phase 2.1：IP 知识层（核心，2-3 天）
- Grok extractor + 集成
- 百度百科 extractor + 集成
- IP Research pipeline 升级（4 步流程）
- 完整性自检 4 维度
- IPKnowledgePack schema 扩展

### Phase 2.2：质量控制基础（1-2 天）
- 防线 1：structured output 框架（LLMRouter 抽象）
- 防线 3：分层 prompt 模板 + Golden examples 库
- 应用到 character_roster + characters

### Phase 2.3：Schema 扩展（2 天）
- LocationDetail schema + builder + migration
- NPC 9 字段 + Alembic migration
- two-step 生成（防线 2）应用到 characters
- 各 builder 接 lore_pack/IP Pack 作 grounding

### Phase 2.4：World 纹理升级（1.5 天）
- lore_pack 接 IP Pack（5 个维度）
- events_data 接 IP Pack（key_events grounding）

### Phase 2.5：Critic 升级（1 天）
- 防线 4a：IP 命中机器规则 critic
- 防线 4b：字段质量 LLM critic
- retry 流程 + warning 持久化

### Phase 2.6：SSE + 前端（1 天）
- 新增 sub-events
- GenerationLoadingScreen 子事件折叠区
- Admin Pack 查看页

### Phase 2.7：验收 + 样板（1 天）
- 跑 5 个 IP 测试集
- 写新 baseline 对比文档
- 5 项主观评分

合计 9-11 天。Phase 2.0 + 2.1 是 P0（IP 复刻直接相关）；2.2-2.5 是 P1（质量保证）；2.6-2.7 收口。

---

## 11. 风险与决策记录

### 风险

1. **Grok web_search reasoning model 成本** — 实测单次 ~$0.05，单局加 1 次。可接受。
2. **百度反爬** — 实测一次成功，但长期可能升级反爬。Mitigation：fallback 到 Tavily site 搜索 + 限速。
3. **structured output 跨 provider 兼容** — Claude/OpenAI/Gemini/Grok 都支持，DeepSeek 是 OpenAI 兼容。但实测时可能踩 schema 复杂度上限。Phase 2.2 实施时先验证。
4. **two-step 生成 LLM 调用次数翻倍** — prompt caching 抵消（Anthropic 缓存命中 90% 时只算 10% input cost）。
5. **lore_pack=0 bug 根因待定** — Phase 2.0 第一件事就是诊断；如果根因复杂可能延期。
6. **schema 扩展破坏向后兼容** — 严格 nullable + Pydantic v2 default 处理，不破坏 Phase 1 数据。Phase 2.3 加 migration 测试。

### 决策

- **Grok 主搜索 + 百度补强 + wiki/tavily 兜底** — 实测对比后选定，4 源协同
- **两步生成只用于 characters stage** — 其他 stage 一次输出更连贯
- **lore_pack 修 bug 单独 phase 先做** — 30 分钟 -> 几小时，独立可验证
- **critic 回炉最多 1 次** — 第 2 次仍未达标 publish + warning，不死循环
- **Admin Pack 查看页做** — 半小时工作量，调 bug 必备
- **schema 字段都 nullable** — 新字段不破坏旧数据，渐进式加深

### 不做的

- 不引入 IP 知识库长期缓存（YAGNI，等用户重复创建同 IP 再做）
- 不做 embedding 召回（运行时 feature，跨产品线）
- 不做国际化抓取源（海外 IP 留 Phase 3）
- 不重新生成已发布世界（只逐玉做样板）
- 不做 events_data prompt 大改（已经够好）

---

## 附录 A：现状代码定位

- Phase 1 IPRecognition: `services/ip_recognizer.py`
- Phase 1 IPKnowledgePack schema: `schemas/ip_knowledge_pack.py`
- Phase 1 IP Research pipeline: `services/ip_research_pipeline.py`
- Phase 1 IP Pack 落表: `services/ip_pack_storage.py`
- Phase 1 wikipedia / tavily extractors: `services/ip_pack_extractors/`
- Phase 1 character_roster builder: `services/character_roster_builder.py`
- Phase 1 world_creator_agent: `services/world_creator_agent_v2.py`
- Grok provider with web_search: `backend/llm/grok.py`（已实装）
- LLMRouter: `services/model_management.py` + `llm/router.py`
- Critic: `services/world_critic_service.py`
- lore_pack builder: `services/lore_pack_builder.py`（待修 bug）
- shared_events builder: `services/shared_events_builder.py`（待修持久化）
- relations_pack builder: `services/relations_pack_builder.py`（待修持久化）
- npcs / characters / events / world_characters 表: `backend/models/`
- SSE 事件 schema: `frontend/lib/admin-sse-events.ts`
- 创作工坊 loading screen: `frontend/components/admin/GenerationLoadingScreen.tsx`

## 附录 B：参考调试样本

- Phase 1 逐玉 baseline: `docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md`
- Phase 1 spec: `docs/superpowers/specs/2026-05-14-ip-fidelity-engine-design.md`
- Phase 1 plan: `docs/superpowers/plans/2026-05-14-ip-fidelity-engine-phase1.md`
- 实测 Grok web_search 输出（2026-05-14 跑出，留 docs/_archive/ 待归档）
- draft `2cb896c2-8ece-4fc5-abdc-a3245d3eb266` 是 Phase 1 最后一次成功生成，作 Phase 2 对比基准
