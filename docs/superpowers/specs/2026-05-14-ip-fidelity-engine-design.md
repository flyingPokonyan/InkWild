# IP 复刻引擎（2026-05-14）

## 范围

把"高复刻真实 IP / 影视 / 小说作品"从一个失效的兜底机制，升级成创作工坊的核心能力。

**目标定档（B+）**：
- 关键人物全员到位（含原作里所有有名有姓的二级人物）
- 世界观、地名、势力、关键事件背景忠于原作
- 剧情走向不强约束 —— 玩家想还原原作能还原、想分支也能分支
- 设计哲学："底色对了，运行时演绎自然真实"

**Out of scope**：
- IP 知识库 / 同 IP 缓存复用 / 热门 IP 人工预校对 / Embedding 长尾召回 / 原作版本化 —— 等业务真出现重复创建同 IP 的信号再做
- 运行时 IP 检索（玩游戏时玩家问原作冷僻细节）—— 是另一条产品线
- 已发布 world 批量重生成 —— 不做。雾隐镇等 4 个是原创、不受影响；只对逐玉单独重生成做样板（见验收标准 #6）

---

## 1. 根因回顾（why this design）

证据链已确认（详见 `intermediate_state.research_pack` 数据库样本）：

| 阶段 | 现状 | 问题 |
|---|---|---|
| Tavily 检索 | ✅ 4 条 passages 含 wiki/爱奇艺/iyf，summary 完整 | 没问题 |
| `probe_ip_canon` (`services/research_pack_builder.py:114`) | 让 LLM 凭"自身训练记忆"回忆 IP | 《逐玉》2026-03 上线，LLM cutoff 早于此 → ip_canon 6 个字段全空 |
| 下游 14 个 stage | 全部读 `ip_canon` 做约束；`lore_dimensions` 完全不读 passages | ip_canon 空 → LLM 看到"标志性人名：（无）"被强暗示"无原作约束" → 自由发挥 → 雪落镇/大晟/北狄 |
| critic | 只做泛泛检查 | 没有 IP 一致性硬卡口 |

**根因一句话**：IP 知识来源选错了——靠 LLM 记忆而非联网证据；下游 prompt 是"参考"而非"必须使用"。

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│ 前端 admin 创作工坊                                              │
│  单 textarea（保持现状低摩擦）→ [开始生成]                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0  IP Recognition（新增，2-3s）                            │
│  1 次 LLM call + 轻量 Tavily 探测 → 输出:                        │
│    { kind: known_ip | hybrid | original, confidence, ip_name,    │
│      one_liner }                                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
       ┌─────────────┼─────────────┬────────────────┐
       ▼             ▼             ▼                ▼
   confidence    confidence    confidence       明确原创
   ≥ 0.85        0.5 ~ 0.85    < 0.5
       │             │             │                │
       │             │             │                │
       ▼             ▼             ▼                ▼
  中介卡片        中介卡片       静默               静默
  「识别到《X》」 「跟《X》相近」 通过              通过
   ① 高复刻       ① 是          (走原创)         (走原创)
   ② 借鉴         ② 否
   ③ 这不是
       │             │
       │ ①           │ ①
       ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage A+  IP Research Pipeline（路线 2 主体，10~20s）            │
│  ① IP 元数据识别（类型/来源平台）                                │
│  ② 多源并发抓取：Tavily + 维基 + 百度百科直抓 + 豆瓣 +（网文→晋江）│
│  ③ RAG 结构化抽取 → IP Knowledge Pack                           │
│  ④ 完整性自检 → 补抓 → 二轮抽取                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
              落表：ip_knowledge_packs
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 下游 14 stage：IP Knowledge Pack 硬约束                          │
│  prompt 改为「必须从清单中选用 / 不得自造同类」                  │
│  lore_dimensions 也接收 pack                                     │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ critic 增强：IP 一致性硬卡口                                     │
│  must_have_characters 命中率 < 90% → 打回 characters             │
│  canonical_places 出现率 < 80% → 打回 world_base                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage 0：IP 识别 + 用户分流

### 3.1 后端：新增 `services/ip_recognizer.py`

