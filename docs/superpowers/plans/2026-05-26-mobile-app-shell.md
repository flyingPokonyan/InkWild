# Mobile App-First Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Visual work caveat:** This is design-led frontend work, not test-driven. Each step pairs code with a 375px DevTools / real device verification against the corresponding demo HTML at `.superpowers/brainstorm/90683-1779700744/`. Acceptance = "looks structurally like the demo at 375 width, golden path is clickable, no regressions on ≥1024 desktop."

**Goal:** 把 6 个移动端 demo（landing / discover / history / workshop / world-detail / start）落地为正式前端代码，建立 App-first 移动外壳，为后续可能的 iOS 原生壳做好结构准备。

**Architecture:** 单代码库响应式策略，**不**拆 mobile / desktop 路由树。移动外壳通过新组件 `<MobileTopBar>` + 既有 `<BottomTabBar>` 共同承担，桌面继续走 `<ProductNav>`。视觉令牌锁死在 `app/globals.css :root .lv-theme`，移动端只用 `@media (max-width: 768px)` 或组件内部 prop 切换分支。每页页面文件保留，新加移动版结构 + media query，不开新路由。

**Tech Stack:** Next.js 16 + React 19 + TypeScript + Tailwind v4 + `motion/react` + next-intl + 现有 lib（vaul Drawer / Radix Popover）。**不引入新依赖。**

**Reference assets:**
- Demos：`.superpowers/brainstorm/90683-1779700744/*.html`（6 个）
- 视觉原则：`docs/design/visual-principles.md` v2.3
- 令牌：`docs/design/frontend-spec.md` v2.3
- 字号工具类：`.lv-t-*`（见 `frontend/AGENTS.md`）

**Scope（按子目标拆，每阶段独立 PR / mergeable）:**

| 阶段 | 任务 | 影响范围 |
|---|---|---|
| A | 共享移动外壳组件（MobileTopBar + LangChip + ProductNav 移动态调整） | 新组件 + ProductNav |
| B | Landing `/` 移动版 | `app/page.tsx` |
| C | Discover `/discover` 移动版 | `app/discover/page.tsx` |
| D | History `/history` 移动版 | `app/history/page.tsx` |
| E | Workshop `/workshop` 移动版 | `app/workshop/page.tsx` |
| F | World detail `/worlds/[id]` 移动版 | `app/worlds/[id]/page.tsx` |
| G | Start flow `/worlds/[id]/start` 移动版 | `app/worlds/[id]/start/page.tsx` |
| H | 收尾：i18n 文案补 / PR 自检 / 删 dev 残留 | 多文件 |

**Out of scope（demo 注释明确不做）:**
- workshop 编辑器移动版（`workshop/worlds/drafts/[id]` / `workshop/scripts/drafts/[id]`）
- workshop generate 页移动版
- play 页移动版（独立 spec：`docs/design/play-mode-spec.md`，已落地）
- 个人中心 sheet 内部内容（仅留入口，账户/语言/登出/管理 sheet 内容后续 spec）

---

## Conventions for every task

- 改的所有页面文件均挂 `className="lv-theme"`（已存在则保留）
- 移动断点统一用 `@media (max-width: 768px)`
- `safe-area-inset-bottom` 用 `env(safe-area-inset-bottom)`（参考 `BottomTabBar.tsx`）
- `100dvh` 不用 `100vh`
- 触摸目标 ≥ 44px
- 不引用旧 token（CI 卡死）：`--font-size-*` / `--ta-*` / `--color-accent`
- 颜色用 `var(--lv-*)`，字号优先 `.lv-t-*` 工具类
- mock 数据只在 hero 视觉字段允许，列表数据来自 TanStack Query 真实接口
- 每个 task 完成后：`npm run lint` 通过 + Chrome DevTools 切 iPhone SE (375×667) 看一眼 + 切桌面 1280 看不回归 → 单独 commit

---

## Stage A · 共享移动外壳

### Task A1: 新建 `MobileTopBar` 组件

**Why:** discover / history / workshop / world-detail 都用同一种顶栏（左 icon / 中 brand-mark / 右 icon-or-avatar），抽出来避免 4 处复写。Landing 不用这个（landing 的顶栏在 hero 内部叠层），但其他页面共用。

**Files:**
- Create: `frontend/components/MobileTopBar.tsx`

**Spec（精确对齐 demo CSS）:**
- 容器：`padding: 48px 16px 10px`（48px 给 iOS 状态栏留余），`display: grid; grid-template-columns: 42px 1fr 42px; gap: 10px`
- left/right slot：可传 React node 或省略，省略时 grid 单元保留占位
- center：`brand-mark`，serif italic 24px font-weight 500，前置 6×6 香槟金圆点（`--lv-accent`）
- icon button 默认样式：42×42 圆形、`rgba(255,255,255,0.035)` 底、`rgba(255,255,255,0.08)` 边、`var(--lv-ink-2)` 色、内部 SVG 20px
- 移动断点：`@media (min-width: 769px) { display: none }` —— 桌面端隐藏（桌面继续用 ProductNav）

