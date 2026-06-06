# Generation Pipeline Overhaul — 2026-05

> 设计 spec，2026-05-25 起草。Generation 侧（world + script 创建）质量提升，
> 覆盖 BUGS #9 / #16 / #23 / #24 / #25-gen + 用户 4 担忧（IP 复原 / 名字一一对应 /
> 跨阶段 name drift / playable 全而不滥）。
>
> **不包含**：runtime 引擎改造（已在 `runtime-architecture-overhaul-2026-05.md` 覆盖）；
> 任务生命周期 reaper / LLM 全局 throttle（BUGS #17/#20，单独 spec）；
> 创作工坊前端 UI 改动（除非 SSE schema 变）。

---

## 1. 背景与动机

### 1.1 现状

Generation pipeline（`services/world_creator_agent_v2.py`，2846 行）目前已落地：
- 五层模型（policy / research / strategy / execution / validation）
- IP 识别 + IP knowledge pack（fidelity_mode: strict / loose / none）
- critic gate（H1 shape / H2 light / H2.5 heavy / H3 moderation）
- 草稿 → 发布原子事务
- cover image gpt-image-2 极简自然语言（cover-image-prompt-redesign-2026-05 落地后）

跑了 4-5 批 batch（multi-compare / ip-compare / dogfood）暴露出的**质量短板**集中在 5 个方向：

| 编号 | 症状 | 当前根因 |
|---|---|---|
| **#9 / #16** | world name 长 800 字（描述当名字）/ 截断到 30 字仍像描述前缀 | LLM 自由发挥 + 仅长度截断兜底，无语义检查 |
| **#23** | 福尔摩斯 fidelity_loose 把玛丽改成莫里亚蒂私生女 | IP pack 只约束 surface 层（人名/地点/era），不约束 plot 层（关系/身份/结局） |
| **#24** | 旧茶局 world_events 暗示林婉清是黑手，结局指认玩家是真凶 | cross_artifact_validator 只查 schema 引用（npc_name 存在 / clue 存在），不查 semantic 一致性 |
| **#25-gen** | 狄仁杰 NPC 在 runtime 持续 information-dump | gen 阶段 LLM 在 IP 上下文里**自己写出**"主动测试观察力 / 导师式"的抢权人设（character_builder prompt 本身没有指令性语句） |
| **用户担忧 3** | 选了"范闲"角色，详情页写成"范慎" | 跨阶段 name drift——roster 出来的 name 在 characters / events / endings 阶段被 LLM 改写或字形混淆 |

加上用户两个产品诉求：
- **担忧 1 / 2**: IP 复原应严格、名字一一对应（既然识别成 IP 就要这个 IP，不允许 LLM 改名 / 重写关系）
- **担忧 4**: playable 视角"主角 + 有戏配角"，3-10 个区间，LLM 自决

### 1.2 根本问题

5 类 bug + 2 个产品诉求归结到 4 个设计 gap：

| Gap | 影响 |
|---|---|
| **G1：name 在系统里没"canonical 化"** | name 既可能在产出时是垃圾（#9/#16），也可能在跨阶段时漂移（担忧 3）。两边都是 name 不被当作 fixed identity 对待。 |
| **G2：IP 复原止步 surface 层** | loose 这一档语义模糊（"参考但允许改"），最容易出 plot 颠覆；strict 也只硬约束人名/地点列表，关系和决定性结局没硬约束（#23）。 |
| **G3：critic 没语义层 cross-check** | events 暗示 A 是凶手 vs endings 揭露玩家是凶手——schema validator 看不到这种矛盾（#24）。 |
| **G4：playable / character 人设没受约束** | playable 是纯 Python heuristic（无视角差检查）；character.personality 由 LLM 自由发挥（容易写出抢权倾向，#25-gen） |

### 1.3 设计目标

- name 不再"沦为描述前缀" / 不再"跨阶段 drift"
- IP 一一对应：strict 是默认（砍掉 loose），must_have_characters 100% 就位，自创 NPC 不允许原作风格命名
- L1（人物关系）/ L3（决定性 plot beat）有硬约束**前提是 fixture 实验验证可行**
- events ↔ endings 凶手链 / 真相链自洽性可被检测
- playable 视角 3-10 个，"主角 + 有戏配角"，无明显冗余
- character.personality 减少抢权倾向（gen 侧弱防御，根治在 runtime v2）

---

## 2. 设计原则

### 2.1 修在已有容器里，不开新阶段
critic gate 已经是 H1/H2/H2.5/H3 多 pass 结构，#24 semantic_review 进 H2.5 扩展。
不新增 generation 阶段，避免 SSE phase 列表变更。

### 2.2 strict-only：砍掉 loose 档
loose 是"参考但允许改"——既不严肃也不自由，最容易出 #23 灾难。
保留 strict（识别成 IP 就严格对应）+ none（原创世界，无 IP 约束）两档。
fidelity_mode 字段保留（向下兼容旧数据），但 loose 行为**升格**到 strict 等价。

### 2.3 name canonicalization 是子系统
name 不是某个阶段的字段，是贯穿 roster → characters → events → endings → playable
的一条线。统一处理（生成时 critic / 冻结 / 下游强制 / drift 检测）才能根治。