输入：用户原始 description 文本（可任意自由文本）  
输出：

```python
class IPRecognition(BaseModel):
    kind: Literal["known_ip", "hybrid", "original"]
    confidence: float  # 0~1
    ip_name: str | None       # 识别出的 IP 名，known/hybrid 时填
    ip_type: Literal["tv", "movie", "novel", "anime", "game", "other"] | None
    one_liner: str | None     # 一句话简介，弹卡片用
    source_hints: list[str]   # 推荐抓取的 url 候选（百度百科/维基）
```

实现：
1. 1 次 LLM call，prompt 让模型判断"这段描述是否指向某个已知 IP"。给出 known/hybrid/original 三态 + 置信度
2. 如果 kind=known_ip 且 confidence 高，再用 Tavily 跑 1 次 quick verify（看搜索结果第 1 条标题是否包含 ip_name）—— 把"LLM 凭记忆"的置信度跟"互联网真有这个 IP"二次确认
3. **关键**：prompt 明确告知"如果你不确定这个 IP 是否存在（如训练 cutoff 之后），但描述里出现作品名，则置 confidence=0.7、由 Tavily verify 提升或降回"—— 避免 cutoff bias

### 3.2 前端：中介卡片 UX

文件：`frontend/components/admin/workshop/IPRecognitionCard.tsx`（新建）

- 不是大弹窗，是 inline 在生成按钮下方 500ms 展开的轻量卡片
- 高置信度命中（≥0.85）时显示三选项，默认勾选"① 高复刻原作（推荐）"
- 中置信度（0.5~0.85）时显示二选项，默认勾选"否，按我写的来"
- 低置信度/明确原创 → 不展示卡片，直接进入生成
- **8 秒无操作 → 自动按默认继续**（避免用户离开导致卡死）
- 卡片可 expand 一行"如有指定原作来源（百度百科 url 等），粘贴在此能提升准确率" —— 选填

### 3.3 SSE 协议扩展

`frontend/lib/admin-sse-events.ts` 新增事件类型：

```ts
type IPRecognitionEvent = {
  phase: "ip_recognition";
  code: "completed";
  meta: {
    kind: "known_ip" | "hybrid" | "original";
    confidence: number;
    ip_name?: string;
    one_liner?: string;
    source_hints?: string[];
  };
};
```

后端在 Stage 0 完成时推送，前端收到后渲染卡片并暂停 pipeline，等待用户选择（或 8s 默认）。

### 3.4 用户选择对下游的影响（fidelity_mode）

用户选项 → 后端字段 `fidelity_mode`：

| 选项 | fidelity_mode | 下游约束等级 |
|---|---|---|
| ① 高复刻原作 | `strict` | 硬约束：地名/角色/势力必须从 IP Pack 选用，不得自造同类 |
| ② 借鉴主线，自由创作 | `loose` | 软约束：IP Pack 作为参考素材，允许扩展 |
| ③ 这不是复刻 / 原创 | `none` | 完全自由，跳过 IP Research 子流水线 |

`fidelity_mode` 持久化到 `world_drafts.payload.fidelity_mode`，整个 pipeline 共享读取。

---

## 4. Stage A+：IP Research 子流水线

替换现有 `services/research_pack_builder.py:build_research_pack`，独立成新模块 `services/ip_research_pipeline.py`。

仅当 `fidelity_mode in (strict, loose)` 时运行；`none` 直接跳过。

### 4.1 子步骤

#### Step 1：IP 元数据识别（复用 Stage 0 结果）
Stage 0 已经识别出 ip_name / ip_type / source_hints，直接复用。不再重跑 LLM。

#### Step 2：多源并发抓取
基于 ip_type 决定抓哪些源：

| ip_type | 抓取源（并发） |
|---|---|
| tv / movie | Tavily 通用 + 维基百科 + 百度百科 `/item/<ip_name>` + 豆瓣搜索 |
| novel | Tavily + 维基 + 百度百科 + 晋江 / 起点（视来源） |
| anime | Tavily + 维基 + 百度百科 + 萌娘百科 |
| game | Tavily + 维基 + 百度百科 + 游侠 / IGN |
| other | Tavily + 维基 + 百度百科 |

