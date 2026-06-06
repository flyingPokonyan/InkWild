# Cover Image Prompt Redesign — 2026-05-19

> 把世界 / 剧本 / 角色 / 结局封面图的生成范式从**密集中英 DP-grammar prompt（针对 Seedream 词袋型模型优化）**切到**极简自然语言 + IP 视觉 DNA 注入（针对 gpt-image-2 语义模型优化）**。
>
> 新 prompt ≈ 80–230 字；当前 ≈ 1100+ 字。生成质量从「AI 风光摄影 / 物理描述」跃迁到「production-grade 电影海报」。
>
> 验证截至 2026-05-19，22 张测试图覆盖 4 个跨题材真实 IP，全部通过。本文档既是 spec 也是 implementation plan。

---

## 1. 为什么要重构

### 1.1 现状诊断

`services/visual_brief.py` + `services/image_prompt_builder.py` 当前的生成链路：

```
世界元数据 + 角色（剥掉 secret）
  ↓ brief LLM call（_WORLD_BRIEF_SYSTEM）
WorldVisualBrief(anchor_location, key_prop, weather,
                 dominant_materials, palette, lighting_signature,
                 camera_grammar, series_signature_line, characters{…})
  ↓ build_world_still_prompt
1100+ 字 dense Chinese-English mixed prompt：
  "主体：xxx，置于画面正中、占据视觉重心。场景：xxx。
   天候：xxx。21:9 电影宽幅 establishing shot；
   三层景深——前景近景物、中景主体清晰落焦、远景融入大气透视。
   光线：xxx。深阴影保留 #0a0d12 不抬灰。色板严格遵循：xxx；
   明显去饱和、无任何饱和原色。材质真实可触：xxx。
   摄影语言：xxx。对标 Roger Deakins、Gregory Crewdson…"
  ↓ gpt-image-2
输出：高质量 establishing shot 风光摄影
```

**问题**：

1. **prompt 本身是为 Seedream 设计的** —— 历史上 `seedream.py` 这个文件名是真实的 Seedream（字节即梦），后来切到 gpt-image-2 但 prompt 风格未跟着切。Seedream 是词袋型，关键词靠前权重高；gpt-image-2 是语义模型，理解自然语言比堆砌关键词强百倍。继续用 Seedream-style 等于反优化。
2. **prompt 全在描述物理世界**（材质 / 光线 / 调色 / 摄影机），完全没有描述**故事**。结果是模型生成「精致的风光摄影」而非「电影海报」——封面图不传达"这是关于谁的什么故事"。
3. **brief LLM 把 secret 显式 strip**：`_build_world_brief_user_message` 注释明确写了"Crucially: secret is stripped at the boundary"。设计意图是防剧透，但副作用是 brief LLM 完全看不到故事的中央张力，只能基于"世界是什么样子的"产生 brief。

### 1.2 实测对比

- **P0 baseline** (现有 dense brief，1161 字)：黄昏穿过玉米地的铁轨，远景钢厂剪影。**无人、纯风光**。
- **P2 charged moment** (247 字自然语言)：玉米地边土路上一个穿蓝工装、戴鸭舌帽的男人背影，远处绿皮火车驶过。**有故事张力**。

P0 → P2 的差距不是 prompt 写得好不好，是**范式不同**：P0 在告诉模型「怎么拍」，P2 在告诉模型「画什么、为了什么」。

### 1.3 重构核心

切到「**IP/世界名 + 题材标签 + typography hint + 极简约束**」范式。让 gpt-image-2 调用自己训练集里的 IP 视觉记忆 + 海报设计本能，我们只做四件事：

1. **Hijack 标题文字** —— 模型想写"漫长的季节"，我们让它写"回来的人"
2. **Hijack 人脸** —— 模型想画范伟，我们告诉它"虚构角色不要像现实演员"
3. **禁止侵权元素** —— Logo / 品牌 / 奖项 / 发行日期不允许出现
4. **注入 typography 偏好** —— 古装毛笔字 / 民国衬线 / 现代无衬线 ……由题材派生

---

## 2. 验证

### 2.1 测试图汇总

22 张测试图保存在 `test_outputs/`（gitignore，本地参考）。完整路径：`/Users/jie/Desktop/code/pokonyan/inkwild/test_outputs/`。