### 2.4 wait-and-see for L1/L3 anchors
inviolable_plot_anchors 是个新概念——靠 LLM 写出"玛丽是华生妻子，禁止设为莫里亚蒂
私生女"这种关系性约束。**先做 fixture 实验**（§6.3），实验过了再投实施。

---

## 3. 当前 Pipeline 与修复落点

### 3.1 World 生成 15 阶段（按 SSE phase 顺序）

| # | Phase | 函数（line） | 当前 LLM 调用 | 本 spec 改动 |
|---|---|---|---|---|
| 0 | research_pack | `_run_research_pack` (512–560) | research_pack LLM × 1 | 不变 |
| 1 | ip_research | `_run_ip_research` (563–739) | pre_extract + grounding × 2 LLM | **+ inviolable_plot_anchors + forbidden_name_patterns**（§6.4）|
| 2 | world_base | `_generate_world_base` (782–881) | world_base LLM × 1（+3 retry） | **+ name_critic post-call**（§5.1）|
| 3 | lore_dimensions | `_run_lore_dimensions` | dim LLM | 不变（已消费 ip_pack）|
| 4 | character_roster | `_run_character_roster` | roster LLM | **+ forbidden_name_patterns 硬约束**（§5.2）+ **+ canonical name 冻结**（§5.2）|
| 5 | lore_pack | `_run_lore_pack` | content LLM × N | 不变 |
| 6 | characters | `_run_characters` | character batch LLM × N | **+ canonical name 强制 + personality 抢权禁令**（§5.3, §9.1）|
| 7 | shared_events | `_run_shared_events` | shared events LLM | **+ canonical name 强制**（§5.3）|
| 8 | relations_pack | `_run_relations_pack` (pure Python) | 无 | 不变 |
| 9 | events_data | `_run_events_data` | events LLM × N | **+ canonical name 强制**（§5.3）|
| 10 | playable | `_run_playable` (pure Python) | 无 | **改 LLM 化**（§7）|
| 11 | critic | `_run_critic` | H1 + H2 + H2.5 + H3 | **+ name-drift detection (H1.5) + viewpoint dedup (H2.5 ext) + character-抢权 warning (H2.5 ext)**（§5.4, §7.3, §9.2）|
| 12 | visual_brief | `_run_visual_brief_stage` | brief LLM | 不变 |
| 13 | images | `_run_images` | image gen × N | 不变 |
| 14 | validating | `_run_validating` (pure Python) | 无 | **+ cross_artifact 扩展跑（roster ⊆ characters[].name ⊆ events.present_npcs ⊆ endings refs）**（§5.5）|

### 3.2 Script 生成 8 阶段

| # | Phase | 函数（line） | 当前 | 本 spec 改动 |
|---|---|---|---|---|
| 0 | research_pack | (2222–2253) | research × 1 | 不变 |
| 1 | script_base | `_generate_script_base_v2` (2589–2668) | script_base LLM × 1 | **+ name_critic post-call**（§5.1）|
| 2 | events | (2275–2314) | events LLM × N | **+ canonical name 强制**（§5.3）|
| 3 | endings | `_generate_endings_v2` (2670–2812) | endings LLM × 3 retry with feedback | **+ canonical name 强制 + inviolable anchors 注入**（§5.3, §6.4）|
| 4 | playable | `_select_script_playable_v2` (2814–2843, pure Python) | 无 | **改 LLM 化**（§7）|
| 5 | critic | (2378–2481) | shape + light + heavy + mod | **+ semantic_review (events↔endings) + name-drift + viewpoint dedup**（§5.4, §7.3, §8）|
| 6 | script_visual_brief | (2704–2767) | brief LLM | 不变 |
| 7 | script_images | (2489–2556) | image gen × N | 不变 |

### 3.3 publish-time 检查

`publish_service.py:516` `validate_cross_artifact(world, script)` 仍保留作为 safety net，
但 critic 阶段会先跑一遍（§5.5）——避免发布时才暴露 cross-artifact 错误已浪费 20 分钟。

---

## 4. 文件改动 overview

### 新增

- `backend/services/name_critic.py` — 单独 LLM 调用，判定 name 是否合格 + 给替换建议（§5.1）
- `backend/services/canonical_name_registry.py` — roster 冻结 + 下游强制 helper + drift detection（§5.2-5.4）
- `backend/services/semantic_review_service.py` — events ↔ endings 自洽性 LLM 检查（§8）
- `backend/services/playable_selector.py` — 从 `_select_script_playable_v2` 抽出 + LLM 化（§7）

### 改写

- `backend/schemas/ip_knowledge_pack.py` — 新增 `inviolable_plot_anchors: list[InviolableAnchor]` + `forbidden_name_patterns: list[str]` 字段（§6.2）
- `backend/services/ip_research_pipeline.py` — `_PRE_EXTRACT_SYSTEM` 和 `_GROUND_SYSTEM` prompt 加新字段 + `_pre_extract_canon` / `_ground_and_augment` 解析新字段（§6.4）
- `backend/services/world_creator_agent_v2.py`:
  - `_generate_world_base` line 854–881 加 name_critic post-call（§5.1）
  - `_generate_script_base_v2` line 2662 加 name_critic post-call（§5.1）
  - `_run_character_roster` 调用 canonical_name_registry.freeze() 冻结 names（§5.2）
  - `_run_characters` / `_run_shared_events` / `_run_events_data` prompt 注入 canonical names 强制条款（§5.3）
  - `_run_playable` / `_select_script_playable_v2` 替换成 playable_selector.select_playable()（§7）
  - `_run_critic` H1.5 加 name_drift_check / H2.5 ext 加 semantic_review / viewpoint_dedup / character-抢权 warning（§5.4, §7.3, §8, §9.2）
  - `_run_validating` 跑 extended cross_artifact（§5.5）