实现方式：

- 维基百科：HTTP fetch `zh.wikipedia.org/wiki/<ip_name>` + 解析
- 百度百科：HTTP fetch `baike.baidu.com/item/<ip_name>` + 解析 infobox / 角色列表
- 豆瓣 / 萌百 / 游侠：Tavily 限制 `site:` 搜索代替直接抓（反爬规避）
- 晋江 / 起点：Tavily `site:` + 标题模糊匹配

每个抓取器输出 `list[Passage]`，统一 schema。单源失败不致命，记录到 warnings。

**容量约束**：
- 每源最多 8 passages
- 单 passage 最长 2000 字符
- 全流程 max passages = 30（足够 LLM 抽取，避免超 token）

#### Step 3：RAG 结构化抽取

新 schema `schemas/ip_knowledge_pack.py`：

```python
class IPCharacter(BaseModel):
    name: str
    role_in_story: str            # "女主"/"男主"/"反派"/"配角"
    relation_to_protagonist: str  # "丈夫"/"师兄"/"母亲"/...
    traits: list[str]             # 性格特征
    must_have: bool               # 是否核心人物，critic 用
    source_passage_ids: list[str] # 可追溯

class IPKnowledgePack(BaseModel):
    ip_name: str
    ip_type: str
    summary: str                  # 200~500 字
    characters: list[IPCharacter] # 至少 5 个核心 + 若干次要
    places: list[dict]            # {name, description, must_have, source_ids}
    factions: list[dict]
    iconic_objects: list[dict]
    key_events: list[dict]        # 原作大事件背景
    tone_lingo: list[str]         # 称谓/口头禅/风格词
    passages: list[Passage]       # 原始素材（保留可追溯）
```

抽取通过 LLM call：把所有 passages 拼成 RAG context，一次性输出完整 pack JSON。Prompt 要点：
- "**只从素材中抽取**，禁止凭记忆补充原作里没有出现的内容"
- "每个条目必须标注 source_passage_ids"
- "must_have_characters 至少包含原作的男女主和核心反派"

#### Step 4：完整性自检 + 补抓

新 LLM call："基于 summary（200 字），上面的 characters 清单是否遗漏了原作里有名有姓的关键角色？请列出可能遗漏的姓名（如有）。"

如果 LLM 列出 ≥2 个遗漏角色：
- 用每个遗漏角色名做 1 次 Tavily 补抓（`site:baike.baidu.com 角色名`）
- 把新 passages 加入，重跑一次 Step 3 抽取
- 至多 1 轮补抓（防止无限循环）

输出最终 `IPKnowledgePack`。

### 4.2 持久化

新表 `ip_knowledge_packs`：

```sql
CREATE TABLE ip_knowledge_packs (
    id UUID PRIMARY KEY,
    world_id UUID REFERENCES worlds(id),
    draft_id UUID REFERENCES world_drafts(id),
    ip_name VARCHAR(200),
    fidelity_mode VARCHAR(20),
    pack_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_ip_packs_world ON ip_knowledge_packs(world_id);
CREATE INDEX ix_ip_packs_draft ON ip_knowledge_packs(draft_id);
```

存储用途：
- 调试：admin 后台只读查看页（半小时工作量），查 pack 内容定位生成偏差
- critic 回炉：critic 打回下游 stage 时复用 pack，不重抓
- 未来缓存接口：表已存在，路线 3 的同 IP 缓存只是加一个 lookup

不做的：版本化、人工编辑器、admin 校对工具 —— YAGNI。

---

## 5. 下游 prompt 硬约束改造

涉及文件（按 stage 顺序）：

