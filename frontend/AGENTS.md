<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# 前端说明（参考，不是律法）

> 这一份是 InkWild 前端的**唯一参考文档**，取代原先散落在 `docs/design/` 的 visual-principles / frontend-spec / play-mode-spec / audit 几份规范（已归档到 `docs/_archive/`）。
>
> **它是参考，不是律法。** 视觉判断归设计师（jie）的眼睛，不靠机器拦字号/间距/圆角。唯一会卡 CI 的硬规则只有一条（见下「机器强制」）。
>
> **真相源是代码，不是这份文档。** 任何数值/类名/组件行为，以下面三处实物为准；本文与代码冲突时，**以代码为准**：
> | 真相 | 在哪 |
> |---|---|
> | 设计令牌（颜色/字号/圆角/间距/z-index/动效的真实值） | `frontend/app/globals.css` 的 `.lv-theme` 块（`--lv-*` 定义，约 line 1440+） |
> | 字体与字号实物样张 | `npm run dev` 后访问 `/dev/type` |
> | 组件/页面的现成写法（卡片、nav、表单、play 布局等） | 直接看对应组件源码，别照本文复述 |

当前视觉系统：**v2.3 cinematic gold**（香槟金 `#dfc290` + 暖象牙 `#f5f2eb`，暗影底 `#08080a`）。主入口页面 `/`（landing）、`/discover`、`/history`、`/workshop`、`/login`、`/worlds/[id]`、`/play/[id]` 都已统一到这套。

> Admin 控制台（`admin-frontend/`，端口 3001）**不复用主站视觉系统**——桌面优先、冷蓝低圆角工程化后台，基线见 `../InkWild Admin.html` + `../docs/plans/admin-console-2026-05.md`。

---

## 机器强制（唯一硬规则）

ESLint 只锁一条（CI 会挂）：**禁止引用旧 token** `var(--font-size-*)` / `var(--ta-*)` / `var(--color-accent)`，统一用 `var(--lv-*)`。见 `eslint.config.mjs` 头注释。

其余全是**约定**，不上 lint，由 PR 走查 + 设计师眼睛把关。约定违反不会被机器拦，但 review 会被指出。

---

## 视觉气质（判断基线）

对标 **Netflix / Apple TV+ / Letterboxd 这一脉**：暗黑底、靠封面墙说话、UI 隐形、克制的衬线点缀、留白多、电影感、文字承载得住而不靠色块堆肌理。

**不是**：AI Dungeon（UGC 集市气质）/ Steam·itch.io（密度大平台感）/ Riot·暴雪（强 hero、橙红 CTA、游戏感）。

**同类元素全站长一样**：世界封面卡、save 卡、filter chip、CTA 按钮——同类型组件不要每页重新发明一套。判断标准：「如果在另一个页面把这个元素重画了一套，能一眼看出不一致吗？」能 → 不对。

---

## 设计令牌速查

> 下表是 `globals.css` 当前实测值，方便速查；**以 `globals.css` 为准**，值变了以那边为准。

**颜色**（`--lv-*`）

| 用途 | token | 值 |
|---|---|---|
| 页面底色 | `--lv-bg` | `#08080a` |
| 游戏舞台底（更深一档） | `--lv-bg-stage` | `#050507` |
| 卡片底 / 微抬起面 | `--lv-bg-1` / `--lv-bg-2` | `#0d1014` / `#15181c` |
| 主文本（暖象牙） | `--lv-ink` | `#f5f2eb` |
| 次级 / 辅助 / 边框占位 / 深块 | `--lv-ink-2/3/4/5` | `#c4bcae` / `#8c8273` / `#4a4338` / `#1f1c18` |
| 边线 | `--lv-line` / `--lv-line-2` | `rgba(255,255,255,.06)` / `.10` |
| 主色（香槟金） | `--lv-accent` | `#dfc290` |
| 自由模式辅助（银雾，事实上少用） | `--lv-accent-2` | `#aeb4b8` |
| 卡片容器 | `--lv-card-bg / -border / -shadow`（含 `-hover`） | 见 globals |
| 封面 overlay | `--lv-cover-overlay-light` / `-cinematic` | 见 globals |
| 状态色（仅反馈，不装饰） | `--lv-danger` / `--lv-warn` / `--lv-success` | `#ef8276` / `#c9a36a` / `#7fb091` |