- `backend/services/character_roster_builder.py` — character batch prompt 加：
  - canonical name 100% 字符匹配条款（§5.3）
  - personality 字段抢权禁令（§9.1）
  - non-IP-style naming 检查（§6.5）
- `backend/services/world_critic_service.py` — `heavy_critic_characters` 加 character-抢权 维度；`heavy_critic_playable` 加 viewpoint_dedup 维度（§7.3, §9.2）
- `backend/services/cross_artifact_validator.py` — 扩展 check：endings.required_clues + character 内自指 + starting_inventory 内 name 引用（§5.5）

### 删除 / 弃用

- 不删 fidelity_mode = "loose"（schema 字段保留向下兼容），但 `_run_ip_research` 中 loose 行为升格为 strict（§2.2）
- `_select_script_playable_v2` 纯 Python heuristic 路径被 LLM 化替换（§7）

### 配置

- `backend/config.py`:
  - 新增 `name_critic_enabled: bool = True`
  - 新增 `inviolable_anchors_enabled: bool = True`（fixture 实验失败时可降级）
  - 新增 `semantic_review_enabled: bool = True`
  - 新增 `playable_count_typical: int = 4`（typical, brief target）
  - 新增 `playable_count_hard_max: int = 10`
  - 新增 `playable_count_hard_min: int = 3`

---

## 5. A. Name canonicalization 子系统

### 5.1 name_critic（生成时质量）

**问题**：world_base / script_base LLM 偶发把整段 description 塞 name 字段；
截断后仍像描述前缀（"原创近未来心理悬疑互动世界" 不是名字）。

**改造**：在 `_generate_world_base` 拿到 LLM JSON 后、写 self 状态前，调一次 cheap LLM：

```python
# backend/services/name_critic.py
class NameCriticResult(BaseModel):
    is_acceptable: bool
    reason: str                  # 不通过的原因（"重复 description 前缀" / "占位 name" / "无关键 IP 标识"）
    suggested_name: str | None   # 建议替换名（4-12 字，含 IP 标识如果有）
```

调用 slot = `world_creator_planner`（廉价档），prompt：
```
你判断一个互动叙事世界的标题质量。
输入：name、description（前 300 字）、genre、era、IP 信息（若有）。
不合格条件（任一命中）：
1. name 重复 description 的前缀（>50% 字符重叠）
2. name 是占位（"未命名世界" / "新世界" / "故事" / "剧情" 等）
3. name 长度 < 3 字或 > 15 字
4. IP 模式下 name 完全没有 IP 标识词（如选了狄仁杰却叫"暗夜疑云"）
5. name 包含 markdown / 换行 / 多余标点

输出严格 JSON：
{"is_acceptable": bool, "reason": str, "suggested_name": str | null}
```

**失败兜底**：
- name_critic LLM 调用失败 → 走当前 line 854–881 的截断兜底（保留）
- is_acceptable=false 但 suggested_name 为空 → 截断兜底
- 配置 `name_critic_enabled=False` 时整个 block 跳过

**成本**：~$0.001 / 调用，2 次（world + script）总 $0.002。

### 5.2 canonical name registry

**问题**：roster 出来的 name 在后续 characters / events / endings 阶段会被 LLM 改写或字形混淆（"范闲"→"范慎"）。

**改造**：character_roster 阶段结束后，立即冻结 name set：

```python
# backend/services/canonical_name_registry.py
class CanonicalNameRegistry:
    def __init__(self):
        self.character_names: frozenset[str] = frozenset()
        self.place_names: frozenset[str] = frozenset()

    def freeze_from_roster(self, roster: list[CharacterRosterEntry], world_base: dict) -> None:
        self.character_names = frozenset(c.name for c in roster)
        locations = world_base.get("locations") or []
        self.place_names = frozenset(loc.get("name") for loc in locations if loc.get("name"))

    def prompt_block(self, kind: str = "character") -> str:
        """Return a prompt fragment to inject into downstream LLM calls."""
        names = self.character_names if kind == "character" else self.place_names
        return (
            f"## CANONICAL NAMES（必须 100% 字符级匹配，禁止同音字 / 别号 / 改写）\n"
            f"{', '.join(sorted(names))}\n"
            f"如需引用此列表外的角色，明确标注『新增 NPC』。"
        )
```

挂在 `WorldCreatorAgent` 实例上：`self._name_registry: CanonicalNameRegistry`。

### 5.3 下游 prompt 强制

修改这些 builder 的 prompt（在已有 system / user prompt 末尾追加 registry.prompt_block）：
- `character_roster_builder.py:build_characters_in_batches` — character batch 阶段
- `events_data_builder.py:build_events_data` — events_data 阶段（world + script 共用）
- `shared_events_builder.py:build_shared_events`
- `world_creator_agent_v2.py:_generate_endings_v2` — endings 阶段（line 2670+）
- `playable_selector` — playable LLM 选择阶段