| Stage | 文件 | 改动 |
|---|---|---|
| world_base | `services/world_creator_agent_v2.py:_run_world_base` | 接收 IP Pack；prompt 中：`地点必须从 IP Pack 的 places 中选用，可微调描述，但不得新增同类地点` |
| lore_dimensions | `services/world_creator_agent_v2.py:_run_lore_dimensions` + `services/lore_dimensions_builder.py` | **新增 passages 参数**（当前缺失）；prompt 注入 IP Pack 的 factions/key_events |
| character_roster | `services/character_roster_builder.py` | prompt：`角色清单必须包含 IP Pack 中 must_have=true 的所有角色，可额外添加配角` |
| characters | `services/world_creator_agent_v2.py:_run_characters` | 每个 character 生成时检索 IP Pack 中对应角色条目，作为强制 grounding |
| shared_events | `services/shared_events_builder.py` | prompt 注入 IP Pack 的 key_events 作为历史背景骨架 |
| events_data | `services/events_data_builder.py` | 软约束：事件可发挥但势力/地名只能从 IP Pack 选 |

`fidelity_mode = strict` 时使用上述硬约束 prompt；`loose` 时改为"参考但允许扩展"；`none` 时跳过整个 IP Pack 注入逻辑。

### Prompt 改造原则

- 删除所有"（无已知 IP）/（无）"这类**反向暗示**（`services/world_creator_agent_v2.py:362-373`）—— 空字段就不渲染那一行
- 把"标志性人名：x, y, z" 这种**参考语气**改成"**必须使用以下角色**：x, y, z"
- 把 `summary[:400]` 提到完整 summary（500 字）+ 关键 passages 头部
- 把 IP Pack 整个 JSON 序列化注入（控制在 3000 token 内）

---

## 6. critic IP 一致性硬卡口

文件：`services/world_critic_service.py`

新增校验规则（仅 `fidelity_mode in (strict, loose)` 时触发）：

```
规则 1: must_have_characters 命中率
  hit = count(NPCs whose name in pack.must_have_characters) / count(pack.must_have_characters)
  strict: hit < 0.9 → 打回 characters stage
  loose:  hit < 0.6 → 打回 characters stage

规则 2: canonical_places 出现率
  hit = count(world.locations whose name in pack.places) / count(pack.places where must_have=true)
  strict: hit < 0.8 → 打回 world_base
  loose:  hit < 0.5 → 打回 world_base

规则 3: 禁词检查（strict only）
  检查生成内容里是否出现"明显与 IP Pack 冲突的同类自造名词"
  实现：让 LLM 1 次 call 判断 "生成的地名 [...] 中有哪些不在 pack 里且语义重叠？"
  命中 → warning（不打回，记录到 admin 审查）
```

每个 stage 最多回炉 1 次（防无限循环），第二次不通过仍 publish 但 admin 看到 warning。

---

## 7. graceful 退化

| 场景 | 处理 |
|---|---|
| `fidelity_mode = none`（原创） | 跳过整个 IP Research、IP Pack 不入表、下游 prompt 走当前的自由创作模式 |
| Stage 0 LLM 失败 | 默认 `kind=original, confidence=0`，走原创流程，事件 warning |
| 多源抓取部分失败（如百度百科超时） | 用 fallback 源（仅 Tavily + 维基）继续，warning |
| 多源抓取全部失败 | 退回当前 `probe_ip_canon` 的 LLM 凭记忆模式，但 critic 跳过硬卡口（因为没有可信 pack 校验依据），warning |
| 抽取出的 pack 角色 < 3 个 | 视为"识别失败"，自动降级到 `fidelity_mode=loose`，admin warning |
| 网络完全不可用 | Stage 0 直接走原创路径 |

---

## 8. 测试集：IP 复刻金标准

文件：`backend/tests/ip_fidelity/`

准备 5 个基准 IP，覆盖不同特征：

| IP | 类型 | 特征 | 金标准要点 |
|---|---|---|---|
| 红楼梦 | 古典小说 | LLM 烂熟 | 12 主要角色全到、贾府/大观园在 places |
| 逐玉 | 影视剧 | cutoff 之后新剧 | 樊长玉/谢征/李怀安/贺敬元 等 6 个核心角色、临安镇 |
| 沙丘 | 海外科幻 | 中文 LLM 弱、英文源 | Paul/Leto/Jessica 等、Arrakis/Caladan |
| 诡秘之主 | 网文（中文） | 长尾、角色复杂、序列体系 | 克莱恩/奥黛丽/罗塞尔，22 序列等 |
| 雾隐镇 | 原创 | 不是 IP | fidelity_mode 应被识别为 original，pack 不应生成 |