| 阶段 | 编号 | IP | 测试假设 | 结果 |
|---|---|---|---|---|
| **基线对比** | P0 | 漫长的季节 | 现有 dense brief 是 baseline | ❌ 纯风光，无人，失败 |
|  | P1 | 漫长的季节 | 398 字自然语言导演 brief | ✅ 有主角背影 + 故事张力 |
|  | P2 | 漫长的季节 | 247 字 charged moment | ✅ 更克制更图形化 |
|  | P3a/b | 漫长的季节 | IP 视觉调性 cue | ✅ 工业 DNA 显著加强 |
| **Minimal 极限** | M1-M6 | 漫长的季节 | "为《xxx》生成 xx 海报" 极简 prompt | ⚠️ 模型直接复刻官方海报，含真名人脸/logo/标题，不可用 |
| **Hijack 架构** | T1-T4 | 「回来的人」(借《漫长的季节》视觉) | world_name 替换 + 人脸虚构 | ✅ 4/4 通过，保留官方美学但合法 |
| **风格框架 + 字体** | Z1a/b | 逐玉 | "《逐玉》风格" 新框架 | ✅ Z1b 略胜，统一用 |
|  | Z2-Z4 | 逐玉 | role_hint 4 维结构化 | ⚠️ Z3 无 hint 把女角色画成男武将（失败但揭示问题） |
|  | V1-V3 | 逐玉 | reference_anchor + name text + typography hint | ✅ 4 维 + ref 完美区分 3 个角色 |
| **跨题材验证** | W series | 漫长的季节 / 三体 / 风声 / 逐玉 | 同一架构 4 题材 17 张 full set | ✅ 17/17 全通过 |

### 2.2 关键发现

1. **指令越多，模型越平庸**。T3/T4 加了 story_pitch + character_descriptor + poster_type，反而比 T1 minimal prompt 出图差。"自由发挥"是 gpt-image-2 的强项，我们越约束越损失。
2. **Reference anchor + name 比"4 维 hint"更高效**。Z3 不带 hint 性别都错（"樊长玉"被画成男武将）；V2 带 reference "《逐玉》里的屠户女主"立刻正确。known IP 走 ref 路径，原创世界 fallback 走 4 维。
3. **Typography hint 跨题材稳定**。毛笔书法 / 民国衬线 / 现代无衬线 在 4 个世界各得其所，模型完全 honor。
4. **Ending card 是新发现的有效维度**。W series 4 个结局图（真相大白 / 威慑纪元 / 风声传出 / 家国并肩）全部"剧透情感不剧透细节"，仪式感强。值得作为新图片类型纳入。
5. **Content policy 边界**：直接说"对标 xxx 官方海报 + 名导演 + 名摄影师"三连会被拒（P3 empty result）；点 IP 名 + 视觉调性 + 不点活人就放行（P3a/b）。

---

## 3. 图片产物清单（5 类，原 4 类 + 新增 ending card）

| 编号 | 类别 | DB 字段 | 比例 | 当前状态 | 重构后 |
|---|---|---|---|---|---|
| 1 | World hero | `worlds.hero_image` | 21:9（1792×768）| dense prompt | 新模板，**比例保持 21:9** |
| 2 | World cover | `worlds.cover_image` | 3:2（1152×768）| 服务端从 hero 中心裁切 | **保持现有 server-crop 逻辑** |
| 3 | Script cover | `scripts.cover_image` | 3:2（1536×1024）| dense prompt | 新模板，直接生成 3:2 |
| 4 | Character portrait | `world_characters.avatar` | 2:3（1024×1536）| dense prompt + 物理 brief | 新模板（reference_anchor + 4 维 fallback + name text） |
| 5 | Ending card 🆕 | `endings.cover_image`（新字段） | 3:2（1536×1024） | 不存在 | 新模板，直接生成 3:2 |

### Schema 变更