注入位置：在所有 IP / brief 注入之后，prompt 最末尾（接近 LLM 注意力最强位置）。

### 5.4 critic name-drift detection（新 H1.5 step）

**问题**：即使 prompt 强制，LLM 仍可能在长输出里写错名字。critic 阶段加纯 Python 检查兜底。

**实现**：`_run_critic` 在 H1 shape 验证后插入 H1.5：

```python
def _check_name_drift(payload: dict, registry: CanonicalNameRegistry) -> list[str]:
    """扫描 payload 全部字段，发现非 canonical 名字 references 就 warn。"""
    warnings = []
    # 1. characters[].name 必须 ∈ registry.character_names
    for c in payload.get("world_characters") or []:
        if c.get("name") not in registry.character_names:
            warnings.append(f"character name '{c.get('name')}' not in canonical registry")
    # 2. character.description / starting_inventory / peer_relations 内提到的名字
    #    扫一遍：用 registry.character_names ∪ characters[].name 做 valid set
    valid_names = registry.character_names
    for c in payload.get("world_characters") or []:
        text_blob = " ".join([
            c.get("description") or "",
            " ".join(c.get("starting_inventory") or []),
            " ".join(str(v) for v in (c.get("initial_peer_relations") or {}).values()),
        ])
        # 简单 heuristic：用 jieba / character n-gram 找疑似人名 → 落地时实现细化
        suspects = _extract_suspected_names(text_blob, valid_names)
        unknown = [s for s in suspects if s not in valid_names]
        if unknown:
            warnings.append(f"character {c.get('name')} text references unknown names: {unknown}")
    # 3. events_data / endings_data 引用
    for ev in payload.get("events_data") or []:
        for npc in ev.get("present_npcs") or []:
            if npc not in valid_names:
                warnings.append(f"event {ev.get('id')} references unknown npc: {npc}")
    # 同理 endings...
    return warnings
```

heuristic name 抽取（`_extract_suspected_names`）：
- 中文 IP：基于已知人名做 fuzzy match（"范闲" vs "范慎" 编辑距离 1）→ warn 类型 = `possible_name_drift`
- 完全不认识的名字 → warn 类型 = `unknown_name_reference`

**失败处理**：name-drift warning 写到 `all_warnings`，**不阻塞** publish（避免误杀），但 critic repair pass 优先针对 drift 修复。

### 5.5 cross_artifact_validator 扩展

`cross_artifact_validator.py` 当前只查 2 类：
- events.present_npcs ⊆ characters[].name
- endings.required_clues ⊆ events.spawn_clues

扩展加 3 类：
- character.description / starting_inventory / peer_relations 内提到的 name ⊆ characters[].name（自指完整性）
- endings.description / soft_conditions 内提到的 name ⊆ characters[].name
- character_roster.names == characters[].name set（roster 冻结一致性）

**调用点**：
- critic 阶段（_run_critic 末尾，跑一次拿 warnings）
- publish 阶段（publish_service.py:516，**仍跑一次**作为 safety net，但应该已经被 critic 拦截过）

**失败处理**：
- critic 阶段失败 → warning 进 all_warnings
- publish 阶段失败 → `CrossArtifactError`，阻止发布

---

## 6. B. IP 复原强化

### 6.1 砍掉 loose 档

`fidelity_mode` 字段保留（schema 向下兼容），但运行时 loose 视为 strict：

```python
# services/ip_research_pipeline.py
def _effective_fidelity(mode: FidelityMode) -> FidelityMode:
    if mode == "loose":
        return "strict"   # 升格
    return mode
```

注入点全部消费 `_effective_fidelity(self._fidelity_mode)`，不再用原始字段。

**前端**：admin 端"创世"表单移除 loose 选项，只剩 strict / none。已有的 loose 草稿在编辑时仍可发布（按 strict 处理）。

### 6.2 IPKnowledgePack schema 新增字段

```python
# schemas/ip_knowledge_pack.py
class InviolableAnchor(BaseModel):
    kind: Literal["relation", "outcome", "identity"]
    subjects: list[str]                      # 涉及的人物 / 实体
    statement: str                           # 一句陈述
    forbidden_alternatives: list[str] = []   # LLM 改编时最容易踩的颠覆形式


class IPKnowledgePack(BaseModel):
    # ... 已有字段 ...
    inviolable_plot_anchors: list[InviolableAnchor] = Field(default_factory=list)
    forbidden_name_patterns: list[str] = Field(default_factory=list)
```

`forbidden_name_patterns`：自然语言陈述（不是 regex），例如：
- "禁止用'狄X'格式给非原作 NPC 命名（防止误认为狄家亲属）"
- "禁止使用维多利亚-style 三段式英文名给现代中国背景"

### 6.3 fixture 实验结果（2026-05-25 已跑）

`experiments/local/pipeline/ip_anchor_fixture.py` 跑了 2 个 IP（福尔摩斯 / 狄仁杰），
使用 `admin_generation` slot，单次 LLM 调用，无 Tavily grounding。
完整报告：[`docs/experiments/2026-05-25-ip-anchor-fixture.md`](../experiments/2026-05-25-ip-anchor-fixture.md)。

