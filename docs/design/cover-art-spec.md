# InkWild · 封面/角色/结局图规范 v2.1
*Cover / Hero / Portrait / Ending — for ops, designers, content reviewers*

> **v2.1（2026-05-22）**：World cover 从"hero 中心裁切"改为**独立生成**——hero 和 cover 的构图诉求不同（21:9 全屏 cinematic vs 3:2 小尺寸卡片陈列），共享一张图会让其中一个吃亏。同时 hero/cover prompt 都加了**用途说明**（"全屏 hero" / "列表卡片陈列"），让模型推理出合适构图，不靠硬约束。Cover 不带 title_hint——列表卡片下方有 UI metadata 标题，画上再来一个会撞。Hero 保留 title_hint：UI 删了叠加的 h1（discover spotlight），让模型决定的"画面级标题"成为终极视觉。
>
> **v2.0（2026-05-19）**：与"封面图生成 pipeline 重构"同步。视觉质量主要由代码（`services/cover_brief.py` + gpt-image-2）保证，本文档收缩到 **产物清单 + 验收红线 + 回炉流程**。设计细则（构图、调色、字体）的"源头规则"在 `docs/plans/cover-image-prompt-redesign-2026-05.md`，本文档不复制。
>
> **v1.2 → v2.0 关键变更**：
> - § 风格、构图、光照、调色、prompt 框架 **整章删除**——下沉到 prompt builder 的派生规则 / typography_hint 表
> - 加入 **第 5 类图：ending card**（3:2）
> - 验收红线收紧到 **法律 / 安全 / spec 不可侵入项** 三条

---

## 1. 5 类图片产物

| 编号 | 类别 | DB 字段 | 比例 | 来源 |
|---|---|---|---|---|
| 1 | World hero | `worlds.hero_image` | **21:9**（1792×768）| 生成 |
| 2 | World cover | `worlds.cover_image` | **3:2**（1152×768）| 生成（fallback: hero 中心裁切） |
| 3 | Script cover | `scripts.cover_image` | **3:2**（1536×1024）| 生成 |
| 4 | Character portrait | `world_characters.avatar` | **2:3**（1024×1536）| 生成 |
| 5 | Ending card 🆕 | `endings.cover_image` | **3:2**（1536×1024）| 生成 |

所有生成图都走 `services/cover_brief.py` 的 4 个 prompt builder + gpt-image-2 实现。代码层面已经强制：face safety、典型 logo/brand/award/release-date negative、typography hint。

## 2. 验收硬红线（任一不达标 = 退回重生成）

### 2.1 法律 / 安全
- ❌ 真实可识别的明星 / 网红 / 公众人物面孔（直接生成 fictional faces 是 prompt 默认行为，但 QA 仍要复核）
- ❌ 真实存在的品牌 logo / 商标
- ❌ 真实奖项标志（戛纳、奥斯卡、金鸡 laurel）
- ❌ 伪造的发行日期 / 电视台署名 / 平台 watermark
- ❌ 现实政治符号、国旗、党徽
- ❌ 未成年人面部清晰特写（character portrait 涉及未成年角色时改用背身 / 侧脸 / 局部）
- ❌ 露点 / 性暗示 / 露骨血腥

### 2.2 Spec 不可侵入
- ❌ Character portrait 上有任何文字、标题、英文名（character name 文字只允许在 **画面下方 1/6 高度区域**，前端圆形 avatar crop 不会侵入；其他位置出现文字 = 退回）
- ❌ Hero / cover / script cover 上出现可识别的"原 IP marketing 元素"（原 tagline 直引、原标题 logo 字形原样复制）—— 我们做的是"新作品"，不是"复刻官方海报"

### 2.3 技术
- ❌ 尺寸 / 比例不符（自动）
- ❌ sRGB 之外的色彩空间
- ❌ AVIF/WebP/JPG 任一缺失（前端 fallback 需要齐）

## 3. 内容禁区（涉及暴力 / 死亡题材的 ending card 用符号化处理）

涉及死亡 / 牺牲 / 案件场面：远景、剪影、道具暗示、光线隐喻。**不允许**：断肢、血池、内脏、明确尸体特写。