**Props:**
```ts
interface MobileTopBarProps {
  left?: React.ReactNode;         // 一般是 IconButton 或 BackButton
  right?: React.ReactNode;        // IconButton / AvatarButton
  brand?: "TaleAlive" | React.ReactNode;  // 默认 "TaleAlive"
}
```

- [ ] **Step A1.1:** 写 `MobileTopBar.tsx`，导出 `MobileTopBar` 和 `MobileIconButton`（42px 圆按钮，接受 `aria-label`、`onClick`、children=SVG）
- [ ] **Step A1.2:** 跑 `npm run lint`，期望：pass
- [ ] **Step A1.3:** `git add components/MobileTopBar.tsx && git commit -m "feat(mobile): add MobileTopBar + MobileIconButton primitives"`

---

### Task A2: 新建 `LangChip` 组件（landing 顶部用）

**Why:** Landing demo 顶部右侧是 `中 / EN` 切换胶囊，目前 ProductNav 没有这个 affordance。抽成独立组件，landing 直接用；未来 workshop avatar sheet 内的"语言"项也复用。

**Files:**
- Create: `frontend/components/LangChip.tsx`

**Spec:**
- 胶囊 `border-radius: 9999px`，`padding: 6px 11px`
- `border: 1px solid rgba(255,255,255,0.18)`，`background: rgba(255,255,255,0.06)`，`backdrop-filter: blur(12px)`
- 字号：mono 10px，`letter-spacing: 0.18em`，uppercase
- 内容：`中 <span style="opacity:0.35"> / </span>EN`
- 暂时**只切 UI 视觉态**（用 `useState` 本地切换）；真实 i18n 切换（next-intl locale 切换）作为 Stage H 单独连线 —— 这一步不做完整 locale 切换避免阻塞外壳推进

- [ ] **Step A2.1:** 写 `LangChip.tsx`，导出 `LangChip`（无 props，内部 `useState` 切 `"zh" | "en"`，TODO 注释指出待接 i18n）
- [ ] **Step A2.2:** 跑 `npm run lint`
- [ ] **Step A2.3:** commit `feat(mobile): add LangChip component (visual only; i18n wire-up deferred)`

---

### Task A3: ProductNav 移动断点收紧

**Why:** 当前 ProductNav 在移动端只是隐藏中间 tab pill 和"创作"按钮，但仍渲染整个顶栏（含 T 徽章 + 登录按钮）。Landing demo 要的移动版顶栏在 hero 内部用 `<LangChip>` + serif italic 品牌；discover / history / workshop / world-detail 直接用 `<MobileTopBar>`。

**结论：移动端不渲染 ProductNav 本体。**桌面端保持不动。

**Files:**
- Modify: `frontend/components/ProductNav.tsx`

- [ ] **Step A3.1:** 在 `ProductNav` 函数组件最外层 `<motion.header>` 加 `className="pn-desktop-only"`（或新增 class），在文件底部 `<style jsx global>` 块里追加：

```css
@media (max-width: 768px) {
  .pn-root { display: none !important; }
}
```

并把 `<motion.header>` 加上 `className="pn-root"`。

- [ ] **Step A3.2:** 启动 `npm run dev`，375px 检查：landing 顶部不再出现 T 徽章 + TaleAlive + 登录按钮（接下来 Stage B 会在 landing 内部叠回品牌 + LangChip）
- [ ] **Step A3.3:** 切回 1280px，桌面端 ProductNav 正常显示
- [ ] **Step A3.4:** commit `feat(mobile): hide ProductNav on mobile (mobile chrome takes over)`

---

## Stage B · Landing `/`

> Demo: `homepage-mobile-demo.html`
> Current: `app/page.tsx`（1076 lines）—— 含 hero / modes section / steps / footer 等多个 section，桌面优先。

### Task B1: Hero 移动版

**Files:**
- Modify: `app/page.tsx`

**Spec（对齐 demo `.hero` / `.pnav` / `.continue-chip` / `.hero-content`）:**
- Hero 高度移动端 = `min(100dvh, 720px)`（桌面保留 `100dvh`）
- 在 hero 内部最顶部叠层渲染：
  - 左：serif italic 20px brand `<span class="brand-dot" />TaleAlive`（6×6 香槟金圆点）
  - 右：`<LangChip />`
  - 容器：`position: absolute; top: env(safe-area-inset-top, 0); padding: 14px 20px; z-index: 90; display:flex; justify-content:space-between`