| IP | anchors | with_forbidden_alt | elapsed | verdict |
|---|---|---|---|---|
| 福尔摩斯（novel）| 6 / 6 good | 6 / 6 | 55s | **USABLE** |
| 狄仁杰（神探狄仁杰系列, tv）| 6 / 6 good | 6 / 6 | 86s | **USABLE** |

样本（福尔摩斯）：
- relation："福尔摩斯与莫里亚蒂是终极宿敌；禁止设为秘密导师或另有隐情的伙伴"
- identity："艾琳·艾德勒不是福尔摩斯的浪漫恋人；禁止改为长期秘密情人"
- outcome："莱辛巴赫瀑布莫里亚蒂坠崖身亡，福尔摩斯假死隐匿"
- forbidden_name_patterns："禁止给哈德森太太杜撰中文姓如『黄太太』"

样本（狄仁杰）：
- relation："李元芳是狄仁杰的护卫与得力助手；禁止改为反派或叛徒"
- outcome："多个剧均以狄仁杰还原真相+反派伏法收尾；禁止改写为狄仁杰失败"
- forbidden_name_patterns："禁止用『狄怀英』『李怀玉』等近似原作姓名结构给非原作 NPC 命名"

**结论：spec §B 全量按 LLM-generated anchors 路线实施**，不需要预定义字典 fallback。
注意：长尾冷门 IP 仍可能 anchors 为空，按 §10 failure mode 处理（不阻塞，fallback 到原有 must_have_characters 约束）。

成本：单次 LLM 调用 ~$0.015（5287 字输出 × DeepSeek-v4-pro 输出价），可接受。耗时 55-90s 折进 ip_research 阶段总耗时不会显著拉长（当前 ip_research 已经是 1-2min 量级）。

### 6.4 IP 注入点改造

5 个 LLM 调用消费新字段（在已有的 fidelity block 后追加）：

| 注入点 | 现状 | 新增 |
|---|---|---|
| `_PRE_EXTRACT_SYSTEM` prompt | 输出 characters/places/... | + 输出 inviolable_plot_anchors + forbidden_name_patterns |
| `_GROUND_SYSTEM` prompt | 验证 + 补字段 | + 验证 anchors（passages 矛盾时删，无矛盾时保留即使无 source）|
| `_generate_world_base` user prompt（line 806-823） | 注入 must_have_characters / places | + 注入 anchors（让 base_setting 文本不写违反 anchor 的设定）|
| `_generate_script_base_v2` user prompt（line 2613-2629） | 注入 IP fidelity block | + 注入 anchors |
| `_generate_endings_v2` user prompt（line 2710-2724） | 注入 must_have_characters / canonical_endings_hint | + 注入 anchors（含 outcome 类）|

### 6.5 character_roster forbidden_name_patterns 硬约束

`character_roster_builder.py` prompt 加：
```
## 命名约束
1. IP must_have_characters 必须 100% 出现（字符完全匹配，无别号 / 简称 / 字号）。
2. 自创 NPC（非原作角色）禁止使用以下命名风格：
   {forbidden_name_patterns 列表}
3. 自创 NPC 在 role_tag 字段标"自创"。
```

critic 阶段 `heavy_critic_characters` 加维度：
- must_have_characters 是否 100% 就位
- 自创 NPC name 是否触碰 forbidden_name_patterns
- 都不通过 → warning + repair pass 优先修复

---

## 7. C. Playable 选择 LLM 化

### 7.1 接通 build_playable_brief

当前 `_run_playable` (world line 1399–1469) 和 `_select_script_playable_v2` (script line 2814–2843) 都是**纯 Python heuristic**（role_tag 含"主角" / is_image_target / fallback first 3）。
`GenerationStrategyService.build_playable_brief` 早已实现（生成 PlayableBrief dataclass），但**没被消费**。

改造：
1. World pipeline：`_run_playable` 改为先调 `build_playable_brief` 拿 brief，再调 LLM 选择
2. Script pipeline：`_select_script_playable_v2` 同上

### 7.2 选择 LLM 调用

新文件 `backend/services/playable_selector.py`：

```python
async def select_playable(
    *,
    characters: list[dict],
    world_base: dict,
    brief: PlayableBrief,
    llm: LLMRouter,
    config: PlayableSelectorConfig,
) -> list[dict]:
    """从 characters 中挑出 3-10 个 playable，目标 typical 数量看 brief。
    
    LLM 任务：
    1. 严格遵守 hard_min=3 / hard_max=10
    2. brief.playable_count_target 是 typical（3-5 常见），允许 ±2 偏离
    3. 必须包含明确的"主角"（role_tag 含主角 / 推动剧情 / 信息接触最广）
    4. 配角入选必须"有戏"：视角差 / 信息差 / 立场差显著
    5. 不允许选明显冗余（两人视角几乎相同时只留一个）
    """
```

prompt 输入：characters[]（每个含 name / role_tag / personality 摘要 / secret 摘要）+
brief（playable_count_target / viewpoint_mix）+ world summary。

prompt 输出：JSON list of `{name, why_playable, viewpoint_signature}`。

### 7.3 heavy_critic_playable 加 viewpoint_dedup 维度

`world_critic_service.py:heavy_critic_playable` 当前查 description validity。
新增维度：
- 任意两个 playable 是否 viewpoint_signature 接近（信息差 + 立场差 + 能力差都≤1 差异）→ warning
- 是否包含至少 1 个明确"主角"标签 → warning if false
- 是否在 hard cap 之内（3 ≤ N ≤ 10）→ error if false（强制 repair）