如生成结果触及上述：cover_brief.py 已在 prompt 加 `"无血腥暴力直白展示，可象征性表达"`。复审仍发现 → 标 `cover_status: redo` 重生成（一般再跑一次模型会换种象征手法）。

## 4. 文件格式

| 格式 | 质量 | 用途 | 浏览器覆盖 |
|---|---|---|---|
| **AVIF** | 75 | 首选 | Chrome 85+ / Safari 16+ / Firefox 93+（>95% 用户） |
| **WebP** | 80 | fallback A | 几乎所有现代浏览器 |
| **JPG**  | 85 | fallback B | 老设备兜底 |

体积上限：

| 用途 | AVIF/WebP | JPG |
|---|---|---|
| 3:2 cover / script cover / ending card | < 200 KB | < 400 KB |
| 21:9 hero | < 300 KB | < 600 KB |
| 2:3 character portrait | < 200 KB | < 400 KB |

`services/image_storage.py` 已处理多格式输出。

## 5. 命名约定

```
{world-id}-hero.{avif,webp,jpg}              # 21:9
{world-id}-cover.{avif,webp,jpg}             # 3:2，server-crop 自 hero
{script-id}-cover.{avif,webp,jpg}            # 3:2
{character-id}-portrait.{avif,webp,jpg}      # 2:3
{ending-id}-card.{avif,webp,jpg}             # 3:2（新）
```

## 6. 存量回炉

**触发条件**：
- 任一现存世界的图不符 §2 红线
- 现存图是 v1.2 老 pipeline 产物（dense DP-grammar prompt）—— 视觉对标已经偏离，建议回炉

**流程**：
1. Admin 后台进入世界编辑器
2. 点 "重新生成全部图片"（Phase 5 待实现，当前可通过 admin draft 编辑 → 重新走生成 pipeline 实现）
3. Preview 预览 5 类新图
4. 通过 → publish 覆盖；不通过 → 调整 typography_hint override 或角色 gender 字段后重跑

**过渡期前端表现**：
- 老世界的 v1.2 图仍展示（不至于 broken），但 admin 后台 `cover_status` 字段（v1.2 引入）显示 "v1_legacy"
- 新生成的图 `cover_status: v2_approved`
- Discover 卡片优先排 `v2_approved` 的世界（少量算法影响）

## 7. 不在本文档（前往 plan 看）

以下内容**不在本规范**，由代码和 plan 共同维护：

- typography_hint × genre 派生表 → `services/cover_brief.py:derive_typography_hint` + `docs/plans/cover-image-prompt-redesign-2026-05.md` §6.1
- prompt 模板 → `services/cover_brief.py` 的 4 个 build_* 函数 + plan §5
- IP-mode 判定逻辑 → `services/cover_brief.py:derive_ip_mode` + plan §6.2
- 角色 reference_anchor 派生 → `services/cover_brief.py:derive_character_reference_anchor` + plan §6.3
- LLM helper 派生英文名 / 4-dim descriptor → `services/cover_brief_helper.py` + plan §6.4-6.5

## 8. 设计师 / 美术介入点

新 pipeline 几乎全自动。设计师 / 美术只在以下点介入：

| 介入点 | 操作 |
|---|---|
| Typography 想要特殊字体 | admin 后台 override `worlds.typography_hint`（字段在 schema 但 UI 待补） |
| 某个世界生成质量低 | 用 admin 编辑器调 `genre` / `era` 让 typography_hint 派生更准；或 admin 显式填写 `world_characters.gender` |
| Ending card 涉及死亡题材生成失败 | `endings.cover_image` 留 NULL，前端 fallback 纯文字展示——这是 spec 接受的状态，不强行要图 |
| 跨世界视觉一致性偏移 | （rare）找运营 / 算法层面调整，不在本规范处理 |

---

> 维护人：[设计负责人] + [后端负责人]
> 最后更新：2026-05-19 v2.0
> 配套文档：
> - `docs/plans/cover-image-prompt-redesign-2026-05.md`（实施 spec + 验证证据）
> - `frontend/AGENTS.md`（前端视觉参考，与本文不冲突；旧 visual-principles 已并入并归档到 `docs/_archive/`）