- **`endings` 表加 `cover_image: str` 字段** —— Alembic migration
- **`world_characters` 表加 `gender: str` 字段** —— Alembic migration（仅原创世界角色 portrait 4 维 descriptor 需要；已知 IP 角色走 reference_anchor 不依赖此字段）
- **比例不变**：hero 21:9 → server-crop 3:2 cover 这套现有 pipeline 保留。hero 在大屏 banner 上的清晰度（21:9 native 1792×768）和 cover 在浏览墙卡片上的尺寸（3:2 裁切 1152×768，显示约 400px 宽足够）都已经合适，不要为简化而牺牲质量

### 关于"系列一致性"的取舍

旧 `WorldVisualBrief` 有 `series_signature_line` 字段，目的是让同一世界的 hero / cover / script / portrait 看起来像同一摄影师拍下的同一系列。

新范式没显式强制 series anchor。但 W series 实测 4 个世界各自 5 张图天然一致（typography + palette + material 同源由 world_name + typography_hint 触发）。我们**不再 enforce series anchor**，相信 gpt-image-2 的 contextual coherence。如果后期发现单体世界图数变多时出现风格漂移，再考虑加 lightweight anchor。

---

## 4. 数据 schema

### 4.1 services/cover_brief.py

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class CoverBrief:
    """统一驱动 world hero/cover、script cover、ending card 的 brief。"""
    world_name: str                # 世界名（中文）
    world_name_english: str        # 英文/拼音；辅助 LLM 出
    genre_tag: str                 # 古装权谋爱情 / 现代东北悬疑 / 硬科幻 / 民国谍战 / ...
    typography_hint: str           # 标题字体风格（见 §6.1 派生表）
    ip_mode: Literal["known_ip_exact", "hybrid", "original"]
    ip_name: str | None            # hybrid 时填；known_ip_exact 同 world_name；original 为 None


@dataclass
class CharacterCoverBrief:
    """驱动 character portrait。"""
    name: str
    name_english: str              # 拼音；辅助 LLM 出
    # reference_anchor 存在时替代 4 维 descriptor。仅 ip_mode != "original" 时可填。
    reference_anchor: str | None   # e.g. "《逐玉》里的武安侯，化名言正"
    # 4 维 fallback —— reference_anchor 为空时必填：
    gender: Literal["男", "女"]
    age_band: Literal["少年", "少女", "青年", "中年", "老年"]
    role_class: str                # 武将 / 文官 / 屠户 / 宰相 / 江湖客 / 工人 / 科学家 / ...
    mood_anchor: str               # 沉默隐忍 / 铁血威严 / 风尘仆仆 / ...


@dataclass
class EndingCoverBrief:
    """驱动 ending card。"""
    title: str                     # e.g. "真相大白"
    title_english: str
    description: str               # 故事到这一结局的状态（含剧透——结局本身就是剧透）