- Continue chip（仅当 user 已登录且有 `lastSessionId`）：`position: absolute; top: 76px; left: 20px`，胶囊形：28px 圆头像 + `继续 · 落雁山` + `→`。**无 session 时不渲染**
- Hero 文案区移动端：
  - eyebrow：`TALEALIVE · AI 互动叙事引擎` + 香槟金小圆点
  - h1：移动端 `font-size: 44px`，2 行，italic 香槟金部分用 `<em>`（CSS `font-style: italic; color: var(--lv-accent)`）
  - lead：14px / lh 1.75，最多 320px 宽
  - 双 CTA：移动端**横排**（demo 是横排，不是 demo 注释里说的"纵向堆叠"——以 demo 实际 HTML 为准，flex-row 各 flex:1，48px 高，圆胶囊；主按钮 `background: var(--lv-ink); color: var(--lv-bg)`，次按钮 ghost 香槟金边）
  - cover indicator：左 dot 组（6 dots，active 24×2 px 香槟金）+ 右 mono 小字 `<glyph>雨</glyph> 雨夜·新宿1997`，靠右
- 移动端**移除 ScrollCue**（桌面保留）
- 现有桌面 hero 结构全部用 `@media (min-width: 769px)` 包住或保留，移动版用单独 JSX 分支：
  - 简化策略：在同一个 hero JSX 里用 CSS 切换两套布局；或在 `app/page.tsx` 顶部加 `useMediaQuery` 钩子按断点切。**优先 CSS 切**（避免 hydration mismatch）
- 数据：`lastSessionId` / `lastWorld` 从 `useAuthStore` + TanStack Query 取最近 session（参考现有 history 页查询）；如 query 未就绪则不显示 chip

- [ ] **Step B1.1:** 在 `app/page.tsx` 内部，hero section JSX 上挂 class `lv-hero`，在文件末尾或全局 css 添加 `@media (max-width: 768px) .lv-hero { ... }` 重写：高度、padding、布局
- [ ] **Step B1.2:** 在 hero 顶部新增叠层 mobile chrome（brand + LangChip），仅 `@media (max-width: 768px)` 可见（class `lv-hero-mobile-chrome`，桌面 `display:none`）
- [ ] **Step B1.3:** 在 hero 顶部新增 continue chip 叠层，仅 user 登录 + 有 session 时渲染，class `lv-hero-continue-chip`，移动端 `display:flex`，桌面 `display:none`（桌面端 hero 已有其他 continue affordance）
- [ ] **Step B1.4:** Hero 文案区移动端重写 CTA 区为横排两按钮（48px / flex:1 / gap:10px）
- [ ] **Step B1.5:** Cover indicator 移动端单行排版（demo `.cover-indicator` 完整对齐）
- [ ] **Step B1.6:** DevTools 375 / 414 / 1280 三个断点目测对齐 demo
- [ ] **Step B1.7:** commit `feat(landing/mobile): rebuild hero per app-first demo`

---

### Task B2: Modes section 移动版

**Spec（对齐 demo `.modes-sec` + `.mode-card.script` / `.mode-card.free`）:**
- 移动端纵向堆叠两卡（桌面保留 grid 双列）
- 每卡：
  - 圆角 14px，padding 18/16，1px 边
  - 剧本卡：`border: 1px solid rgba(223,194,144,0.18); background: linear-gradient(180deg, rgba(223,194,144,0.05) 0%, var(--lv-bg-1) 60%)`
  - 自由卡：`border: 1px solid rgba(174,180,184,0.16); background: linear-gradient(180deg, rgba(174,180,184,0.045) 0%, var(--lv-bg-1) 60%)`
  - 顶部右角 corner-glyph：剧本 `◆` 香槟金 / 自由 `◇` 银雾，serif 20px opacity 0.85
  - mode-eyebrow（mono 9.5px caps）+ serif 18px title + bullets list（左 6×1 line 边 + 5px padding + 12.5px / lh 1.55）+ inline pill CTA（7×14 padding，圆胶囊，1px line-2 边，body 12.5px）
- 标题改为情绪向："追到一个结局" / "活到你想停的那天"

**Files:**
- Modify: `app/page.tsx`（modes section 块）

- [ ] **Step B2.1:** 找到 modes section JSX，移动端重写两卡为 demo HTML 结构
- [ ] **Step B2.2:** 375 / 1280 双断点检查
- [ ] **Step B2.3:** commit `feat(landing/mobile): restyle modes section with corner glyphs + mode-tinted gradients`

---

### Task B3: Steps + demo preview 移动版

