# InkWild · 视觉原则 v2.3（最终版）
*Visual Principles — site-wide, single source of truth*

> 这一份**取代** v1 / v2 / v2.1 / v2.2。所有 PR review 对照这一份。
>
> 配套：`cover-art-spec.md`（封面规范）、`frontend-spec.md`（设计令牌的具体值）。
>
> **v2.2 → v2.3 变更摘要（2026-05-23 cinematic gold）**：
> - 主色板换皮：暖金 `#c9b48a` → **香槟金 `#dfc290`**（更亮、更暖、更电影质感）；
>   暗底 `#0a0a0c` → **`#08080a`**；主文本 `#f5f3ee` → **暖象牙 `#f5f2eb`**；danger `#b85c5c` → **暖珊瑚 `#ef8276``
> - **`--lv-accent-2` 从苔绿 #7fb091 改为银雾 #aeb4b8**（自由模式辅助色去绿化，避免与"成功态绿色"语义冲突；
>   `--lv-success` 仍保留独立绿色 #7fb091，用于状态反馈）
> - 全局 Navbar 被**移除**：所有页面用 `<ProductNav variant="transparent|solid" active="..." />`（桌面）+ `<BottomTabBar />`（移动），
>   layout.tsx 不再渲染统一顶栏；详见 §15.2
> - 主题颜色字段全站统一在 `globals.css :root` 唯一定义，**禁止 per-page override**；landing/discover/history/workshop 等主入口已迁完
> - 重构计划归档到 `docs/_archive/frontend-refactor-2026-05.md`，阶段 0–7 全部完成（含 PWA serwist + manifest）
>
> **v2.1 → v2.2 变更摘要**（保留备查）：
> - 字号阶梯 7 档 → **9 档**（加 `t-h3` 卡片标题 + `t-micro` 极小标记）
> - 字号全部 **clamp() 化**，废除 `@media (max-width: 768px)` 跳变
> - serif 字重 300/400 → 400/500（中文 serif 太细加粗）
> - caps 字间距 0.18em → 0.2em
> - 叙事正文 serif → sans（中文长段 sans 更舒适）
> - 基础设施层（next-intl / TanStack Query / Framer Motion / shadcn 选择性 / Storybook）
> - 移动端：navbar → 底部 tab bar；play 页 → 单栏+抽屉
>
> **v2 → v2.1 变更摘要**（保留备查）：
> - 正文字号 14 → 15；新增 `t-narrative`
> - 长正文行高 1.7 → 1.6
> - 圆角加 `--lv-r-input` 10px 例外
> - 文案替换原则改成"删修饰词，保情绪"

---

## 0. 总纲

### 视觉对标（全站统一）

**Netflix / Apple TV+ / Letterboxd 这一脉。**

具体气质坐标：
- **像 Netflix**：暗黑底、靠封面墙说话、UI 隐形
- **像 Apple TV+**：克制的衬线点缀、留白多、电影感
- **像 Letterboxd**：编辑/影评人调性，文字承载得住，不靠色块和数字堆肌理

**不是**这些：
- ❌ AI Dungeon（UGC 集市气质，密度大、社交化、靠插画堆肌理）
- ❌ Steam / itch.io（密度大、平台感）
- ❌ Riot / 暴雪官网（强 hero、橙红 CTA、游戏感）

→ **全站每一个页面都按这一条线判断**。首页、发现、世界详情、游戏页、历史、登录、创作工坊——同一套语言，不分页面切换风格。游戏页（§12）有"沉浸优先"的局部例外，但仍受这条总纲约束。

### 同类元素 = 同一视觉（v2.3.1 新增铁律）

**同类型组件在全站必须长得一样**，禁止每页自己发明一套。

| 元素类型 | 必须共享的属性 |
|---|---|
| 「世界封面卡」（discover lobby、history ended、worlds 详情卡） | aspect-ratio 3:2 / 圆角 12px / `--lv-card-border` / `--lv-cover-overlay-light` / 标题外置 |
| 「横向 save 卡」（discover continue save、history active save、SavesCarouselCard） | bg/border 用 `--lv-card-*` tokens / 缩略图圆角 8-12px / hover 反应一致（§2.5） |
| 「Filter chip」（discover、workshop、admin） | 高度 32 / pill / 未选中规则 + 选中规则一致（§2.5） |
| 「Mode 区分」（剧本 / 自由） | 纯文字「剧本」/「自由」+ 中性 ink-2，**不再使用 ◆/◇ 符号**，**不再分金/银染色** |
| 「CTA 按钮」 | 用 `lv-btn-primary` / `lv-btn` 通用类，尺寸用 sm/md/lg token，**不准每页发明新尺寸** |

判断违反："如果设计师/AI 同事在另一个页面把这个元素重画了一套，能否一眼指出它不一致？" 能 → 违反。

---

## Part A · 形（Shape & Rhythm）

## 1. 字体规则

### 1.1 三套字体的法定用途

只有这三种用途允许用对应字体，**其他场合一律 sans**：

| 字体 | 仅用于 | 反例 |
|---|---|---|
| **Cormorant Garamond + Noto Serif SC** (serif) | ① hero 主标题 ② 一段 italic 高亮短语 ③ 卡片世界名 ④ 引文（&ldquo;…&rdquo; 衬线斜体） | ❌ section 标题、按钮、列表项、章节副标、叙事正文 |
| **Inter + PingFang SC** (sans) | 其他全部文本（正文、按钮、标签、副标题、表单、菜单、**游戏页叙事段落**） | — |
| **JetBrains Mono** (mono) | 数字 / 时间戳 / 版本号 / id / 进度 % / 路径 / **caps & micro 大写小标签** | ❌ 中文短语（"03 · 时间线" 这种禁用 mono）❌ 英文标签 |

> v2.1 → v2.2：叙事段落从 serif 改 sans。中文长段 sans 阅读更舒适，serif 留给标题与引文这种"被注视"的位置，避免 serif 滥用。

### 1.2 字号阶梯（钉死 9 档）

整站只允许这 9 档，组件里**禁止出现这 9 档之外的字号**。所有标题档用 `clamp()` 平滑响应，UI 档固定。

| 名 | 移动端 | 桌面端 | clamp 实现 | 用途 | 字体 |
|---|---|---|---|---|---|
| `t-display`   | 48 | 112 | `clamp(48px, 9vw, 112px)`   | Hero 大标题（landing/ending），每页 ≤1 个 | serif |
| `t-h1`        | 28 | 48  | `clamp(28px, 4vw, 48px)`    | 页面主标题（world 名、admin 页头） | serif |
| `t-h2`        | 20 | 28  | `clamp(20px, 2.4vw, 28px)`  | 区块/section 标题 | serif |
| `t-h3`        | 16 | 18  | `clamp(16px, 1.4vw, 18px)`  | 卡片/小区块标题（PosterCard、history card） | sans |
| `t-narrative` | 15 | 17  | `clamp(15px, 1vw, 17px)`    | 叙事正文（play 页 narrator、world detail desc） | sans |
| `t-body`      | 15 | 15  | 固定                        | UI 正文（按钮、表单、消息气泡）—— 不响应式 | sans |
| `t-meta`      | 12 | 12  | 固定                        | 辅助/时间戳/状态文字 | sans |
| `t-caps`      | 11 | 11  | 固定                        | 大写小标签（模式徽章、章节编号）—— 配套 uppercase + ls 0.2em | mono |
| `t-micro`     | 10 | 10  | 固定                        | 极小标记（徽章/版本号）—— 每页 ≤3 处 | mono |

**为什么标题响应、UI 不响应**：移动端读 17px body 比 15px 累，UI 档保持锚点；标题是视觉重锤，必须随屏跟随。

**禁止**：写 `text-[Xrem]` arbitrary 值、写中间档（13/14/17/19/22/26/30/40/56/64/80/96 等都禁止）。约定级（不上 lint），由 PR 走查把关——见 §14.5。

> v2.1 → v2.2：
> - 7 档 → 9 档（新增 `t-h3` + `t-micro`）：原 h2 (20) 与 body (15) 之间断层，实战中卡片标题塌到 body 字重；现存 0.65rem 破例值 86 处归 caps，0.6rem 11 处归 micro。
> - 全部 clamp 化，废除 `@media (max-width: 768px)` 跳变。
> - 字体重新分配：narrative 从 serif 改 sans。

### 1.3 一页字号上限

主内容区域（不含 nav/footer/角标）**最多 4 档字号同屏**（v2.1 是 3 档，9 档体系下放宽到 4）。常见组合：

- 卡片网格页：`t-caps`（角标）+ `t-h3`（卡片标题）+ `t-body`（摘要）+ `t-meta`（题材标签）
- 详情页：`t-caps`（eyebrow）+ `t-h1`（世界名）+ `t-narrative`（描述）+ `t-meta`（meta）
- 首页 hero：`t-display`（主标题）+ `t-caps`（eyebrow）+ `t-body`（引文）
- 游戏页：`t-caps`（角色名）+ `t-narrative`（叙事）+ `t-body`（输入/UI）+ `t-meta`（系统提示）

`t-micro` 不计入 4 档上限，但每页 ≤3 处。

### 1.4 行高阶梯

| 字号档 | line-height |
|---|---|
| `t-display` | 1.05 |
| `t-h1` | 1.1 |
| `t-h2` | 1.2 |
| `t-h3` | 1.35 |
| `t-narrative`（叙事段落） | **1.85**（不可改 — 叙事感的来源） |
| `t-body` 短文本 / 按钮 | 1.6 |
| `t-body` 长文本 / 引文 | 1.7 |
| `t-meta`、`t-caps`、`t-micro` | 1.4–1.5 |

### 1.5 字间距

- serif `t-display`：`-0.02em`
- serif `t-h1`：`-0.015em`
- serif `t-h2`：`-0.01em`
- sans 标题/正文：默认 0
- `t-narrative`（叙事）：`0.005em`（轻微正字距帮助 CJK 散开）
- `t-caps`（mono ALL CAPS）：`0.2em`
- `t-micro`（mono ALL CAPS）：`0.15em`

### 1.6 字重

- serif：**400 / 500**（300 对中文 serif 太细，禁用）
- sans：400 / 500 / 600（**禁止 700+**，中文 sans 加粗到 700 在 dark 底上易糊）
- mono：500 单一字重

### 1.7 修复现状的工序

排查清单（v2.2 重构期工序，已完成；归档版见 `docs/_archive/frontend-refactor-2026-05.md` 阶段 5）：

1. **令牌系统并轨**：`globals.css` 里的 `--font-size-*` / `--ta-*` 整组删除，全站只保留 `--lv-*` 一套作为 source of truth
2. **grep 全站 `text-[\d`** arbitrary class 值（约 163 处），按 §1.2 表对照映射到 9 档之一
3. **grep `font-family: serif`**，凡不在 §1.1 法定四种用途的，改 sans
4. **grep `font-family: mono`**，凡不是数字/时间戳/版本号/caps/micro，改 sans
5. **ESLint 锁旧 token**：禁止 `var(--font-size-*)` / `var(--ta-*)` / `var(--color-accent)` 引用，CI 卡死。其余字号/间距/圆角破例不上 lint，由走查处理（见 §14.5）。

做完这一遍，"不协调"问题 90% 解决。剩下 10% 在动效一致性和移动端布局，见 §6 §15。

---

## 2. 颜色规则

### 2.1 金色使用白名单（v2.3.1 收敛，2026-05）

香槟金 `--lv-accent` (#dfc290) 是**语义色，不是装饰色**。下面 5 类是唯一允许的使用位，**其他场景一律禁止**。

| 允许场景 | 具体位置 |
|---|---|
| ✅ **品牌标识** | ProductNav T 字母 / brand dot、MobileTopBar brand dot |
| ✅ **Spotlight / 运营标签** | hero 「本周精选」eyebrow、运营徽章 |
| ✅ **Active 选中态（全部）** | filter chip 选中（实金底 + 黑字）、active nav tab（金字 + 微金底胶囊）、workshop tab underline、pagination active dot。金色是 InkWild 的品牌色 "cinematic gold"，active 用品牌色跟 Netflix 红 / Spotify 绿同理，让"你在我的体系里"这条信息有温度有锚点 |
| ✅ **Focus ring** | a11y `:focus-visible` outline 2px |
| ✅ **Perfect ending 语义** | 剧本完美结局专属（`endingThemeColor("perfect")`） |

**禁止使用**：
- ❌ 任意 hover-paint-gold：`hover` 把 background / border / text / shadow 切金
- ❌ 普通卡片 / 按钮的 border、shadow 带金渍（`rgba(223, 194, 144, 0.x)`）
- ❌ 装饰性金色 line / gradient / glow（如 nav 下"金 hairline"、box-shadow 金光晕）
- ❌ default button bg 金；hover bg 金（CTA 用 `--lv-ink` ivory + 中性 lift）
- ❌ 列表项前缀 ◆ ◇ 符号染金（mode 区分用纯文字，不用符号 + 色彩）

**银雾 `--lv-accent-2` (#aeb4b8)** 早期保留给"自由模式" ◇ 符号语义，v2.3.1 起随 ◆/◇ 符号全站删除而**事实上停用**。文件里仍有引用是过渡，不要新增。

> v2.3 → v2.3.1：上一版"剧本/自由"用 ◆ 金 / ◇ 银双符号区分，实测在卡片网格里读起来油腻（多个卡同时染金/染银）。改成纯文字「剧本」/「自由」+ 中性色，模式仍清晰，视觉干净。

### 2.2 状态/选中色用 ink 不用 accent

- chip 选中 / sort 选中 / nav 选中：用 `rgba(255,255,255,0.07)` 背景 + `--lv-ink` 文字
- 进度条：用 `--lv-ink-2` 或 `--lv-ink-3`
- 徽章 / 标签 / 章节序号：灰阶

### 2.3 灰阶层级

继续用 spec 的 `--lv-ink` / `-2` / `-3` / `-4` / `-5`，无新增。`--lv-line` / `--lv-line-2` 用于边框，不再加第三种亮度。

### 2.4 状态色

只用于错误、警告、成功反馈，**不参与装饰**：

| Token | 颜色 | 用途 |
|---|---|---|
| `--lv-danger`  | 暖珊瑚 #ef8276 | 错误信息、删除确认 |
| `--lv-warn`    | 琥珀 #c9a36a | 警告（与 `--lv-accent` 区分：warn 偏橙、accent 偏金） |
| `--lv-success` | 苔绿 #7fb091 | 仅状态成功反馈（v2.3 起独立于 `--lv-accent-2`） |

每个状态色一屏 ≤ 1 处。错误信息**不能只靠颜色传达**——红字必须配文字描述或图标（§13）。

> v2.2 → v2.3：danger 从暗红 #b85c5c 改成暖珊瑚 #ef8276，在暗底上对比度更高、不像"血红警告"那么粗暴；success 与 accent-2 解绑（accent-2 改成银雾）。

### 2.5 Hover / Focus 反应统一（v2.3.1 新增）

**全站只允许一种 hover 反应模板**——禁止每个组件自己发明 hover 反应。

| 元素 | 默认 | Hover | Focus-visible |
|---|---|---|---|
| **按钮 (Primary / `lv-btn-primary`)** | ivory `--lv-ink` 底 + 黑字 | `translateY(-1px)` + `box-shadow: 0 12px 30px rgba(0,0,0,0.55)` | 金色 outline 2px |
| **按钮 (Ghost / `lv-btn`)** | 透明 + 中性白 border `rgba(255,255,255,0.10)` | bg `rgba(255,255,255,0.06)` + border `rgba(255,255,255,0.20)` | 金色 outline 2px |
| **卡片 / Link** | `--lv-card-bg` + `--lv-card-border` | bg `--lv-card-bg-hover` + border `--lv-card-border-hover` + `translateY(-2~3px)` | 金色 outline 2px |
| **文字链接 / Tab** | `--lv-ink-2` 或 `--lv-ink-3` | 切 `--lv-ink`（**不切金**） | 金色 outline 2px |
| **Chip / Pill (未选中)** | `--lv-ink-2` 文字 + 中性白 border | 文字切 `--lv-ink`，border 升 `rgba(255,255,255,0.16)`（**不切金**） | 金色 outline 2px |
| **Chip / Pill (已选中)** | `--lv-accent` 实金底 + 黑字 | 不变（已是终态） | 金色 outline 2px |
| **Nav / Tab (已选中)** | `--lv-accent` 金字 + 微金底胶囊 `rgba(223,194,144,0.06)` + 微金边 `rgba(223,194,144,0.12)` | 不变 | 金色 outline 2px |
| **Pagination (active dot)** | `--lv-accent` 长条 28×2，inactive 灰白 6×2 | 不变 | — |
| **Filter / Search input** | `rgba(255,255,255,0.035)` 底 + 中性白 border | — | border 升 `rgba(255,255,255,0.16)` + bg `0.06`，**禁止金色 focus 圈** |

**反模式（一律禁止）**：
- ❌ Hover 切金 background：`:hover { background: var(--lv-accent) }`
- ❌ Hover 切金 border：`:hover { border-color: rgba(223,194,144,*) }`
- ❌ Hover 切金 text：`:hover { color: var(--lv-accent) }`（active 选中态除外）
- ❌ Hover 加金色 box-shadow：`:hover { box-shadow: 0 * * rgba(223,194,144,*) }`
- ❌ 嵌套 hover 反应：外卡片 hover 时，内部 pill / icon / text 各自又切金（堆叠油腻的根因）

### 2.6 卡片容器 token（v2.3.1 新增）

全站卡片**只准用这一套 token**，不准每页手写 rgba 数值：

```css
/* 默认 */
background: var(--lv-card-bg);          /* rgba(255,255,255,0.01) */
border:     var(--lv-card-border);      /* 1px solid rgba(255,255,255,0.06) */
box-shadow: var(--lv-card-shadow);      /* 0 6px 15px rgba(0,0,0,0.2) */

/* Hover */
background: var(--lv-card-bg-hover);    /* rgba(255,255,255,0.025) */
border:     var(--lv-card-border-hover);/* 1px solid rgba(255,255,255,0.12) */
box-shadow: var(--lv-card-shadow-hover);/* 0 16px 32px rgba(0,0,0,0.45) */
```

特殊场景（hero / spotlight / modal）允许例外，但要在 PR 里说明理由。

### 2.7 封面图 overlay token（v2.3.1 新增）

| Token | 用途 | 强度 |
|---|---|---|
| `--lv-cover-overlay-light` | 普通封面网格卡（discover lobby、history ended） | 顶部至 35% 处完全透明，底部 0.28（**保亮**） |
| `--lv-cover-overlay-cinematic` | 全屏 hero / spotlight 海报 | 38% 透明 → 72% 处 0.55 → 94% 处 0.92 → 底接 bg（cinematic gradient） |

禁止自己手写 `linear-gradient(... rgba(8,8,10,0.x))` 量级 ≥ 0.5 的 cover overlay——除非是 hero / spotlight。普通卡用 token，保证封面"亮"。

---

## 3. 圆角

| Token | 半径 | 用途 |
|---|---|---|
| `--lv-r-card`  | 16px   | 卡片、面板、modal、徽章、角标 |
| `--lv-r-input` | 10px   | **仅** input / select / textarea 表单控件 |
| `--lv-r-pill`  | 9999px | 按钮、chip、tag、nav 胶囊 |

**只许这 3 档。** 删除 `--lv-r-sm` (8px) / `--lv-r-md` (12px) / `--lv-r-xl` (24px) 三档（不删 token 但代码禁用）。

> v2 → v2.1：v2 的"全部归并到 16"会让输入框看起来像"卡片套卡片"，工坊全是表单受影响最大。新增 `--lv-r-input` 10px 例外。

---

## 4. 间距尺度

整站只用这 9 档：

| Token | px | 典型用途 |
|---|---|---|
| `s-1`  | 4  | 图标内距、tag 内距 |
| `s-2`  | 8  | 紧凑组件内边距、icon-text 间距 |
| `s-3`  | 12 | 按钮垂直 padding |
| `s-4`  | 16 | 卡片内边距、组件间距 |
| `s-6`  | 24 | 段间距 |
| `s-8`  | 32 | 章节间距 |
| `s-12` | 48 | 大块间距 |
| `s-16` | 64 | hero 上下 padding |
| `s-24` | 96 | 章节大块间距（落地页限定） |

**禁止**写 7 / 10 / 14 / 18 / 20 / 22 / 28 / 36 / 40 / 56 等破例值。Tailwind class 也按这 9 档对齐（gap-1/2/3/4/6/8/12/16/24，禁用 gap-5/7/9/10/11）。

> 当前实现：`globals.css` 中 `--lv-pad-x` 桌面 48px / 移动端 16px (s-4)，`--lv-pad-y` 桌面 96px (s-24) / 移动端 64px (s-16)，全部对齐间距 9 档。

---

## 5. 图层（z-index）

整站只许这 6 档，**禁止**写 99 / 999 / 9999：

| Token | 值 | 用途 |
|---|---|---|
| `--z-base`    | 1   | 默认堆叠 |
| `--z-sticky`  | 50  | sticky header / sticky CTA |
| `--z-drawer`  | 100 | 侧抽屉、底部抽屉 |
| `--z-modal`   | 200 | modal 对话框 |
| `--z-toast`   | 300 | toast、流式状态浮层 |
| `--z-overlay` | 400 | 全屏覆盖（暂停、ending cinematic、加载） |

---

## 6. 动效

| 用途 | 时长 | 缓动 |
|---|---|---|
| 一切常规交互（hover、按钮、输入框、菜单、抽屉、淡入淡出） | **200ms** | `cubic-bezier(0.2, 0.7, 0.2, 1)` |
| Scroll Reveal / 列表入场 stagger（每项 fade-up） | **500ms** + 70ms 间隔 | 同上（详见下） |
| **Modal 入场例外**：身份切换型 modal（如 login）overlay ≤ 450ms / 内容卡 ≤ 600ms（fade + 12px 浮起 + 微缩放 + 模糊褪去），退场 ≤ 250ms | 450 / 600ms | 同上 |
| **Cinematic 例外 A**：仅首页 hero 封面 crossfade、Ken Burns | 1800ms / 18s | 同上 |
| **Cinematic 例外 B**：游戏页结局 fade-in、按段揭示 | 1200ms / 段 600ms | 同上 |

> 一切 hover transform 500ms+ 的写法**全部改 200ms**。Cinematic 长动效**只许出现在首页 hero 和游戏结局**。Modal 入场例外**仅允许身份/状态切换 modal**（如登录/确认弹窗），不许用于普通信息 modal、抽屉、popover。

### Scroll Reveal & 列表入场 stagger（统一规则）

整站任何 "元素进入视口出现" 或 "列表 mount 时渐次浮起" 的动效，**只允许**这一套实现：`lvStaggerContainer` + `lvStaggerItem`（`frontend/lib/motion.ts`）+ Framer Motion (`motion/react`)。Netflix / Apple TV+ 路线，柔而非快。

| 参数 | 值 | 备注 |
|---|---|---|
| 单项 fade-up duration | **500ms** | 比常规 200ms / 旧"页面进入 400ms" 略柔 |
| 单项 lift offset | y: **12px** | 入场前从下方 12px 偏移浮起 |
| stagger 间隔 | **70ms** | 多项之间的入场延迟 |
| 容器 delayChildren | **40ms** | 容器开始到首项入场的延迟 |
| 缓动 | `cubic-bezier(0.2, 0.7, 0.2, 1)` (`LV_EASE`) | 全站统一 |

**两种触发场景，同一套 variants**：
- **列表 mount**（discover 网格、history 列表、admin 列表）：父容器 `animate="show"`，挂载即触发
- **Scroll Reveal**（landing screen 2/3、长页 section）：父容器 `whileInView="show"` + `viewport={{ once: true, amount: 0.2 }}`

**示例**：

```tsx
import { motion } from "motion/react";
import { lvStaggerContainer, lvStaggerItem } from "@/lib/motion";

<motion.div variants={lvStaggerContainer} initial="hidden" animate="show">
  {items.map((it) => (
    <motion.div key={it.id} variants={lvStaggerItem}>
      <Card data={it} />
    </motion.div>
  ))}
</motion.div>
```

**禁止**：
- 自己写 `IntersectionObserver` + CSS transition 实现 fade-up（重复造轮子，节奏不一致）
- 用 CSS `animation-delay` 实现 stagger（不响应 prefers-reduced-motion 且 SSR 闪烁）
- 单项 duration 超 600ms 或低于 400ms（前者拖沓、后者节奏断了）
- stagger 间隔超 100ms 或低于 50ms（前者粘连感太强、后者糊在一起）
- 引入 ScrollMagic / GSAP / AOS 等第三方库（已有 Framer Motion）

### 毛玻璃 backdrop-filter

`backdrop-filter` 本身允许（不属于"装饰堆叠"反例），但**只在以下场景单独使用**，不与暖金角光 / 苔绿微光 / SVG noise 叠加：

- **Modal overlay**：`backdrop-filter: blur(12-16px) saturate(120%)`，配合 50-60% 黑底
- **Modal 内容卡**：`backdrop-filter: blur(24-32px) saturate(140%)`，配合 70-78% 不透明深底
- **play 页 header 浮层 / drawer / sticky**：见 §12.5

禁止：① 组合多层 blur + 装饰光晕；② 在普通卡片 / section 上加毛玻璃（卡片用实心 `--lv-bg-1`）。

### 自动循环动画

整站 ≤ 2 处。允许：①首页 hero Ken Burns；②加载态（§10.1，全屏 Branch + Grow 或小内联 8px 脉冲）。其他位置（脉冲点、流光、扫光、扫描线、霓虹辉光）**禁止**。

### prefers-reduced-motion

所有 cinematic 动效（Ken Burns、ending fade、加载脉冲）必须监听 `prefers-reduced-motion: reduce`，命中时降级到瞬时切换或 200ms 短动效。

---

## Part B · 信（Content & Information）

## 7. 信息密度（卡片上限）

### 7.1 世界卡片字段（钉死）

```
[封面 16:10 横版]
  ├─ 角标 1（模式编码 ◆/◇，封面右上，仅 glyph 不加文字）
  └─ 角标 2（NEW / HOT 标签，可选，封面左上，ink 灰阶不要 accent）
[标题]                          ← serif t-h2，1 行 clamp
[摘要 hook]                     ← sans t-body，1 行 clamp，ink-2
[题材 · 时代 · 难度 · 时长]      ← sans t-meta，ink-3
```

**总共 5 个文字位**（含 2 角标 + 标题 + hook + meta）。**禁止**追加：作者头像、播放数、收藏数、点赞数、评论数、上线日期。这是 AI Dungeon 的字段表，不是我们的。

封面 16:10 横版的对标坐标是 Netflix / Apple TV+ 的"浏览墙 capsule"——不是 Letterboxd 的"电影海报页"（那是 3:4）。摘要 1 行、单行 meta、模式角标只用 ◆/◇ glyph，都是这条对标的下游推论。封面规范见 `cover-art-spec.md` v1.2。

### 7.2 历史卡片字段（钉死）

进行中：
```
[封面 1:1，120px]
[世界名 · 角色] ← caps
[当前章节]      ← serif t-h2
[上次到这里 引文] ← serif italic t-body
[更新时间 · 用时 · 进度 %] ← mono t-meta
[继续 →] ← 主 CTA
```

已结束：紧凑列表行，**只许**：缩略图 + 世界名/角色 + 结局标签 + 时间。

### 7.3 hero 文案结构（钉死）

- Eyebrow（caps 1 行）
- 主标题（1-2 行，可含 1 个 italic 高亮）
- 副标题/引文（≤ 30 字，1 行）
- CTA（1-2 个）

---

## 8. 布局

### 8.1 工具栏

- **必须**：左对齐，左边分类/搜索，右边排序
- **禁止**：居中孤岛工具栏、单独占一屏的筛选区

### 8.2 网格

- 发现页：4 列等宽 3:4 卡片，gap 20px。1280-1920px 屏统一 4 列，**禁止** 5 列 / 6 列 / masonry。
- 移动端：1 列。平板 2 列。

### 8.3 容器宽度

- 主内容容器：**1320px 上限**。1920+ 屏不再扩。
- 长文阅读：760px。
- 游戏页阅读区：760px（§12）。

### 8.4 反模式（一律禁止）

- ❌ 占 70vh 的"功能名 4 字 serif 大标题 + 一行小字" hero（替代：要么真做全屏封面 hero，要么压扁到 200px 内）
- ❌ 一行只有 2-3 个 chip 然后大块空白
- ❌ 卡片 caption 居中（应左对齐与图左缘对齐）
- ❌ 装饰性的 ──── 长分隔线横跨屏宽
- ❌ "发 现 世 界" 这种字符间空格的伪间距设计

---

## 9. 文案

### 9.1 替换原则：**删修饰词，保情绪**

不是把所有文案变成大白话——Letterboxd 的调性是"诗意但不空"，不是冷冰冰直说。

判别方法：**如果一句话删一半还能传达原意，就该删。** 凡是堆叠"无限 / 沉浸 / 唤醒 / 启程 / 序章 / 维度 / 多重宇宙"的，几乎都能删一半。

| ❌ AI 味（堆叠修饰） | ✅ 凝练（保情绪） |
|---|---|
| 探索无限可能的叙事宇宙 | 看看有什么世界在等你 |
| 翻阅你在多重宇宙里遗留的足印、停滞的光阴与尘封的终局 | 你的足迹 / 还没结束的故事 |
| 沉浸式叙事体验 | 一坐两小时 |
| 解锁全新故事维度 | 进入剧本 |
| 唤醒/觉醒/启程/序章 | 进入 / 开始 / 玩 |

> v2 → v2.1：v2 的替换示例过矫正（"翻阅你的足印" → "你玩过的"丢了 Letterboxd 的诗意调性）。原则改成"删修饰词，保情绪"，给具体写文案的人留判断空间。

### 9.2 hero 不放功能名

"发现世界" / "溯源记录" / "创作工坊" 这种功能名**不做** hero 主标题。功能名留给 nav / 面包屑 / `t-h1` 小标题。Hero 应该承担**钩子**——一句让人想看下去的话，或一张让人想点进去的封面。

如果实在没钩子，**直接进内容**。压扁的 200px header + `t-h1` 小标题就够。

---

## 10. 三态：加载 / 空 / 错误

### 10.1 加载态

- **禁止**纯文字加载提示（即"正在加载..."独立成段当唯一视觉）
- **全屏 / 页面级加载**（v2.4，2026-05 升级）：**Branch + Grow 2.5s** + 下方 italic serif 文案"正在加载"（默认）。Branch 是主视觉，文案是辅助说明，两者一起出，不再裸奔。caller 已有自己的上下文文案（GameLoadingScreen 的角色行 / GenerationLoadingScreen 的 phase headline）时传 `label=""` 隐藏默认。配套组件 `<LoadingPulse variant="block" label="..." />`，CSS `.lv-loading-branch`（`globals.css`）
- **小内联反馈**（保存指示 / 重试小圆点 / admin 内嵌等小 UI feedback）：8px 暖金圆 1800ms 脉冲（`opacity 0.3 ↔ 1`）—— 配套 `<LoadingPulse variant="inline" />` 或 raw `<span class="lv-loading-pulse">`
- **思考态进度**（play 回合内，2026-05-30）：提交动作 → 首包前，时间线底部左对齐**小号 Branch logo**（`<LoadingPulse variant="branch" />`，持续 Grow）+ 演进式过程反馈小字（按真实里程碑切换：接收行动 → 推演 → NPC 进场 → 落笔，零额外 LLM、每回合不同）。Branch 主视觉 + 文案辅助、非纯文字，合规。详见 `play-mode-spec.md §4.3`
- **列表加载**：骨架屏 `.lv-skel` 类（见下），不用 spinner
- **内容回来**：走 §6 Scroll Reveal & 列表入场 stagger（`lvStaggerContainer` + `lvStaggerItem`）

#### 为什么 v2.4 改成 Branch + Grow

InkWild 定 brand mark = Branch（一根有 3 分叉的枝）后，全屏加载就是品牌入场的最佳时机。"枝在生长" 1:1 对应 "世界正在长出来" 的产品 promise，比抽象 8px 圆点强 100 倍的品牌记忆度。
小尺寸内联保留 8px 金点 —— 那种场景是 UI feedback 不是品牌时刻，Branch 上去会过重。

#### prefers-reduced-motion 降级

Branch + Grow 自动检测，命中时退到简单 opacity 脉冲（保留可访问性，去掉 stroke-dashoffset 动画）。`.lv-loading-branch` CSS 内置该 fallback。

#### Skeleton Screen 骨架屏（统一规则）

整站任何 "列表内容加载时显示" 的占位骨架，**只允许**这一套实现：`.lv-skel` 类（`globals.css`）。Netflix / Apple TV+ 路线，柔光扫过而非静态灰块。

| 参数 | 值 | 备注 |
|---|---|---|
| 背景渐变 | `linear-gradient(90deg, --lv-bg-1 0%, --lv-line-2 50%, --lv-bg-1 100%)` | 200% 宽度便于扫动 |
| 动画 keyframe | `background-position: 200% 0 → -200% 0` | 横向扫过 |
| 动画 duration | **2s** | ease-in-out，慢而柔 |
| 循环 | infinite | 直到内容回来 |
| 形状 | 由 caller 用 `borderRadius` + `aspectRatio` / `height` / `width` 控制 | 封面 `aspectRatio: "16 / 10"`，文字条 `borderRadius: var(--lv-r-pill)` |
| `prefers-reduced-motion` | 自动停动画 + 退到 `--lv-line` 静态色 | 已在 `.lv-skel` 内置 |

**示例**：

```tsx
// 封面骨架
<div className="lv-skel" style={{ aspectRatio: "16 / 10", borderRadius: "var(--lv-r-card)" }} />

// 标题文字条
<div className="lv-skel" style={{ height: 18, width: "60%", borderRadius: "var(--lv-r-pill)" }} />

// meta 文字条
<div className="lv-skel" style={{ height: 12, width: "45%", borderRadius: "var(--lv-r-pill)" }} />
```

**布局原则**：
- 占位卡数 ≈ 视口可见数（避免内容回来时大幅布局跳变）
- 占位形状 ≈ 真实内容（封面骨架用真实 16:10，标题骨架宽度约 60-70%）
- 占位与真实内容衔接：用 §6 stagger 入场，不要硬切

**禁止**：
- 自己写 `@keyframes` + `background-image` 实现 shimmer（重复造轮子）
- 用 `LoadingPulse` 圆点 spinner 替代列表骨架（违反列表加载规则）
- 骨架灰度太亮（`--lv-bg-1` ↔ `--lv-line-2` 已是上限，再亮像加载条）
- 骨架运动太快（≤ 1s 显得"焦虑"，破坏 cinematic 调性）

### 10.2 空态

布局：
```
[一句话状态]   ← sans t-body
[次级提示]     ← sans t-meta
[1 个 CTA]    ← lv-btn 主按钮
```

例：
- "还没玩过任何世界" / "世界墙里有 8 个等你" / "去看看 →"
- "你还没创建任何草稿" / "从一个点子开始" / "+ 新建世界"

**禁止**：插画占位、emoji、SVG 卡通角色、"哎呀，这里空空如也~" 类口语化文案。

### 10.3 错误态

- 6px 红色圆点（`--lv-danger`）+ sans `t-body` 一句话 + 1 个 retry chip
- **不显示**堆栈、HTTP code、技术名词
- 错误信息要带行动指引："网络断了，重试" 而不是 "Error: fetch failed"
- 致命错误（如 401）跳到对应解决路径（登录页），不显示在原页面

---

## Part C · 场（Context-Specific）

## 11. 表单规范

### 11.1 布局

- label 在 input **上方**（不在左边、不浮动）
- label 用 sans `t-meta`，颜色 `--lv-ink-2`
- 必填字段在 label 后加 4px 暖金小点，**不写 `*`**
- 帮助文字始终在 input 下方，sans `t-meta`，颜色 `--lv-ink-3`

### 11.2 控件尺寸

- input/select/textarea 高度 44px（移动端可点）
- 圆角 10px (`--lv-r-input`)
- 内边距 12px 水平 / 0 垂直（高度由 height 控制）
- 边框 1px `--lv-line-2`，背景 `rgba(255,255,255,0.02)`

### 11.3 状态

- focus：`box-shadow: 0 0 0 2px var(--lv-accent-soft)`，**不改 border 颜色**
- error：input 下加 6px 红点 + sans `t-meta` 红字描述
- disabled：opacity 0.5，不改背景色
- readonly：背景 `rgba(255,255,255,0.04)`，光标禁用

### 11.4 反模式

- ❌ 多列表单（开始-结束、姓-名 这类成对字段除外）
- ❌ floating label（动效贵，且和 cinematic 调性不符）
- ❌ "请输入..." 占位（占位用真实示例：`例：1925 年的青岛`）
- ❌ 红色 `*` 必填星号
- ❌ 内联 inline error tooltip（用下方静态错误描述代替）

---

## 12. 游戏页（Play Mode）规范

游戏页是"在世界里"的状态，**沉浸优先**于"内容墙"的视觉密度，但仍受 §1-§6 总规约束。这是整站最复杂、用户停留最久的页面，规则必须显式。

### 12.1 沉浸要求

- nav 折叠（hover 或菜单按钮唤出，不常驻）
- 容器宽度阅读区 760px（不用 1320）
- 背景比 `--lv-bg` 再深 4-5%（用 `--lv-bg-stage` 令牌）
- 进入页：cinematic fade-in 1200ms（§6 例外 B）

### 12.2 叙事段落

- 字体 **sans**（v2.2 改），字号 `t-narrative` (clamp 15→17px)，行高 **1.85（不可改）**
- 段落间距 24px（`s-6`）
- 玩家动作 italic + 缩进 1em
- 系统提示居中、`t-meta`、`--lv-ink-3`
- 角色名用 `t-caps` 颜色 `--lv-ink-3`，与叙述间留 8px 垂直间距

### 12.3 消息呈现（不要做 IM）

- **不用** IM 式气泡（边框 + 背景色块）
- 用左侧小字角色名（caps，颜色 `--lv-ink-3`）+ 缩进对齐叙述
- 角色名和叙述间留 8px 垂直间距
- 玩家自己的动作：右对齐缩进 + italic

### 12.4 流式状态

- streaming 时段落末尾 8px 闪烁光标（**不**逐字 typewriter，分散注意力且性能差）
- 中断/重试按钮：浮层（toast 层 `--z-toast`），不阻塞历史阅读
- 思考态进度轨道（`StreamingStatusRail`，2026-05-30 重设）：时间线底部**左对齐**，小号 Branch logo + 演进式 stage 文案（接收 → 推演 → 进场 → 落笔），首包到达 300ms 淡出。详见 §10.1 + `play-mode-spec.md §4.3`

### 12.5 案件板 / Hologram

- 全屏 modal，背景 `backdrop-filter: blur(40px) brightness(0.4)`
- 卡片用 `--lv-r-card` (16px)
- **禁止**全息特效堆叠（脉冲、扫光、扫描线、霓虹）—— 案件板是清单看板，不是科幻片道具

### 12.6 结局动画

- §6 cinematic 例外 B 的应用场景
- fade-in 1200ms，文字按段揭示（每段 600ms 间隔），**不**逐字
- 结局标题 `t-display` serif，正文 `t-narrative`（sans）
- 背景图（如有）应用 Ken Burns，但缩放幅度 ≤ 1.05（hero 的 1.1 太大会显廉价）

### 12.7 输入框

- 底部固定（**不**浮动跟随滚动，避免抖动）
- 高度 56px（比常规 input 略大，是主要交互目标）
- placeholder 给具体动作示例：`查看房间 / 推开门 / 询问她的来历`，**不**写"请输入"
- 提交后输入框微微下沉 200ms 再恢复，作为反馈
- 圆角 `--lv-r-pill`（输入框是行动入口，按胶囊处理而非 form input）

### 12.8 移动端布局（v2.2 新增）

- 桌面双栏（chat + 案件板）→ 移动端**单栏 + 底部抽屉**
- nav 折叠为右上角图标（不用底部 tab，play 页是沉浸态）
- 案件板抽屉从底部上推，而非桌面端的右侧滑入
- 输入框 `100dvh` + `safe-area-inset-bottom`，避免被 iOS Safari 工具栏遮挡
- 触摸目标 ≥ 44px

---

## 13. 无障碍底线

不是"加分项"，是合规底线：

- 文字对比度 ≥ 4.5:1（正文）/ 3:1（≥ 24px 大字号 / 图标）
- 所有可交互元素 keyboard focus 必须有可见焦点环（默认 `outline: 2px solid var(--lv-accent)`，offset 2px）
- 触摸目标最小 44×44px（按钮、chip、icon button）
- `<img>` 必须有 `alt`；装饰图 `alt=""`
- 错误信息**不能只用颜色**传达（红字必须配文字描述 + 图标）
- `prefers-reduced-motion: reduce` 命中时关闭：Ken Burns、ending fade、加载脉冲、所有 hover transform
- 表单 label 必须 `<label htmlFor>` 或 `aria-label` 关联
- modal 打开时 trap focus，Esc 关闭

---

## Part D · 治（Governance）

## 14. 落地机制

### 14.1 PR 自检表（落到 `.github/pull_request_template.md`）

```
[ ] 字号只用了 9 档之一（display/h1/h2/h3/narrative/body/meta/caps/micro）
[ ] 一屏字号 ≤ 4 档（micro 不计）
[ ] 没有 inline text-[Xrem] 或 fontSize 数字
[ ] serif 仅用于 hero / 卡片标题 / 引文（叙事正文已改 sans）
[ ] mono 仅用于数字 / 时间戳 / 版本号 / caps / micro
[ ] 字重符合 §1.6（serif 400/500、sans 不超 600、mono 500）
[ ] 装饰性 accent 一屏 ≤ 1 处，且是暖金
[ ] 绿色仅用于"自由模式"语义编码
[ ] 圆角只用了 16 / 10（仅表单）/ 9999
[ ] 间距用 9 档之一，没出现 7/10/14/18/22/28
[ ] z-index 用 6 档之一，没出现 99/999/9999
[ ] hover/transition ≤ 250ms（cinematic 例外除外）
[ ] 卡片信息项 ≤ 5
[ ] 没有"翻阅你的足印"类 AI 文案
[ ] 没有四字 serif 大标题占满首屏（首页 hero 例外）
[ ] toolbar 左对齐
[ ] 加载态不写"正在加载..."文字
[ ] 三态完整（loading / empty / error）
[ ] 移动端 375px 截图通过 + 桌面 1280px 截图通过
[ ] 触摸目标 ≥ 44px
[ ] 焦点环可见、对比度 ≥ 4.5:1
[ ] prefers-reduced-motion 时关闭长动效
[ ] 文案走 i18n（next-intl t() 调用，不硬编码中文）
```

这是走查清单，不是 CI 卡点（机器只锁旧 token，见 §14.5）。漏项不阻塞合入，下次走查（§14.3）补回来。

### 14.2 组件库 + Storybook（必须搭）

- 把 token + 12-15 个原子组件钉死：`<Button>` `<Chip>` `<PosterCard>` `<Tag>` `<PageHeader>` `<Toolbar>` `<EmptyState>` `<Pill>` `<Modal>` `<Drawer>` `<FormField>` `<LoadingPulse>` `<Skeleton>` `<ErrorState>`
- 复杂交互组件（Dialog/Drawer/Popover/Combobox/Toast/Command Menu）从 **shadcn/ui** 引入并 retheme，**简单组件保持手写**保留 cinematic 风格
- 页面里**禁止**手写 `<button style={{...}}>`、`<div style={{ borderRadius: ... }}>`，必须 import 组件
- Storybook 首页放 `/dev/type` 字体样张，每个组件展示所有状态（default / hover / active / disabled / loading / error）

### 14.3 每周设计走查（30 分钟）

- 你 + 前端 leader + 1 个其他眼睛
- 跑一遍这周新合的页面，对照 §14.1 自检表
- 不通过的开 issue，下周修

**没有走查机制，写多详细的规范都没用。**

### 14.4 基础设施层（v2.2 新增）

新页面/重构页面**必须**用这套基础设施，不再每页重新发明：

| 关注 | 库 | 替换什么 |
|---|---|---|
| 数据获取 | **TanStack Query** | 替掉 `useEffect + apiFetch + active flag` 重复模板 |
| 表单 | **React Hook Form + Zod** | 替掉 `useState + onChange + 手动校验` |
| 动效 | **Framer Motion** (`motion/react`) | 替掉手写 `transition` + `IntersectionObserver` |
| i18n | **next-intl** | 替掉硬编码中文，文案走 `t('xxx')` |
| 复杂交互 | **shadcn/ui** 选择性引入 | 替掉手写 Dialog/Drawer/Popover/Toast |
| 设计系统家 | **Storybook** | 替掉口头约定 |

不引入：TanStack Query 之外的 server state 库（SWR/Apollo）、CSS-in-JS、UI 框架（MUI/Chakra/Mantine）。

### 14.5 ESLint（v2.2 末期决策：最小约束，2026-05-09）

**只锁一条硬规则：禁止引用旧 token**（`--font-size-*` / `--ta-*` / `--color-accent`），防止漂回旧系统。CI lint 失败 = PR 拒绝。

字号 / 间距 / 圆角 / z-index / inline `fontSize` 等**不上 lint**——视觉判断还给设计师的眼睛 + §14.3 走查把关。

> **为什么松绑**：v2.2 早期把全部破例值锁死，实战发现 `text-[var(--lv-ink-3)]`（用 token 设颜色）这种合理写法被一并拦掉，且机器拦不出审美。改为最小约束后，规范从"机器执法"退回"团队约定 + 走查"。这条是规范成熟度的真实状态，不是治理松懈。
>
> 实现见 `frontend/eslint.config.mjs` 文件头注释。

---

## 15. 移动端规范（v2.2 新增）

整站默认**移动优先**：所有组件先设计 375px，桌面是放大版。

### 15.1 断点

| 名 | 宽度 | 用法 |
|---|---|---|
| mobile | < 768px | 默认基线 |
| tablet | 768–1024px | 卡片网格 2 列 |
| desktop | ≥ 1024px | 卡片网格 4 列、双栏布局生效 |

### 15.2 导航（v2.3 已落地）

- **移动端**：`<BottomTabBar />`（首页 / 发现 / 历史 / 我），高度 56px + safe-area-inset-bottom，挂在 `app/layout.tsx`
- **桌面端**：`<ProductNav variant="transparent|solid" active="..." />` 由各页面自行渲染（transparent 用于 hero 全屏页、solid 用于内容墙）
- **layout.tsx 不再渲染全局 Navbar**：旧的统一顶栏已废，per-page 自决 nav 形态以匹配各页面的视觉节奏
- play 页特殊：移动端 nav 折叠为右上角图标，并**隐藏** BottomTabBar（沉浸态，详见 `play-mode-spec.md` §2）

### 15.3 触控

- 触摸目标最小 44 × 44px
- 不依赖 hover 表达状态（hover-only 信息必须有移动端等价）
- 滑动手势用于抽屉关闭（向下滑）、卡片切换

### 15.4 视口

- 全部用 `100dvh` 而非 `100vh`（处理 iOS Safari 工具栏）
- `safe-area-inset-{top,bottom}` 处理刘海屏 / 底部 home indicator
- viewport meta：`width=device-width, initial-scale=1, viewport-fit=cover`

### 15.5 PWA（v2.3 已落地）

- `frontend/public/manifest.webmanifest` + `icon.svg` / `icon-maskable.svg`
- service worker 由 **serwist** (`@serwist/next` ^9.5) 生成；源在 `app/sw.ts`，构建产物 `public/sw.js`
- `layout.tsx` 已配 `manifest`、`appleWebApp`、`viewportFit: cover`、`themeColor: #0a0a0c`
- 启动页（splash screen）用 `lv-bg` 背景 + 中央 logo

---

## 16. 不在这份原则里的内容

- token 具体值（颜色 hex、间距 px 数组、字体栈）→ 看 `frontend-spec.md`
- 封面图标准 → 看 `cover-art-spec.md`
- 重构计划与阶段（已归档，v2.3 已上线）→ 看 `docs/_archive/frontend-refactor-2026-05.md`
- 技术架构 / 代码规范 → 看 `docs/ARCHITECTURE.md`
- 引擎 / agent 编排 → 看 `docs/modules/`

这份**只回答**："为什么我们令牌都对、画面还是杂？" 答：按 §1-§15 做减法、补缺失，按 §14 建机制。

---

> 维护人：jie / Claude Code
> 最后更新：2026-05-23（v2.3 cinematic gold：accent #c9b48a → #dfc290、accent-2 苔绿 → 银雾、danger #b85c5c → #ef8276、bg/ink 微调；全局 Navbar 移除，ProductNav + BottomTabBar 双形态；PWA 已落地）
> 状态：v2.3 已上线，主入口页面（landing / discover / history / workshop / login）全部按 v2.3 落地。play 页例外清单见 `play-mode-spec.md`