```

### 4.2 worlds / scripts / endings 模型变更

- `endings.cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)` 新增
- `worlds.visual_brief` JSONB 改存 `CoverBrief.dict()`；旧 `WorldVisualBrief` 字段不再写入但**保留兼容性**（旧数据读取失败时降级到默认）
- `scripts.visual_brief` 同样改存

---

## 5. Prompt 模板

> 所有模板示例在 `backend/scripts/exp_cover_prompts_multiworld.py` 的 builders 里有可执行版本（已用 17 张图验证）。下面是规范化版本。

### 5.1 World hero (3:2)

**known_ip_exact**（world_name 就是 IP 名，如 "逐玉"/"漫长的季节"）：

```
生成一张《{world_name}》风格的电影海报。
若海报包含标题文字，使用「{world_name}」(中文) + {world_name_english} (英文)，字体风格：{typography_hint}。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
21:9 电影宽幅。
```

**hybrid**（world_name 借用 IP 视觉，如 "回来的人" 借《漫长的季节》视觉）：

```
为一个叫《{world_name}》的虚构{genre_tag}剧生成一张电影海报，视觉调性参照《{ip_name}》。
若海报包含标题文字，使用「{world_name}」(中文) + {world_name_english} (英文)，字体风格：{typography_hint}。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
21:9 电影宽幅。
```

**original**：

```
为一个叫《{world_name}》的虚构{genre_tag}剧生成一张电影海报。
若海报包含标题文字，使用「{world_name}」(中文) + {world_name_english} (英文)，字体风格：{typography_hint}。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
21:9 电影宽幅。
```

> hero 出 21:9（1792×768）后，由现有 `image_cropper.py` server-crop 中心 3:2 区域得 cover（1152×768）。hero 直接当详情页 banner，cover 用于浏览墙卡片。
>
> **测试图档案的 21:9 验证**：测试时 W series 用了 3:2，未直接验证 21:9 模板。模板逻辑一致，21:9 给模型更多横向空间做 sweeping 场景，预期不会退化；如 Phase 2 实施后第一张 hero 出现问题，回退到 3:2 + 加 server-crop logic 改造（生成 3:2 直接当 hero，不做 crop）。

### 5.2 Script cover (3:2)

```
为《{world_name}》中的剧情线《{script_title}》生成一张《{world_name}》风格的电影海报。
若海报包含标题文字，使用「{script_title}」(中文) + {script_title_english} (英文)，字体风格：{typography_hint}。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
3:2 横版。
```

（剧本依附世界，不分 known_ip / hybrid / original —— 世界已经定调了，剧本只是它的一条线。）

### 5.3 Character portrait (2:3)

```
为《{world_name}》中的角色「{name}」（{character_descriptor}）生成一张《{world_name}》风格的 2:3 人物海报。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
眼线落在画面上三分位附近（前端将自动裁出圆形头像）。
画面下方约 1/6 高度的区域居中渲染文字「{name}」，字体风格：{typography_hint}，文字宽度约占画面宽度 1/4–1/3，不要遮挡角色面部。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
2:3 竖版。
```

`{character_descriptor}` 派生：
- `reference_anchor` 存在：`{reference_anchor}；{mood_anchor}`
- `reference_anchor` 为空：`{gender}性，{age_band}，{role_class}，{mood_anchor}`

### 5.4 Ending card (3:2)

```
为《{world_name}》生成一张「{ending_title}」结局画面卡。
故事到这里的状态：{ending_description}
若画面包含标题文字，使用「{ending_title}」，字体风格：{typography_hint}。
人物是虚构角色，不要与任何现实演员、明星、公众人物相似。
无血腥暴力直白展示，可象征性表达。
不要任何品牌 logo、奖项标志、发行日期、电视台署名。
3:2 横版。
```

---

## 6. 派生规则

### 6.1 typography_hint × genre 默认映射

每个 typography_hint 显式包含 **charset 偏好**（简体 / 繁体），避免模型自己 lookup 旧 IP 时把现代内地世界画成繁体（如 W series 风声 hero 模型自发用繁体「風聲」是 bug，需要 typography_hint 主动指明 charset）。

| 题材 / 时代 | typography_hint |
|---|---|
| 古装 / 武侠 / 仙侠 / 玄幻 | 毛笔书法（金色或墨黑，传统印章式，**简体中文**） |
| 民国 / 旧上海 / 谍战 | 民国衬线竖排（暗红或墨黑，铅字感，**繁体中文**——呼应年代） |
| 现代刑侦 / 都市悬疑 | 黑体无衬线（白 / 黑 / 暗红，**简体中文**） |
| 现代东北 / 90 年代时代剧 | 毛笔书法（暖黄或暗金，**简体中文**） |
| 科幻 / 赛博 | 现代无衬线（冷青或暗银，未来感，**简体中文**） |
| 武侠 / 江湖（独立游戏感） | 行书 / 隶书（墨黑，**简体中文**） |
| 默认 fallback | 黑体无衬线（**简体中文**） |

**注意**：
- charset 嵌入 typography_hint 里 → 通过 prompt 模板自然传给模型，不需要在 prompt 末尾额外加约束子句
- admin 可在世界编辑器 override 整个 typography_hint —— 比如某个特殊民国世界想要现代简体设计（如《漫长的季节》），admin 改成"毛笔书法（暖黄，简体中文）"

### 6.2 ip_mode 派生（从现有 IPRecognition）

```python
def derive_ip_mode(
    world_name: str,
    recognition: IPRecognition | None,
) -> tuple[Literal["known_ip_exact", "hybrid", "original"], str | None]:
    if recognition is None or recognition.kind == "original":
        return "original", None

    if recognition.kind == "known_ip" and recognition.confidence >= 0.85:
        if world_name.strip() == (recognition.ip_name or "").strip():
            return "known_ip_exact", world_name
        return "hybrid", recognition.ip_name

    if recognition.kind == "hybrid":
        return "hybrid", recognition.ip_name

    return "original", None