**Spec（对齐 demo `.steps-sec` + `.step-row` + `.demo-preview`）:**
- 三步移动端纵向：每行 grid `36px 1fr` 16 gap；序号 32×32 香槟金边 + mono 12px 数字（圆角 8px）；标题 serif 17px / 描述 13px
- 演示卡（**替代桌面 MultiSceneDemo**）：
  - `background: var(--lv-bg-stage)`，1px line 边，圆角 16px，padding 18/18/16
  - 头部 mono caps `◆ 第三幕 · 22:14`（香槟金 ◆）+ 右上 live-dot（6×6 香槟金，pulse 1.6s）
  - NPC 标记（mono 9px caps）+ narrator text（13px / lh 1.75，内嵌 `<em>` 用 serif italic 香槟金）+ player text（serif italic 13px 右对齐）+ 香槟金光标 blink

**Files:**
- Modify: `app/page.tsx`

- [ ] **Step B3.1:** 移动端隐藏现有 MultiSceneDemo（如有），新增静态 demo 卡 JSX，`@media (min-width: 769px) { display: none }`
- [ ] **Step B3.2:** Steps grid 移动端 force 单列 + 序号方框样式
- [ ] **Step B3.3:** commit `feat(landing/mobile): swap MultiSceneDemo for static play preview card on mobile`

---

### Task B4: Footer + 移除 ScrollCue

**Files:**
- Modify: `app/page.tsx`

- [ ] **Step B4.1:** Footer 移动端：3 link + 单行 mono 极小 © 字。padding `32px 24px 24px`，顶部 1px 极淡线
- [ ] **Step B4.2:** 找到 ScrollCue 组件（如有），加 `@media (max-width: 768px) { display: none }`
- [ ] **Step B4.3:** commit `feat(landing/mobile): finalize footer + drop scroll cue on small screens`

---

## Stage C · Discover `/discover`

> Demo: `discover-mobile-demo.html`
> Current: `app/discover/page.tsx`（906 lines）

### Task C1: 顶栏 + 搜索/筛选/题材 chip

**Spec:**
- 顶部用 `<MobileTopBar left={undefined} right={<MobileIconButton><User/></MobileIconButton>} />`（参考 demo `.topbar`：左 brand、右用户）—— 实际 demo brand 在左，user 图标在右。
  - 实际 demo 是左 brand + 右 user 图标，没有 left icon。所以重新设计 prop：
    - 用法：`<MobileTopBar variant="brand-left" right={<MobileIconButton .../>} />` 或干脆 left 为 brand，right 为 icon。
    - **决策：** MobileTopBar 改成 3 列 grid，但允许 left 传 brand 节点。Discover 用法：`<MobileTopBar left={<BrandMark />} right={<MobileIconButton aria-label="我的"><UserIcon /></MobileIconButton>} brand={null} />`。或者更简单：让 MobileTopBar 接 `variant: "centered" | "brand-left"`。
    - **最终决策：** 把 brand 放成自带的 center，discover 在 left 位放空，right 位放 user icon。 demo 实际是 `.topbar` 用 `justify-content: space-between` 而非 grid —— 跟 history/workshop demo 的 grid 不同。**discover 单独处理顶栏**：自定义 `<div class="discover-topbar">` 不用 MobileTopBar。

- 搜索行：search-box（高 44px，圆胶囊，`background: rgba(255,255,255,0.045)`，左 SVG + placeholder「搜索世界、题材、时代」）+ filter pill（mono 10px caps「筛选」，44px 高）
- chip row：横滑无 scrollbar，每个 chip 圆胶囊 9/15 padding，active 态 `background: rgba(223,194,144,0.12); border-color: rgba(223,194,144,0.28)`，文字 mono 10px caps

**Files:**
- Modify: `app/discover/page.tsx`

- [ ] **Step C1.1:** 移动端断点下：top bar / search row / chip row JSX 写出。桌面端保留现有搜索/筛选实现，用 CSS 切显示
- [ ] **Step C1.2:** 接入现有 search state + chip filter state（不引入新 store）
- [ ] **Step C1.3:** 375 检查横滑流畅；commit `feat(discover/mobile): app-first top bar + search + filter chip row`

---

### Task C2: Spotlight 卡 + view-toggle + 垂直 world list

**Spec:**
- Spotlight：高 188px，圆角 22px，封面 + 双层渐变 + 香槟金径向高光；内部左下 eyebrow（香槟金 mono 9px）+ serif 24px title + 12px desc；右下 CTA 胶囊「▶ 进入」（米白底 / `var(--lv-bg)` 字）。Data：取 `useQuery` 拿到的世界列表第一项作为 spotlight（或运营字段 `is_featured`，按现有 API 实际字段）
- section head：左 serif 21px「全部世界」+ 右 view-toggle（2×34 圆胶囊：网格 / 列表，默认列表态高亮）
- world list：纵向 9px gap，每卡 grid `108px 1fr`、min-height 130px、圆角 20px
  - 左封面：背景图 + 暗渐变；左上 mode-badge 胶囊（`◆` 香槟金 / `◇` 银雾，22px 高，黑底 blur）
  - 右内容：title row（mono 9px caps tag 如 `悬疑 · 民国`）+ serif 20px title（单行省略）+ 12px desc（2 行省略）+ bottom row（mono 9px caps meta + 胶囊「进入」34px）