**金色是语义色，不是装饰色。** 大体只用在：品牌标识、运营/spotlight 标签、active 选中态、focus ring、完美结局语义。约定上**不要** hover 把背景/边框/文字/阴影切金，不要给普通卡片/按钮描金渍。CTA 默认用 ivory `--lv-ink` 底而非金底。具体怎么落，看 `ProductNav` / 卡片组件现成写法。

**字号**（`.lv-t-*` 工具类，对应 `--lv-t-*`）—— 实测 **10 档**：

```
display    clamp(48px, 9vw, 112px)   serif   Hero 大标题（每页 ≤1）
h1         clamp(28px, 4vw,  48px)   serif   页面主标题
h2         clamp(20px, 2.4vw, 28px)  serif   区块/section 标题
h3         clamp(16px, 1.4vw, 18px)  sans    卡片/小区块标题
narrative  clamp(15px, 1vw,  17px)   sans    叙事正文（line-height 1.85）
body       15px                      sans    UI 正文（按钮/表单/气泡）
compact    13px                      sans    紧凑正文（移动端密集卡片/列表行）
meta       12px                      sans    辅助/时间戳/状态
caps       11px                      mono    大写小标签（uppercase + ls 0.2em）
micro      10px                      mono    极小标记（每页 ≤3）
```

写代码用 `.lv-t-display` / `.lv-t-h1` / … / `.lv-t-compact` / `.lv-t-meta` / `.lv-t-caps` / `.lv-t-micro`（叙事长段另有 `.lv-t-body-long`）。三套字体：serif（Cormorant + Noto Serif SC）只给标题/引文/卡片世界名；sans（Inter + PingFang SC）给其余一切，含 play 叙事段；mono（JetBrains Mono）给数字/时间戳/id/caps·micro 标签。

**圆角 / 间距 / z-index / 动效**

```
圆角     --lv-r-card 16  /  --lv-r-input 10（仅表单控件）  /  --lv-r-pill 9999
间距     --lv-s-1/2/3/4/6/8/12/16/24 = 4/8/12/16/24/32/48/64/96
z-index  base 1 / sticky 50 / drawer 100 / modal 200 / toast 300 / overlay 400
动效     --lv-dur-fast 200ms（常规上限）；cinematic 例外仅 hero 与游戏结局
容器宽   --lv-max-w 1320  /  --lv-max-w-read 760（长文/play 阅读区）
缓动     --lv-ease cubic-bezier(0.2,0.7,0.2,1)
```

`prefers-reduced-motion` 下 cinematic 时长会降到 200ms（globals 已处理），新动效要保证降级不出戏。

---

## 三态约定（loading / empty / error）

- **加载态**：不写「正在加载…」死文字。用 Branch logo pulse（`<LoadingPulse variant="branch" />`）；play 思考态走 `StreamingStatusRail`，文案由后端真实里程碑驱动。
- **空态**：给引导（去哪、做什么），不要只放一句「暂无数据」。
- **错误态**：红字**必须**配文字描述或图标，不能只靠颜色传达。

---

## Play 页（沉浸优先的局部例外）

play 是停留最久的页面，沉浸优先于内容密度。相对其它页的**例外**：