### 7.4 配置

```python
# config.py
playable_count_typical: int = 4
playable_count_hard_max: int = 10
playable_count_hard_min: int = 3
```

`playable_count_typical` 是 brief 默认目标。LLM 在 hard_min..hard_max 间自由发挥，
但 critic 检 viewpoint 冗余把过度膨胀的拉回来。

---

## 8. D. semantic_review

### 8.1 形态

新文件 `backend/services/semantic_review_service.py`：

```python
async def semantic_review_script(
    *,
    world_payload: dict,       # 已生成的世界（含 characters / events_data / shared_events）
    script_payload: dict,      # 已生成的剧本（含 events_data / endings_data）
    ip_pack: IPKnowledgePack | None,
    llm: LLMRouter,            # 用 reasoning 模型（world_creator_critic slot）
) -> SemanticReviewResult:
    """LLM 判断：
    1. world.events_data 暗示的反派身份 vs script.endings_data 揭露的真凶 是否一致
    2. script.events_data 的 trigger 暗示的因果链 vs endings 的"假解→真解"链 是否自洽
    3. 关键 NPC 的 secret / knowledge / role_in_story 与 endings 出现的揭露是否一致
    4. IP 模式下，inviolable_anchors 是否被违反（重复 §6.4 检查但放在最终 artifact 上）
    """


class SemanticReviewResult(BaseModel):
    passed: bool
    issues: list[SemanticIssue]


class SemanticIssue(BaseModel):
    kind: Literal["villain_mismatch", "causal_break", "secret_inconsistency", "anchor_violation"]
    severity: Literal["warn", "error"]
    description: str            # 一句话描述
    related_artifacts: list[str]  # 涉及的 events.id / endings.id / characters.name
```

### 8.2 调用点 & 处理

- **调用点**：critic 阶段 H2.5 扩展（heavy_critic_endings 之后）。Script 流必跑，
  world 流不跑（world 没 endings 就没自洽性检查的目标）。
- **失败处理**：
  - issues 全 warn → `all_warnings` 追加；不阻塞发布
  - issues 含 error → 触发 repair pass（喂给 endings retry）；仍失败留 warning 不阻塞
- **存档**：`SemanticReviewResult` JSON 存到 `script_drafts.payload.semantic_review`，admin 草稿编辑页可展示

### 8.3 成本

- reasoning 模型一次调用 ~$0.03 / script（DeepSeek-v4-pro 或 Qwen 3.7 thinking）
- 失败 repair → +$0.05（重跑 endings）
- 加权：~$0.04 / script avg

可接受（当前 script gen 总成本 ~$0.30，+13%）。

---

## 9. E. Character 抢权 gen-side 弱防御

### 9.1 character prompt 加禁令

`character_roster_builder.py` character batch system prompt 加：

```
## personality 字段禁令
personality 描述人物**是谁**，不写**怎么和玩家互动**：
- ❌ 禁止: "主动测试玩家观察力" / "会抛细节考验玩家" / "导师式给提示"
- ❌ 禁止: "主动揭示线索" / "替玩家分析" / "代替玩家做判断"
- ✅ 允许: "性格温和，遇事先思考再开口" / "对官场虚伪深恶痛绝"
- 玩家与该 NPC 的互动模式由游戏引擎决定，不由 personality 设定。
```

### 9.2 critic 加 character-抢权 warning

`world_critic_service.py:heavy_critic_characters` 加维度：
- personality 是否包含抢权倾向用词 → warning

不阻塞发布（warning only），但 quality_warnings 里告知 admin。

### 9.3 局限承认

gen-side 禁令是**减弱**不是根治：
- LLM 可能改个说法继续写（"老于 mentor 玩家"等）
- 真正根治在 runtime v2（NPC agent prompt §4 + dramatic_intensity clamp §12）

本 spec 不假装这条能解决 #25。

---

## 10. Failure modes & validators

| 失败 | 处理 |
|---|---|
| name_critic LLM 调用失败 / 解析失败 | 走截断兜底，warn 日志 |
| name_critic 不通过但 suggested_name 空 | 截断兜底 |
| IP pack 中 inviolable_plot_anchors 为空（LLM 没写出来）| 不阻塞；fallback 到 must_have_characters / canonical_endings_hint 已有约束 |
| canonical_name_registry.freeze 为空（roster 为 0）| 已有 fail-fast _MIN_CHARACTERS 闸捕获，本 spec 不动 |
| name-drift detection heuristic 误报 | warning only，不阻塞；admin 可在 quality_warnings 查看 |
| playable_selector LLM 失败 | fallback 到当前 Python heuristic（行为兼容）+ warn |
| playable 数量 < 3 或 > 10 | repair pass 重新选；2 次仍失败 fallback heuristic |
| semantic_review LLM 失败 | warn only，不阻塞；admin 在草稿页可见"未做 semantic review" |
| extended cross_artifact 失败 in critic | warning |
| extended cross_artifact 失败 in publish | CrossArtifactError 阻塞（safety net）|

---

## 11. Cost & latency budget

### 11.1 单次 world generation 增量