每个 IP 准备一份 `expected.json`：
```json
{
  "must_have_characters": ["樊长玉", "谢征", "李怀安", ...],
  "must_have_places": ["临安镇", "北境", ...],
  "ip_recognition_kind": "known_ip"
}
```

测试脚本 `backend/tests/test_ip_fidelity.py`：
- 跑生成 → 提取生成结果中的 npc names / location names
- 跟 expected 对比，计算 hit_rate
- 整体目标：5 个 IP 平均命中率 ≥ 85%

跑通后纳入 CI 周跑（不每 PR 跑，太贵）。

---

## 9. 验收标准

1. 用户输入"影视剧 逐玉"四个字 → 生成出的 world 含李怀安 + 临安镇 + 武安侯将军 + 十七年前血仇 + 其他二级角色
2. 用户输入"未来火星上的官僚社会" → 系统识别为 original，不走 IP Pack，下游自由创作正常
3. 用户输入"赛博朋克版红楼梦" → 系统识别为 hybrid（confidence 0.5~0.85），中介卡片展示，用户选"是"后红楼梦角色到位
4. IP 复刻金标准测试集 5 IP 平均命中率 ≥ 85%
5. 已发布的雾隐镇（原创）行为不变
6. 逐玉重新生成一份样板 world，与现有版本并排，对比文档放在 `docs/_archive/`

---

## 10. 实施顺序与拆分

### Phase 1（核心，1 周）
- Stage 0 IP 识别后端 + SSE
- 前端中介卡片
- `ip_knowledge_pack` 表 migration + schema
- IP Research 子流水线（不含百度百科直抓，先只用 Tavily + 维基 + 多源 site: 搜索）
- 下游 prompt 改造（world_base / character_roster / characters）

### Phase 2（补强，3-4 天）
- 百度百科 / 萌百 / 游侠的直抓 parser
- lore_dimensions 接 passages
- shared_events / events_data prompt 改造
- critic IP 一致性硬卡口
- graceful 退化全分支

### Phase 3（验证，2 天）
- IP 金标准测试集
- 逐玉重生成样板
- admin 后台 IP Pack 只读查看页

---

## 11. 风险与决策记录

- **抓取反爬风险**：百度百科直抓可能被反爬。Phase 1 先不做直抓，验证 Tavily `site:baike.baidu.com` 搜索是否够用；Phase 2 必要时再加直抓
- **多源延迟**：当前 8s，未来可能涨到 15-25s。SSE 心跳 pulse 已就位（来自 2026-05-12 generation-feedback 计划），用户体感可控
- **LLM token 成本**：IP Pack 序列化注入下游 prompt 会增加 token。预估 +20% 单局 LLM 成本，路线 2 整体成本仍可接受
- **LLM 抽取幻觉风险**：即使叫它"只从素材抽取"，仍可能编。完整性自检 + critic 双层兜底
- **`fidelity_mode=loose` 的使用率**：暂无数据。如上线后发现用户基本不选 loose，未来可以删掉这个中间档简化系统
- **国际化**：当前测试集偏中文 IP，海外 IP（沙丘等）的多源抓取效果待 Phase 3 实测验证

---

## 附录 A：现状代码定位

- 现有 `probe_ip_canon`：`services/research_pack_builder.py:114`
- 现有 `build_research_pack`：`services/research_pack_builder.py:148`
- 现有下游 stage：`services/world_creator_agent_v2.py:454`(lore_dimensions, 缺 passages) / `:499`(character_roster) / `:587`(lore_pack) / `:656`(characters) / `:720`(shared_events) / `:808`(events_data)
- 现有 critic：`services/world_critic_service.py`
- 现有 ResearchPack schema：`schemas/research_pack.py`
- 现有 SSE 事件 schema：`frontend/lib/admin-sse-events.ts`

## 附录 B：参考调试样本

任务 ID `e1b16f6d-6f82-464b-8b29-bdff3349da11`（2026-05-12 逐玉生成）的 `intermediate_state.research_pack` 是本设计的根因证据样本，保留备查。