- View-toggle 切到网格态时**保留**现有桌面网格卡（`WorldCard.tsx`）的移动版，2 列；默认仍是列表

**Files:**
- Modify: `app/discover/page.tsx`
- Possibly modify: `components/WorldCard.tsx`（如果列表卡复用，否则单独写）

- [ ] **Step C2.1:** Spotlight 卡 JSX + 样式
- [ ] **Step C2.2:** section head + view-toggle
- [ ] **Step C2.3:** vertical world card 写好，复用现有 list query 数据
- [ ] **Step C2.4:** 移动端默认列表，view-toggle 切网格态仍走桌面 WorldCard（2 列）
- [ ] **Step C2.5:** commit `feat(discover/mobile): spotlight + vertical world list with 108px covers`

---

## Stage D · History `/history`

> Demo: `history-mobile-demo.html`
> Current: `app/history/page.tsx`（1091 lines）

### Task D1: 顶栏 + segmented + 继续游玩卡

**Spec:**
- 用 `<MobileTopBar left={<MobileIconButton aria-label="搜索"><Search/></MobileIconButton>} right={<MobileIconButton aria-label="筛选"><Filter/></MobileIconButton>} />`（brand 自带 center）
- segmented：3 列 grid 4 gap，外圆胶囊 4px padding；每段 34px 高、mono 9px caps；active 态米白底 / `var(--lv-bg)` 字
- 继续游玩 section：title row「继续游玩」serif 21px + 右 mono 9px `N active`
- continue card：130px 高、grid `108px 1fr`、圆角 20px、`border: 1px solid rgba(223,194,144,0.16)`，背景为香槟金极淡 wash + 半透明米白叠加
  - 左封面 + 剧本/自由 mode-badge
  - 右：mono 9px caps `4 小时前 · 第 7 回合` + serif 20px 世界名（单行省略）+ serif 12px 引文（2 行省略）+ 底部 progress 条（70×3 px，剧本模式才显示）+ 「继续」按钮（米白胶囊，34px 高）

**Files:**
- Modify: `app/history/page.tsx`

- [ ] **Step D1.1:** Top bar + segmented（filter state 沿用已有）
- [ ] **Step D1.2:** Continue card（用现有「进行中 session」query 数据）
- [ ] **Step D1.3:** commit `feat(history/mobile): app-first top bar + segmented + continue card`

---

### Task D2: 最近结束 list

**Spec:**
- section title row「最近结束」+ `N done` meta
- history-row：圆角 19px、1px line 边、padding 14/14/12，**无封面**（区别于 continue card）
  - row-top：mono 9px caps date + 右侧 `回看` 12px 链接
  - row-title：serif 20px（结局/会话标题）
  - row-desc：12px / lh 1.42 / 2 行省略
  - row-foot：左 mono caps 世界名 + 右 mono caps（剧本则香槟金「证据 N%」/ 自由则「N 回合」，自由模式不强行显示百分比）
- 列表末尾「已经到底了」sentinel

**Files:**
- Modify: `app/history/page.tsx`

- [ ] **Step D2.1:** 已结束 query + 渲染 history-row
- [ ] **Step D2.2:** Sentinel
- [ ] **Step D2.3:** commit `feat(history/mobile): ended sessions list (text-only, no thumbs)`

---

## Stage E · Workshop `/workshop`

> Demo: `workshop-mobile-demo.html`
> Current: `app/workshop/page.tsx`（1849 lines）—— 最长，但 demo 只覆盖**列表入口**，编辑器/生成页保持桌面

### Task E1: 顶栏（含头像）+ create card + 生成中 progress card

**Spec:**
- `<MobileTopBar left={<MobileIconButton aria-label="搜索"><Search/></MobileIconButton>} right={<AvatarButton />} />`
  - AvatarButton：42px 圆形，渐变底（`radial-gradient(circle at 34% 24%, rgba(245,242,235,0.88), transparent 18%), linear-gradient(135deg, #3e3325, #8d7b64 48%, #171412)`），13px 大写字母（用户首字母）
  - 点击：弹 vaul Drawer（bottom sheet），内容暂时占位「账户 / 语言 / 登出 / 管理入口」—— 实际项可暂时只有「登出」+ TODO comment，避免外壳推进被 sheet 内容阻塞
- create card：116px min-height，圆角 22px，香槟金 wash 渐变背景，padding 15/16/14
  - kicker mono 10px caps 香槟金「创作工坊」
  - serif 24px「继续搭建你的世界」
  - 13px desc / lh 1.55「从草稿继续，或新建一个世界 / 剧本」
  - 右下角「+ 创建」胶囊按钮（米白底，绝对定位 right:14 bottom:14，38px 高）
  - 点击：bottom sheet 显「生成世界 / 生成剧本」两项，路由到现有 `/workshop/generate/world` / `/workshop/generate/script`