- 阅读区收窄到 `--lv-max-w-read`（760）而非全站 1320
- 顶部用 `GameHeader`（折叠态），**不用 ProductNav**
- 移动端 `BottomTabBar` 自动隐藏（`components/BottomTabBar.tsx` 对 `/play/` 返回 null）
- 案件板：桌面右侧浮窗 / 移动底部上推抽屉（`drawerMode` 切换，见 `lib/play-layout.ts` + `play/[id]/page.tsx`）
- 结局 cinematic 长动效允许（curtain → narrative → credits → actions，可点击跳过）
- 毛玻璃 backdrop-filter 用于 header 浮层 / drawer / case-hologram

**不豁免**：字号档、`--lv-*` 颜色、圆角、z-index、触摸目标 ≥ 44px、focus ring、reduced-motion、文案克制——一律照常。

叙事段落细节（line-height 1.85、玩家动作 italic+缩进、角色名 caps、不做 IM 气泡、不做逐字 typewriter）以 `app/globals.css` 里 `play-message-*` 类和 play 组件实际写法为准。模式判断：`gameSession.script_id != null` → 剧本模式。

---

## 基础设施层（已就位，新页面/重构页面用这套，别每页重新发明）

| 关注 | 库 | 备注 |
|---|---|---|
| 数据获取 | `@tanstack/react-query` | Provider 见 `components/QueryProvider.tsx`，已挂 layout |
| 表单 | `react-hook-form` + `zod` + `@hookform/resolvers` | — |
| 动效 | Framer Motion (`motion/react`) | 统一预设在 `lib/motion.ts`（`lvStaggerContainer` / `lvStaggerItem` / `lvFadeUp` 等） |
| i18n | `next-intl` | 文案 `t('xxx')`，文件 `i18n/zh.json` + `i18n/en.json` |
| 复杂交互组件 | Radix（dialog/popover/toast）+ `vaul`（Drawer）+ `cmdk`（Command Menu） | 不引入 shadcn 整套，simple 组件继续手写 |
| PWA | `@serwist/next` | sw 源 `app/sw.ts`，manifest `public/manifest.webmanifest` |
| 错误上报 | `@sentry/nextjs` | DSN 用 `NEXT_PUBLIC_SENTRY_DSN` |
| 单测 | `vitest` + `@testing-library/react` + jsdom | `npm run test`；测试就近 `lib/*.test.ts` |

---

## 工程约定

- 谨慎 `"use client"`，只在需要交互或浏览器 API 时用
- 客户端状态：Zustand（`stores/`）；服务端状态：TanStack Query
- 流式：`fetch + ReadableStream`，**不用 `EventSource`**（cookie 认证约束）
- 只用 Tailwind，不引入 CSS Modules / styled-components；重复样式用 `<style jsx global>` 局部块（参考 `ProductNav.tsx` / `workshop/page.tsx`），别每节点 inline 60 行 style 对象
- 路由级页面只接 TanStack Query 真实数据；mock 仅限 hero 字段（标题/题材），不要虚假指标数字
- 主题色字段统一在 `globals.css :root` 唯一定义，不要 per-page override

## 移动端检查项（每个页面 PR 必做）

真正移动端优先：先 375px 设计，桌面是放大版。

- [ ] 375px 单手能用（DevTools 切 iPhone SE）
- [ ] 用 `100dvh` 不用 `100vh`，处理 `safe-area-inset-{top,bottom}`
- [ ] 触摸目标 ≥ 44px，不依赖 hover 表达状态
- [ ] play 页移动端单栏 + 底部抽屉（不是双栏挤压）
- [ ] 导航：移动底部 tab（首页/发现/创作/我，历史并入「我」+ `/history` 全量页），桌面顶部 `ProductNav`

## Dev 命令

```bash
npm install
npm run dev          # 端口 3000，被占用自动切 3001
npm run dev:fresh    # 清 .next 再 dev（HMR 异常时用）
npm run build        # 生产构建
npm run lint         # ESLint（仅锁旧 token）
npm run lint:strict  # 同上 + max-warnings=0
npm run test         # vitest 单测
```

dev server 默认 Turbopack，`darwin/arm64` native binding 缺失会自动回退；报错就显式 `npx next dev --webpack`。