| 项 | LLM 调用 | 增量成本 | 增量耗时 |
|---|---|---|---|
| name_critic (world_base) | 1 cheap | +$0.001 | +3s |
| ip_research 加 anchors（同一调用扩字段）| 0 新调用 | +$0.005（token 增量）| +5s |
| extended cross_artifact in critic (Python) | 0 | $0 | <1s |
| name-drift detection (Python) | 0 | $0 | <1s |
| playable LLM 化 | 1 thinking | +$0.02 | +15s |
| **world 增量小计** | +2 | **+$0.026** | **+24s** |

当前 world gen 成本 ~$1.5 + 时长 ~15min，增量 ~1.7% / 2.7%。

### 11.2 单次 script generation 增量

| 项 | LLM 调用 | 增量成本 | 增量耗时 |
|---|---|---|---|
| name_critic (script_base) | 1 cheap | +$0.001 | +3s |
| canonical name 强制（prompt 加字段）| 0 新调用 | <$0.002 (token) | <2s |
| playable LLM 化 | 1 thinking | +$0.02 | +15s |
| semantic_review | 1 thinking | +$0.04 | +30s |
| **script 增量小计** | +3 | **+$0.063** | **+50s** |

当前 script gen 成本 ~$0.30 + 时长 ~10min，增量 ~21% / 8%。

### 11.3 总约束

- 单 world gen 仍在 $2 / 20min 内：✅
- 单 script gen 仍在 $0.40 / 11min 内：✅
- 单 dogfood batch（world+script）增量 ~$0.09，可接受

---

## 12. Migration & rollout

### 12.1 数据 schema

- `IPKnowledgePack` 加 2 字段 → 默认值空 list → 老数据兼容
- 老草稿无 semantic_review 字段 → JSON 列加字段不影响
- **无 Alembic migration**

### 12.2 feature flag

`config.py` 4 个开关：
- `name_critic_enabled` (默认 True，可关掉退回截断兜底)
- `inviolable_anchors_enabled` (默认 True，fixture 失败时降级关掉)
- `semantic_review_enabled` (默认 True，admin 想加速生成可关掉)
- `playable_llm_selection_enabled` (默认 True，可退回 Python heuristic)

每个独立可切，方便定位回归。

### 12.3 rollout 步骤

1. 跑 fixture 实验定 anchor 路线（USABLE / WEAK fallback / BAD fallback dict）
2. 实施 A 子系统（name canon）→ 跑 1 个 world + script 看 name drift 是否消失
3. 实施 C playable LLM → 跑 1 个 script 看 viewpoint 是否多样
4. 实施 D semantic_review + E character 禁令 → 跑 1 个 world+script 看 critic warnings
5. 实施 B IP 强化 → 跑 1 个 IP world（福尔摩斯 strict）看 anchors 是否被遵守
6. 全部上线后跑 1 个 multi-source batch（3 source × script 模式）verify 整体质量

### 12.4 BUGS.md 回写协议

参照 runtime spec Appendix C：每个 BUG 修完同 commit 更新 `experiments/local/BUGS.md`：
- 索引表 🟡 → ✅
- 详细记录追加 `## 修复（YYYY-MM-DD）` 节，含 spec § 引用 + 关键改动 + 验证

涵盖的 BUG：#9 / #16 / #23 / #24 / #25-gen。

---

## 13. 验收标准

### 13.1 功能验收

- [ ] world name 长度 ∈ [3, 15] 且 60% 字符不重复 description 前缀（连跑 3 个 source 验证）
- [ ] script.endings_data 内引用的 character.name 全部 ∈ characters[].name 集合（cross_artifact 扩展查）
- [ ] character.starting_inventory / description 中提到的 name 全部 ∈ canonical registry
- [ ] strict IP world：must_have_characters 100% 就位 + 自创 NPC 触碰 forbidden_name_patterns 数量 = 0
- [ ] semantic_review 在已知"凶手身份冲突"测试样本上正确报 `villain_mismatch`
- [ ] playable 数量 ∈ [3, 10]，且任意两人 viewpoint_signature 不接近
- [ ] character.personality 不含抢权倾向用词（critic 不报 warning）

### 13.2 质量验收（对比）

| 维度 | baseline | 目标 |
|---|---|---|
| world name 是 description 前缀 case 占比 | ~30%（dogfood 跑过 7 个 / 23 个）| ≤ 10% |
| Tier1 fidelity 子项（IP world，strict）| 3.5 平均 | ≥ 4.2 |
| script 发布前 cross_artifact 异常率 | 当前低（schema-only 拦不住语义）| 不变（critic 已拦） |
| Tier1 总分（含 IP world）| 4.2 (5 sessions 估)| ≥ 4.4 |
| 跨阶段 name drift 实例（人工 audit）| 平均 1-2 处 / world | ≤ 0.3 处 / world |
| character.personality 抢权词频次 | 平均 2-3 个 character / world | ≤ 1 个 character / world |

### 13.3 性能 / 稳定性验收

- [ ] 单 world gen 总成本 ≤ $2，总时长 ≤ 20min
- [ ] 单 script gen 总成本 ≤ $0.40，总时长 ≤ 11min
- [ ] 4 个 feature flag 全 False 时 pipeline 行为 = 当前（回归）
- [ ] 跑 1 个 3-source batch（含 1 IP + 2 原创）全绿（critic 不出 error 级 warning）

---

## 14. 不在范围（防 scope 蔓延）