- 生成中 progress card（**仅当有 in-progress generation task 时渲染**）：圆角 18px、padding 10/13、grid `1fr auto`；左 serif 17px 标题 + 12px meta；右香槟金胶囊 mono 9px caps 「42%」
  - 数据：现有 `generation_tasks` query（参考桌面 workshop 实现）

**Files:**
- Modify: `app/workshop/page.tsx`

- [ ] **Step E1.1:** 顶栏 + AvatarButton（drawer 内容占位）
- [ ] **Step E1.2:** create card + bottom sheet 触发
- [ ] **Step E1.3:** 生成中 progress card（条件渲染）
- [ ] **Step E1.4:** commit `feat(workshop/mobile): top bar with avatar + create card + in-progress task pill`

---

### Task E2: segmented + 草稿/世界/剧本 列表

**Spec:**
- segmented：3 列「草稿 / 世界 / 剧本」（**移动端默认草稿 tab**；桌面端保持现有顺序）
- section title row：左 serif 21px「最近草稿/全部世界/我的剧本」+ 右 `N items` meta
- work-card：130px min-height、grid `108px 1fr`、圆角 20px
  - 左封面，左上 status-badge（草稿 = `--lv-warn` 黄 / 已发布 = `--lv-green` / 剧本 = 香槟金）
  - 右：mono 9px caps meta（`世界 · 2 小时前` / `剧本 · 已发布`）+ serif 20px title（单行省略）+ 12px desc 2 行省略
  - 底：`small-meta`（如 `8 NPC · 3 地点`）+ 右侧「编辑/查看」34px 胶囊 + `···` more 按钮（34×34 圆）
- more 按钮点击：弹 popover「重命名 / 复制 / 删除」（Radix Popover；删除用 ConfirmDialog 二次确认）

**Files:**
- Modify: `app/workshop/page.tsx`

- [ ] **Step E2.1:** segmented + 默认 tab 切到「草稿」
- [ ] **Step E2.2:** work-card 列表（三种状态：draft / world / script），用现有 query
- [ ] **Step E2.3:** more popover
- [ ] **Step E2.4:** commit `feat(workshop/mobile): segmented tabs + work-card list with status badges`

---

## Stage F · World detail `/worlds/[id]`

> Demo: `world-detail-mobile-demo.html`
> Current: `app/worlds/[id]/page.tsx`（477 lines）

### Task F1: Hero（278px）+ 顶栏叠层 + mode badges

**Spec:**
- hero 高度移动端 = 278px（桌面保留现有高度）
- 顶栏叠层：`<MobileTopBar left={<MobileIconButton aria-label="返回"><ChevronLeft/></MobileIconButton>} right={<MobileIconButton aria-label="更多"><MoreVertical/></MobileIconButton>} />`
  - 注意：MobileTopBar 在 hero 内部 `position: absolute; top:0; left:0; right:0`，需要可控的背景透明态（icon 按钮 background 调成 `rgba(8,8,10,0.36)`，加 backdrop blur 16px）
  - **决策：** MobileTopBar 加 `variant: "transparent"` prop，透明时无 `padding-top` 由父容器控制，icon-btn 背景换深玻璃
- hero 内容（左下）：
  - meta-line：题材 · 时代 · 难度 · 时长（mono 9px caps，用 `·` 灰点分隔）
  - serif 36px title（白色）
  - 13px desc 2 行省略
  - mode-badges 行：两个胶囊「◆ 剧本模式 / ◇ 自由探索」，仅作能力标签（**不可点击选模式**，模式选择在 start 流程做）

**Files:**
- Modify: `app/worlds/[id]/page.tsx`
- Modify: `components/MobileTopBar.tsx`（加 transparent variant）

- [ ] **Step F1.1:** MobileTopBar 加 `variant?: "default" | "transparent"`，transparent 时透明背景 + icon 深玻璃
- [ ] **Step F1.2:** hero 移动版重写，含叠层顶栏 + 内容
- [ ] **Step F1.3:** mode badges 行（非交互）
- [ ] **Step F1.4:** commit `feat(world-detail/mobile): 278px hero with overlay top bar + mode capability badges`

---

### Task F2: 剧本 carousel + 角色 strip

**Spec:**
- 剧本 carousel：横滑 snap，每卡 224px 宽 / 184px min-height，圆角 18px
  - 顶部 cover 98px 高、左上 script-pill「◆ 主线/支线/短篇」香槟金
  - 下方 card-copy：mono 9px caps「真相线 · 难度 3」+ serif 18px title（单行省略）+ 11.5px desc（2 行省略）+ 底部 mono 9px caps「45 min」