```

### 6.3 character reference_anchor 派生

- `ip_mode in ("known_ip_exact", "hybrid")` + 角色在 `IPKnowledgePack.characters` 中：直接取 `role_in_story` 字段加上 IP 前缀。e.g. `"《逐玉》里的武安侯（化名言正）"`
- `ip_mode == "original"` 或角色不在 IP pack 中：reference_anchor = None，必须填 4 维 descriptor

### 6.4 4 维 descriptor 派生（仅原创世界）

- **gender**：当前 `world_characters` schema 没有 gender 字段，需要：
  - **方案 A**：加字段 `world_characters.gender: str`（admin 编辑器加 dropdown）—— 推荐，最稳
  - **方案 B**：辅助 LLM 从 personality 推断 —— 兜底，但有时不准
- **age_band / role_class / mood_anchor**：辅助 LLM 一次性从 character.personality + character.description 抽 3 个短词

辅助 LLM 用现有 `world_brief_summarizer` slot 或新建 `cover_brief_helper` slot（推荐新建，bind 到最便宜的模型——haiku-4-5 或 deepseek-v4-flash）。

### 6.5 world_name_english / script_title_english / name_english 派生

辅助 LLM 一次性出。规则：
- 已知 IP 用其官方英文名（如《逐玉》→ "Pursuit of Jade"）
- 未知 IP / 原创：拼音 fallback（如「无人记得的冬」→ "The Forgotten Winter" 或 "Wuren Jide De Dong"，由 LLM 判断哪个更顺）

---

## 7. 实施路线

### Phase 1 — 新建 cover_brief 模块（无破坏改动）

**文件**：
- 新建 `backend/services/cover_brief.py` —— schemas + 4 个 builder + typography 派生表
- 新建 `backend/services/cover_brief_helper.py` —— 辅助 LLM 出英文名 + 4 维 descriptor 的封装

**Migration**：
- `endings.cover_image` 字段新增 Alembic migration

**测试**：
- `backend/tests/test_cover_brief.py` —— 每个 builder 给 fixture 输入 → 期望 prompt 字符串
- 覆盖 3 个 ip_mode × 4 个图片类型 = 12 个核心 case

**预期工作量**：1 天

### Phase 2 — 切换 image_prompt_builder 到新模板

**文件**：
- 改 `backend/services/image_prompt_builder.py`：删除 `build_world_still_prompt` / `build_script_poster_prompt` / `build_character_portrait_prompt`；改写为薄 wrapper 调 `cover_brief.build_*_prompt`

**测试**：
- 现有测试用 fixture 仍能通过（接口签名兼容）

**预期工作量**：0.5 天

### Phase 3 — 改造 world_creator_agent_v2 调用链

**文件**：
- `backend/services/world_creator_agent_v2.py`：
  - `_run_visual_brief_stage`：删除现有 `generate_world_visual_brief` LLM call；改成调 `cover_brief_helper.derive_world_cover_brief(world_data, ip_recognition)` 静态派生（仅辅助 LLM 出英文名 + 原创世界角色 4 维 descriptor）
  - `_run_script_visual_brief_stage`：同样
  - Stage I (images)：**hero 比例保留 21:9 + server-crop 3:2 cover 现有逻辑不变**；只把 hero prompt 文本换成新模板；**新增 ending card 生成循环**——对每个 ending 出一张 3:2 图
- `backend/services/visual_brief.py`：**整个文件可以删除**——不再保留 `WorldVisualBrief` / `ScriptVisualBrief` dataclass；新 pipeline 不持久化 brief，每次生成时 derive on-the-fly
- DB migration：`worlds.visual_brief` / `scripts.visual_brief` JSONB 字段 **drop**（Alembic migration）

**测试**：
- Smoke test：跑一遍 world creation pipeline，看 5 类图都生成

**预期工作量**：1.5 天

### Phase 4 — 前端 ending card 展示

**文件**：
- 前端：游戏结束页面 (`frontend/app/play/[id]/...` 或类似) 新增 ending card 展示——根据当前结局类型，显示对应 `endings.cover_image`；图为 NULL 时 fallback 到纯文字
- 前端：admin workshop 预览页加入 ending card 列表（每个 ending 一张卡，admin 可单独"重新生成"某个 ending card）
- 前端：hero banner / cover 比例无需调整（21:9 + 3:2 保持现状）

**预期工作量**：1 天

### Phase 5 — 存量回炉

走 `docs/design/cover-art-spec.md` §10 已经定义的"redo"流程：

- admin 后台加一键"重新生成全部图片"按钮
- 按世界遍历：每个世界先在 admin preview 看新图，OK 再 publish 覆盖
- 灰度：先 5 个世界，看用户反馈，再批量

**预期工作量**：0.5 天（按钮 + 批处理），实际跑图 admin 自己点

### Phase 6 — 文档与 spec 更新

**文件**：
- `docs/design/cover-art-spec.md` v1.2 → v2.0：
  - §2 风格定位：删除"电影摄影写实 · 戏剧光影"独家锁定，改成"由 typography_hint × IP 视觉 DNA 自然涌现"
  - §3 技术规格：hero 比例 21:9 → 3:2；删除独立 cover 出图流程
  - §4 构图规则：放宽——不再 enforce 主体居中、留白带等硬规则；这些由模型自决
  - §5 光照与色调：advisory 化——typography_hint + IP 派生足以保证一致性
  - §7 AI 出图工作流：**全部重写**，对齐本 spec
  - §10 存量回炉：保留，作为 Phase 5 的执行流程
- `docs/modules/world-creator.md`：
  - Stage I-pre 描述改：不再调 brief LLM，改静态派生
  - Stage I 描述改：5 类图（含 ending），统一 3:2 / 2:3 两种比例
- `docs/MIGRATION_NOTES.md`：记 breaking change（旧 `WorldVisualBrief` 字段废弃）

**预期工作量**：0.5 天

### 总计工作量

约 **5 天**单人工作，可拆分给 2 人并行（Phase 1+2 一组、Phase 3+4 一组）。Phase 5/6 串行收尾。

---

## 8. 决定（locked 2026-05-19）

| # | 决定 | 实施细节 |
|---|---|---|
| Q1 | **加 `world_characters.gender` 字段** | Alembic migration；admin 编辑器加 dropdown（男 / 女）；历史数据按已有 personality 文本人工/脚本回填一次 |
| Q2 | **新建 `cover_brief_helper` slot** | 绑 haiku-4-5 或 deepseek-v4-flash；每个世界一次调用出英文名 + 4 维 descriptor，token 量 ~300 |
| Q3 | **保留现有 dual-aspect pipeline** | hero 21:9（1792×768，prompt 改新模板）+ server-crop 中心 3:2 cover（1152×768）。不合并，不简化 server-crop |
| Q4 | **不加 `suppress_title` flag** | 沿用条件式子句"若海报包含标题文字..."。生产数据如果显示某场景必须无文字再补 |
| Q5 | **typography_hint 内嵌 charset** | 见 §6.1 表。简体为默认；民国/谍战 typography 内显式标注"繁体中文"；admin 可 override 整个 hint |
| Q6 | **Ending card 失败留 NULL** | gpt-image-2 retry 3 次后仍失败 → `endings.cover_image = NULL`；前端检测到 NULL fallback 纯文字结局展示，不显示 placeholder |
| Q7 | **直接 drop visual_brief 字段** | Alembic migration 删 `worlds.visual_brief` / `scripts.visual_brief`；新 pipeline 不持久化 brief，每次生成时 on-the-fly derive |

---

## 9. 风险与监测

### 9.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 跨世界 series-coherence 弱化 | 中 | 视觉风格不一致显得乱 | W series 4 个世界各 5 张图天然一致。监测：QA 抽查前 20 个 publish 后的世界。如发现漂移，加 lightweight `series_anchor_phrase` 字段 |
| 官方 IP marketing 元素泄露 | 低-中 | 出现可识别 tagline / actor / brand | T1-T4 + W series 22 张 0 案例。但小概率事件。监测：admin publish 前必须 preview；爬虫式 OCR 文字检测 + 已知 IP tagline 黑名单 |
| 小众/陌生 IP fallback | 中 | "《xxx》风格" 在模型没见过此 IP 时退化 generic | 检测办法：可以在 IP recognition 阶段加 confidence 阈值（< 0.85 → 走 hybrid 改写为 "类似《similar_ip》的视觉调性" 或回退到 original） |
| Content policy refusal | 中 | 某些结局/角色 prompt 被 gpt-image-2 拒（empty result） | 现有 retry + placeholder fallback 已处理。监测：跟踪 placeholder rate；超过 5% 触发 review |
| Typography hint 不一致 | 低 | 某些 hint 文本模型不识别 | typography 派生表只用模型擅长的描述词（毛笔/衬线/无衬线/行书）。如果发现某 hint 失效，从派生表里删除 |

### 9.2 上线后监测指标

- **placeholder rate**：图片生成失败率，按 5 类分别监测，目标 < 3%
- **content_policy_refusal rate**：empty result 比例，目标 < 2%
- **admin preview rework rate**：admin 在 publish 前点 "重新生成" 的比例，目标 < 30%
- **复刻泄露率**：QA 每周抽查 10 张生成图，看是否含真实 IP 营销元素（tagline / actor / logo / brand / 奖项 / 发行日期），目标 0%

---

## 10. 测试图档案

完整 22 张测试图在 `test_outputs/`（本地 gitignore）：

```
# Phase 1: dense vs natural language 对比
P0_baseline.png                   现有 dense brief (1161 chars)
P1_director_brief.png             自然语言导演 brief (398 chars)
P2_charged_moment.png             charged moment (247 chars)
P3a_ip_named.png                  + IP cue (199 chars)
P3b_aesthetic_only.png            + 类型氛围 (232 chars)