| 不做 | 理由 |
|---|---|
| critic gate v2 整体结构化重写 | 等本 spec 跑数据再决定 |
| 持久化 research / IP pack 缓存 | 一人 admin 用量不到痛点 |
| 生成任务可中断（cancel endpoint）| BUGS #17 同期 spec |
| 任务 reaper / zombie 配额修复 | BUGS #17 同期 spec |
| LLM 全局 throttle | BUGS #20 同期 spec |
| Admin 创世前端 UI 改动 | 只移除 loose 选项一处，spec 不专列 |
| Frontend 主体改动 | 不需要 |
| 重新生成图片 UI | 已有 placeholder，admin 通过编辑触发，UX 改善单独 |
| LLM 化 character_roster 选择 | 当前 brief + LLM batch 已足；本 spec 不动 roster 生成逻辑 |

---

## 15. Open Questions

| 项 | 待决 |
|---|---|
| fixture 实验 anchors 写不出来时 fallback dict 维护成本 | 预定义 5-10 个高频 IP 字典是否值得？长尾 IP 怎么办？ |
| semantic_review 在 100% 原创 world 上 ROI | 没 IP 也没"凶手身份"目标时是否跑？倾向跑（events↔endings 还是有自洽性需求）|
| canonical name registry 对 free 模式的扩展 | free 模式 NPC 是 runtime 动态生成的，是否也需要 registry？ |
| 长尾 IP（如冷门小说）的 inviolable anchors 来源 | LLM 不熟悉 → anchors 空 → fallback 到无约束，等于回到当前；这是预期的渐进 |
| name_critic 的 IP 标识检测 | "选了狄仁杰 IP 但 name 叫'暗夜疑云'" 这种 case 算不算合格？倾向 warn 不 reject（创作自由）|

---

## Appendix A — 关键文件改动清单

详细行级改动放到 plan，这里给文件层面 overview。

### 新增（4 文件）

- `backend/services/name_critic.py`
- `backend/services/canonical_name_registry.py`
- `backend/services/semantic_review_service.py`
- `backend/services/playable_selector.py`

### 改写（8 文件）

- `backend/schemas/ip_knowledge_pack.py` — schema 加 2 字段
- `backend/services/ip_research_pipeline.py` — 2 个 system prompt 改 + 2 个 extract 函数解析
- `backend/services/world_creator_agent_v2.py` — 6 处 hookpoint
- `backend/services/character_roster_builder.py` — prompt 加 3 块约束
- `backend/services/world_critic_service.py` — heavy_critic_characters / heavy_critic_playable 各加 1 维度
- `backend/services/cross_artifact_validator.py` — 扩展 3 类 check
- `backend/api/admin.py` 前端创世入口 — 移除 loose 下拉项（小改）
- `backend/config.py` — 加 4 个 feature flag

### 测试（建议新增）

- `backend/tests/test_name_critic.py` — 5 不合格 case + suggested_name 兜底
- `backend/tests/test_canonical_name_registry.py` — freeze + drift detection
- `backend/tests/test_semantic_review_service.py` — villain_mismatch / causal_break fixture
- `backend/tests/test_playable_selector.py` — viewpoint dedup / hard cap
- `backend/tests/test_ip_anchor_schema.py` — schema 字段 + 验证
- `backend/tests/test_extended_cross_artifact.py` — 3 类新 check

---

## Appendix B — 决策对照表

| 设计选择 | 选了什么 | 拒绝了什么 | 理由 |
|---|---|---|---|
| fidelity 档位 | strict + none | 保留 loose | loose 是 #23 根因；"参考但允许改"既不严肃也不自由 |
| name 治理范围 | canonical registry + critic + cross_artifact 三层 | 只加 name_critic | name drift 跨多阶段；单层挡不住 |
| IP plot anchors 来源 | LLM 提取（fixture 验证后）/ fallback 预定义 dict | 完全手工 dict | LLM 能 cover 长尾 IP；dict 维护成本 |
| anchors 触达点 | pack schema + 5 个注入点 | 单独 anchor validator 阶段 | 注入到 LLM 生成时比事后查更省 retry |
| semantic_review 位置 | critic 阶段 | publish 前 | 发布按钮的延迟敏感；critic 已是 LLM 多 pass 容器 |
| playable 选择 | LLM 选 + critic viewpoint dedup | 纯 Python heuristic / 完全自由 LLM | heuristic 漏视角差；完全自由没上限 |
| playable 个数 | 3 ≤ N ≤ 10，typical 4 | 单主角 / 固定 5 | 用户诉求"主角 + 有戏配角"区间宽，LLM 自决 |
| character 抢权治理 | gen 禁令 + critic warning（弱）| 不做 / 强阻塞 | LLM 可绕，强阻塞误杀；真正根治在 runtime v2 |
| critic 增强 vs 新阶段 | 增强（H1.5 / H2.5 扩展）| 新增 "name_check / semantic_check / playable_check" 阶段 | 不破坏 SSE phase 列表；admin UX 不变 |
| feature flag 数量 | 4 个独立切 | 单一总开关 | 定位回归 / 分批 rollout |
| 灰度策略 | 4 步 rollout，每步 1 source 验证 | 一次全切 / N 周 A/B | 一人 admin，4 步够 |

---

**End of spec.** B 章 §6.3 待 fixture 实验结果填入。