- 角色 strip：横滑，每个角色 78px 宽：64×64 圆头像（1px line 边）+ serif 15px name + 10.5px meta（2 行省略）
- 数据：现有 `scripts` / `characters` query
- **如果世界无剧本：** 隐藏剧本 section，hero 下直接接角色

**Files:**
- Modify: `app/worlds/[id]/page.tsx`

- [ ] **Step F2.1:** 剧本 carousel JSX + `overflow-x: auto; scroll-snap-type: x mandatory; scroll-padding-left: 4px` + 各卡 `scroll-snap-align: start`
- [ ] **Step F2.2:** 角色 strip
- [ ] **Step F2.3:** 无剧本世界的 fallback 分支
- [ ] **Step F2.4:** commit `feat(world-detail/mobile): scripts carousel + playable roles strip`

---

### Task F3: 固定 CTA dock + 底部 tab 共存

**Spec:**
- 底部固定 CTA dock：`position: fixed; left:0; right:0; bottom: calc(76px + env(safe-area-inset-bottom))`（BottomTabBar 高 76px+safe-area），渐变上 fade-in 背景
- 主按钮：52px 高、圆胶囊、米白底、serif weight 700 + 14px、`开始游玩 →`，box-shadow 黑色 deep
- 点击：路由 `/worlds/[id]/start`
- 内容滚动区底部 padding 加 `144px` 给 dock + tab 让位

**Files:**
- Modify: `app/worlds/[id]/page.tsx`

- [ ] **Step F3.1:** CTA dock JSX + 桌面端 `@media (min-width: 769px) { display: none }`
- [ ] **Step F3.2:** 滚动区底部 padding 调整
- [ ] **Step F3.3:** commit `feat(world-detail/mobile): fixed CTA dock above bottom tab`

---

## Stage G · Start flow `/worlds/[id]/start`

> Demo: `start-mobile-demo.html`
> Current: `app/worlds/[id]/start/page.tsx`（387 lines）
> 关键：BottomTabBar 已在 `pathname.includes("/start")` 时自动隐藏 —— 不动

### Task G1: 模糊背景 + 顶栏（返回 + pips 进度）

**Spec:**
- 全屏背景：当前世界封面图，blur 32px / saturate 138% / opacity 0.72 + 渐变叠加
- 顶栏：左 back 胶囊（`← 返回世界` 12px 14px padding 圆胶囊 玻璃底），右 pips 进度点（4 个，已完成态 22×2 米白 / 未完成 8×2 半透明）

**Files:**
- Modify: `app/worlds/[id]/start/page.tsx`

- [ ] **Step G1.1:** 全屏背景容器（blurred world cover）+ 渐变叠加
- [ ] **Step G1.2:** 顶栏 back pill + pips（接现有 step state，4 步：模式 / 剧本 / 角色 / 确认；自由模式跳过剧本步骤，pips 显示 3 步）
- [ ] **Step G1.3:** commit `feat(start/mobile): blurred world cover background + back pill + step pips`

---

### Task G2: Step 1 选模式 + Step 4 确认

**Spec:**
- 中部内容居中（vertical center），最大宽 292px
- 标题块：eyebrow mono 10px caps + serif 28px title + 12px desc（最大宽 250px）
- 模式列表（step 1）：每行 list-option：grid `34px 1fr 22px`，68px min-height，圆角 18px，1px line 边
  - 左 number `01/02` mono 10px caps
  - 中 title「剧本模式 ◆ / 自由探索 ◇」14px 600 + 11.5px desc
  - 右 arrow `→`
  - active 态：border `rgba(245,242,235,0.62)`，background `rgba(255,255,255,0.07)`
- 确认页（最后一步）：去掉标题，只留：
  - mono 10px caps label「想说点偏好（可选）」
  - 46px 圆胶囊 input（placeholder「如：节奏慢一点 / 多内心独白」）
  - 48px 米白胶囊「进入」按钮

**Files:**
- Modify: `app/worlds/[id]/start/page.tsx`

- [ ] **Step G2.1:** Step 1 模式列表 JSX 移动版
- [ ] **Step G2.2:** Step 4 确认页 JSX 移动版
- [ ] **Step G2.3:** commit `feat(start/mobile): step 1 mode + step 4 confirm screens`

---

### Task G3: Step 2 剧本 / Step 3 角色（media-strip 横滑）

**Spec:**
- media-strip：横滑 snap，每卡 204×274 px，圆角 18px
- 卡内：背景图覆盖（渐变叠加 + 底部信息）
  - serif 20px title
  - chips 行：题材/难度/时长（圆胶囊小标 10px）
  - 11.5px desc（3 行省略）