# Phase 2: minimal "为《xxx》生成 xx 海报" 极限测试 → 暴露版权问题
M1_naked.png ... M6_english.png

# Phase 3: hijack 架构验证（虚构世界名「回来的人」借《漫长的季节》视觉）
T1_title_hijack.png               仅标题替换
T2_face_safety.png                + 人脸虚构
T3_with_story.png                 + 故事（不建议）
T4_character_poster.png           + 类型（不建议）

# Phase 4: 风格框架 + 字体 + 4 维 hint 验证（《逐玉》）
Z1a_old_framing.png               "为《逐玉》生成"
Z1b_style_framing.png             "《逐玉》风格"（推荐）
Z2_xie_zheng_with_hint.png        4 维 hint
Z3_fan_changyu_no_hint.png        无 hint → 失败，画成男武将
Z4_wei_yan_with_hint.png          但跟 Z2 视觉雷同

# Phase 5: reference_anchor + name text + typography 终极验证（《逐玉》）
V1_xie_zheng.png                  谢征（武安侯 ref）
V2_fan_changyu.png                樊长玉（屠户女 ref）
V3_wei_yan.png                    魏严（宰相 ref）

# Phase 6: 跨题材 17 张 full set
W_long_season_hero / script / portrait_王响 / portrait_沈墨 / ending
W_three_body_hero / script / portrait_罗辑 / portrait_叶文洁 / ending
W_message_hero / script / portrait_李宁玉 / portrait_顾晓梦 / ending
W_zhuyu_script / ending

# 参照
REFERENCE_official_wiki.jpg       《漫长的季节》维基官方海报缩略图
```

测试脚本可执行版本：

```
backend/scripts/exp_cover_prompts.py              Phase 1
backend/scripts/exp_cover_prompts_p3.py           Phase 1 retry
backend/scripts/exp_cover_prompts_minimal.py      Phase 2
backend/scripts/exp_cover_prompts_hijack.py       Phase 3
backend/scripts/exp_cover_prompts_zhuyu.py        Phase 4
backend/scripts/exp_cover_prompts_zhuyu_v2.py     Phase 5
backend/scripts/exp_cover_prompts_multiworld.py   Phase 6
```

这些脚本可以删除或保留作为 reproducibility 证据。建议保留并放到 `backend/scripts/experiments/`，加 README 说明只是 brainstorm 工件。

---

> **状态**：spec 完成；§8 的 7 个决定已 locked（2026-05-19）。可直接进入 Phase 1 实施。