- 角色卡 avatar-card 变体：顶部居中圆形高光叠加（`radial-gradient(circle at 50% 26%, rgba(245,242,235,0.18), transparent 26%)`）
- active 态：白色边框 `rgba(245,242,235,0.66)` + inset 1px shadow
- 自由模式时：跳过 step 2，直接到 step 3
- 选完后页面底部出现「下一步」按钮（48px 圆胶囊米白）—— demo 没画但需要：点击当前 active 卡 OR 显式 next 按钮，两种交互都接受

**Files:**
- Modify: `app/worlds/[id]/start/page.tsx`

- [ ] **Step G3.1:** Step 2 剧本 strip
- [ ] **Step G3.2:** Step 3 角色 strip
- [ ] **Step G3.3:** 自由模式跳过剧本步骤的逻辑
- [ ] **Step G3.4:** commit `feat(start/mobile): script + role media strips with snap scroll`

---

## Stage H · 收尾

### Task H1: i18n 文案对接

**Spec:**
- 新增的所有文案（"继续 ·"、"创作工坊"、"继续搭建你的世界"、"开始游玩"、"想说点偏好（可选）"等）补到 `i18n/zh.json`，用 `t('xxx')` 取
- 英文 `i18n/en.json` 同步补占位

**Files:**
- Modify: `frontend/i18n/zh.json` / `frontend/i18n/en.json`
- Modify: 各页面引用文案处

- [ ] **Step H1.1:** 把新增硬编码中文文案抽到 `zh.json`
- [ ] **Step H1.2:** 同步 `en.json` 占位（英文翻译）
- [ ] **Step H1.3:** commit `feat(mobile/i18n): externalize new mobile copy strings`

---

### Task H2: LangChip 接 next-intl 真切换

**Files:**
- Modify: `components/LangChip.tsx`
- 可能改: `app/layout.tsx`（locale switch 持久化，cookie 或 localStorage）

- [ ] **Step H2.1:** LangChip 内部 onClick 触发 locale 切换（cookie `NEXT_LOCALE` 写入 + `router.refresh()`）
- [ ] **Step H2.2:** layout.tsx 从 cookie 读 locale，传给 `NextIntlClientProvider`
- [ ] **Step H2.3:** commit `feat(mobile/i18n): wire LangChip to next-intl locale switching`

---

### Task H3: 移动端整体 QA

- [ ] **Step H3.1:** Chrome DevTools 375 / 414 / 768 三个断点逐页过：landing / discover / history / workshop / world-detail / start
- [ ] **Step H3.2:** 真机过一次（iPhone Safari 或 Android Chrome），关注：
  - safe-area-inset 正确避刘海 / Home indicator
  - 触摸目标手感
  - 横滑 snap 流畅度
  - hero 卡顿 / Ken Burns 动画性能
- [ ] **Step H3.3:** `npm run lint:strict` + `npm run build` 全绿
- [ ] **Step H3.4:** PR 模板 `.github/pull_request_template.md` 自检表勾完
- [ ] **Step H3.5:** commit `chore(mobile): final qa pass`

---

## Self-Review

**Spec coverage:**
- ✅ Landing demo → Stage B (B1-B4)
- ✅ Discover demo → Stage C (C1-C2)
- ✅ History demo → Stage D (D1-D2)
- ✅ Workshop demo → Stage E (E1-E2)
- ✅ World detail demo → Stage F (F1-F3)
- ✅ Start demo → Stage G (G1-G3)
- ✅ 共享 chrome → Stage A (A1-A3)
- ✅ 收尾 → Stage H

**类型一致性：**
- `MobileTopBar` 在 A1 定义 props（left/right/brand），在 F1 扩展 `variant: "default" | "transparent"` —— 在 F1 task 中显式记录扩展，未来 task 用同一签名
- `LangChip` 在 A2 视觉态、H2 接真实 i18n —— 公开 API 不变

**Placeholder 扫描：**
- ❌ workshop AvatarButton sheet 内容在 E1 标记"暂时只有登出 + TODO"——这是有意的范围决策，sheet 内容详细 spec 在后续 plan（不构成本 plan placeholder）
- 其余 task 步骤均有具体代码/文件/spec

**Gap 提示：**
- Landing demo 注释提到「未登录用户也不加登录 banner」+「登录入口在 lang button 旁可考虑加，需单独决」—— 本 plan 不加登录入口，保留待决
- 移动端 `/login` 页 demo 未提供，本 plan 不动 login 页

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-26-mobile-app-shell.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 我每个 Stage 派一个 fresh subagent，stage 间 review

**2. Inline Execution** - 在当前 session 顺序执行 Stage A → H，每个 Stage 完成 checkpoint 给你过

**Which approach?** 推荐 1，因为每个 stage 涉及多文件 + 视觉验证，subagent 隔离上下文更稳；但如果你想边做边给反馈调方向，选 2 更顺手。
