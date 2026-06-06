# 前端 v2.2 重构 · Master Implementation Plan

> 起草：2026-05-08
> 状态：草案，等用户 review
> 配套：
> - `docs/plans/frontend-refactor-2026-05.md`（产品级 vision，**不替换**）
> - `docs/design/visual-principles.md` v2.2（视觉原则，最高法）
> - `docs/design/frontend-spec.md` v2.2（token 值表，stage 0 实施蓝图）
> - 单 spec 只列**实施细节**，不复述哲学/规则。

---

## 0. 起点核对（真实状态 vs vision 文档声明）

| 阶段 | vision 文档声明 | 代码真实状态 |
|---|---|---|
| 0 type system 落地 | ✅ 已完成 | 🟡 部分完成：`.lv-theme` 块 + 全部 `--lv-*` token + 9 档 `.lv-t-*` 工具类 + 表单类 + 焦点环 + reduced-motion 都已写好（globals.css line 1190+）。**但**：①`.lv-theme` 没应用到 `<body>`，②body 还挂着旧 `bg-bg-primary text-text-primary` Tailwind 类 → 实际 lv-theme 对页面无效，③注释仍写 v2.1，④viewport meta 缺 `viewport-fit=cover` |
| 1 文档统一 | 🟡 进行中 | ✅ `visual-principles.md` `frontend-spec.md` `AGENTS.md` `CLAUDE.md` 都已 v2.2，**只剩 plan 文档自己的进度行没真实化** |
| 2 ESLint 上锁 | ⏳ | ❌ `eslint.config.mjs` 只有 next 默认配置 |
| 3 基础设施层 | ⏳ | ❌ `package.json` 只有 next/react/zustand/sentry。0/6 库装好 |
| 4 移动端布局 | ⏳ | ❌ |
| 5 page train | ⏳ | ❌ 现状有 230 处 `text-[Xrem]` 散在 33 个文件 |
| 6 play spec | ⏳ | ❌ |
| 7 PWA | ⏳ | ❌ |

**修订后真实施工顺序**：本 plan 以"代码真实状态"为准。Stage 0 的 token 落地是**第一个干**的事；vision 文档的进度行在 stage 1 顺手改。

**lib 测试现状**：`frontend/lib/*.test.ts` 有 10 个文件，`package.json` 没有 test 脚本，没装 vitest/jest——测试代码存在但跑不起来。stage 3 顺手把 vitest 装上让它们能跑。

**git 状态**：项目**不是 git repo**。每阶段交付不走 PR，按"自然 checkpoint"组织（写完 stage N、跑过该阶段验收、给用户看截图/总结）。

---

## 1. 阶段依赖图

```
                ┌─────────────────────────────────────┐
                │                                     │
                ▼                                     │
    Stage 0 (token 落地) ─┬──> Stage 2 (ESLint 上锁) │
                          │                            │
                          ├──> Stage 5 (page train)  ◀┤
                          │                            │
                          └──> Stage 6 (play spec)   ◀┤
                                                       │
    Stage 1 (vision 文档进度真实化) ─── 与 stage 0 并行 │
                                                       │
    Stage 3 (基础设施层 6 子任务，可并行) ─────────────┤
                                                       │
    Stage 4 (移动端基线) ─── stage 5 入场前必须 done ──┘

    Stage 5 (page train, 5a→5b→5c→5d→5e 顺序)
        每页改完 stop-the-line 给用户发截图

    Stage 6 (play spec doc) ── 在 5d 之后

    Stage 7 (PWA) ── 在 5e 之后
```

**并行机会**：stage 0 / 1 / 3 完全独立，可同时启动。stage 4 与 5 之前并行。
**串行硬约束**：stage 5 page train 五页严格顺序（每页都基于前一页学到的映射决策）。

---

## 2. 跨阶段决策（一次定死）

这些选择在 master plan 里钉死，每阶段不再重新讨论：

| # | 决策 | 选择 |
|---|---|---|
| D1 | i18n 时机 | stage 3 装 next-intl 基础设施；**实际 t() 化跟 page train 同步**（每迁一个页面顺手 t() 化该页所有硬编码中文）。不做"全站 t() 化大跃进" |
| D2 | shadcn 引入范围 | 装 5 个组件，全部 retheme 到 `--lv-*`：Dialog / Drawer / Popover / Toast / Command Menu。**简单组件继续手写**保留 cinematic 风格 |
| D3 | Storybook 范围 | stage 3 末交付：① 首页 = `/dev/type` 字体样张内嵌、② 12 个原子组件入册（Button / Chip / PosterCard / Tag / PageHeader / Toolbar / EmptyState / Pill / Modal / Drawer / FormField / LoadingPulse）。复杂业务组件延后到 page train 抽出后再补 |
| D4 | 测试框架 | vitest（next 16 兼容好）+ @testing-library/react。现存 `frontend/lib/*.test.ts` 让它们跑通。新组件**不强制 TDD**（CLAUDE.md 已说"轻量测试"），但纯函数（token util / 类型映射等）要写测试 |
| D5 | page train 参考产品 | 5a login → **Linear 登录页**（最简、纯黑、无装饰）；5b admin workshop → **Linear settings**（表单部分）+ **Vercel dashboard**（列表/草稿）；5c worlds/[id] → **Letterboxd 影片页** + **Apple TV+ show 详情**；5d play/[id] → 不找外部 ref，**保留现有沉浸框架，只换 token 与字号** |
| D6 | 现存 case-hologram 处理 | stage 5d 时 retheme（teal `#00a693` → `--lv-accent` 暖金），保留交互结构。**不重写** |
| D7 | 后端协议 | 零变更。所有改动停在 `frontend/` 内 |
| D8 | 旧 token 删除时机 | globals.css 旧 `@theme inline` 块到 stage 5e 才整组删，期间老页面靠它继续工作 |
| D9 | 单位 | px 全程（spec 已写 px，不混用 rem） |
| D10 | 自主度（C 路线） | 阶段内决策我自己定，记录在阶段总结。**例外**：stage 5 page train 每页改完前发截图给用户看 |
| D11 | 失败回退 | 每阶段未通过自检（见 §5 不变量）则**当场修复**或回退该阶段改动，不带病推进 |
| D12 | i18n 占位语言 | `zh.json` 全填，`en.json` 仅占壳（key 齐、value 留 TODO 字符串），不翻译 |

---

## 3. 各阶段实施细则

每节格式：**入场条件 / 文件清单 / 验收口径 / 典型决策默认走法**。

### Stage 0 · v2.2 token + 9 档工具类落地

**入场条件**：master plan 通过 review。

**实际工作量已大幅缩小**（CSS 已写好，只缺应用 + 校准）。

**文件清单**：
- 改：`frontend/app/layout.tsx`
  - body 加 `className="lv-theme min-h-full flex flex-col"`（移除 `bg-bg-primary text-text-primary`，让 `.lv-theme` 接管色板）
  - 加 `export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#0a0a0c" }`
- 改：`frontend/app/globals.css`
  - 注释 `v2.1` → `v2.2`（line 1184、1361、1469、1554、1571、1580、1591、1604）
  - 移除 body 元素选择器中的 radial-gradient teal 背景（line 81-91 那块）—— `.lv-theme` 已设 background，body 元素规则冲突
  - 旧 `@theme inline` / `:root --ta-*` 块**保留不动**（标 @deprecated 注释已存在，stage 5e 删）
- 不改：`frontend/app/dev/type/page.tsx`（已写好，应用 `.lv-theme` 后直接生效）

**验收口径**：
- [ ] 开 dev server 访问 `/dev/type`，9 档字号样张全部正常渲染（serif/sans/mono 字体可见，clamp 在 320–1920 屏宽响应）
- [ ] 旧页面（`/login` / `/discover` / `/play`）打开**不崩**——旧 token 仍在
- [ ] `:focus-visible` 暖金 2px 焦点环可见
- [ ] `prefers-reduced-motion: reduce` 命中时 cinematic 动效降级

**典型决策默认走法**：
- Cormorant Garamond / Inter / JetBrains Mono / Noto Serif SC / PingFang SC 字体来源 → 用 `next/font/google`（Cormorant、Inter、JetBrains Mono）+ system fallback（PingFang SC 系统已有）。Noto Serif SC 通过 next/font 接 Google Fonts
- 若 Tailwind v4 与 `.lv-t-*` 类有 specificity 冲突 → 类内规则用 `!important` 单点压制，不全局
- 加载脉冲 keyframe → 直接搬 plan 文档 §10.1 的描述（8px 圆，opacity 0.3↔1，1800ms）

---

### Stage 1 · 文档进度真实化

**入场条件**：可与 stage 0 并行启动。

**文件清单**：
- 改：`docs/plans/frontend-refactor-2026-05.md`
  - 阶段 0 状态从"已完成"改为"实施中"或"已完成"（取决于 stage 0 是否真做完）
  - 阶段 1 加一句"本计划文档已进入 docs/plans/，AGENTS / CLAUDE / visual-principles / frontend-spec 已同步 v2.2"
- 增：`docs/superpowers/specs/2026-05-08-frontend-refactor-master-plan.md`（即本文档，stage 0 启动前已存在）

**验收口径**：
- [ ] plan 文档进度行与代码真实状态一致
- [ ] master plan 与 vision plan 双向引用清晰

**典型决策默认走法**：进度更新只改状态行，不改阶段定义/范围。

---

### Stage 2 · ESLint v2.2 上锁

**入场条件**：stage 0 完成（token 终态确定）。

**文件清单**：
- 改：`frontend/eslint.config.mjs`
  - 新增 `no-restricted-syntax` 规则禁用：
    - `className` 含 `text-\[\d` arbitrary
    - `style` 含 inline `fontSize` 数字
    - `var(--font-size-*)` / `var(--ta-*)` / `var(--color-accent)` 旧 token 字符串
    - `className` 含 `gap-5/7/9/10/11`、`p-5/7/9/10/11`
    - `className` 含 `z-\[\d` arbitrary
    - `className` 含 `rounded-\[` arbitrary
  - 现存违规（230 处）**逐一加 `// eslint-disable-next-line`** 注释 + TODO 标 stage 5 该页（避免 stage 2 PR 把 stage 5 的工作做完）
- 增：`frontend/package.json` 加 `"lint:strict"` script（CI 跑这个）
- 文档：在违规注释旁简短写"将在 stage 5x 迁移"

**验收口径**：
- [ ] `npm run lint` 0 error 0 warning（违规处都有 disable 注释）
- [ ] 故意写一个 `text-[1.7rem]` 验证规则触发
- [ ] 故意写一个 `gap-7` 验证规则触发
- [ ] 现存所有页面打开不变化（disable 注释不影响运行时）

**典型决策默认走法**：
- 规则用 `no-restricted-syntax` selector 实现，不写自定义 plugin（成本太高）
- 中间档 `gap-5/7/9/10/11` 是禁止的；`gap-1/2/3/4/6/8/12/16/24` 允许
- ESLint disable 行注释格式：`// eslint-disable-next-line no-restricted-syntax -- stage5x: 待迁移`

---

### Stage 3 · 基础设施层（6 子任务）

**入场条件**：可与 stage 0/1 并行（不依赖 token）。

**文件清单**（6 子任务并行）：

| 子任务 | 装 | 文件改动 |
|---|---|---|
| 3a TanStack Query | `@tanstack/react-query` `@tanstack/react-query-devtools` | 改 `frontend/app/layout.tsx` 包 `<QueryClientProvider>`；新增 `frontend/lib/query-client.ts`；新增 `frontend/lib/api/` 目录用 useQuery/useMutation 包现有 fetch（**不替换** stages 5 才换页面消费方）|
| 3b RHF + Zod | `react-hook-form` `@hookform/resolvers` `zod` | 新增 `frontend/lib/forms/` 放 schema；不改业务，stage 5b/5c 用到时挂 |
| 3c Framer Motion | `motion` (即 `motion/react`) | 新增 `frontend/lib/motion.ts` 把统一 ease / duration token 包成预设；不改业务 |
| 3d next-intl | `next-intl` | 新增 `frontend/i18n/zh.json` `frontend/i18n/en.json`（en 占壳）+ `frontend/i18n/request.ts` + `frontend/middleware.ts` 路由配置（仅 `/` 不带 locale 前缀，单语模式）；改 `next.config.ts` 加 plugin |
| 3e shadcn 5 组件 | `class-variance-authority` `clsx` `tailwind-merge` `@radix-ui/react-{dialog,popover,toast,command}` `vaul`(Drawer) | 用 shadcn CLI 拷 5 组件到 `frontend/components/ui/shadcn/`，retheme 到 `--lv-*`；不改业务 |
| 3f vitest（已做） | `vitest` `@vitejs/plugin-react` `@testing-library/react` `@testing-library/jest-dom` `@testing-library/user-event` `jsdom` | `vitest.config.ts` + `vitest.setup.ts`；删除 lib/*.test.ts 里的 `import test from "node:test"`（vitest globals 接管，13/15 文件通过，2 个 assertion 漂移延后） |
| 3g Storybook + 12 原子组件（**延后**） | — | **scope reduction（2026-05-08）**：原计划 3f 含 Storybook + 新建 12 原子组件（Button/Chip/PosterCard/...），实测工作量 2-3 天与"加速"目标冲突。改为：page train 阶段自然抽组件 → 抽哪个写哪个 story。Storybook 等 5b 起需要可视化复杂表单状态时再装 |

**验收口径**：
- [ ] `npm install` 干净通过
- [ ] `npm run dev` 启动正常
- [ ] `npm run build` 通过
- [ ] `npm test` 跑通（10 个 lib test 全绿）
- [ ] `npm run storybook` 起来，type sample + 12 组件全部可见
- [ ] 单语 i18n 验证：把 landing 的某一句中文换成 `t('landing.hero.title')`，`zh.json` 配上，正常显示

**典型决策默认走法**：
- shadcn 通过 CLI 拷源码而非 npm 包，便于 retheme
- next-intl 路由模式：`as-needed` localePrefix（zh 默认无前缀，en 占壳但暂不暴露）
- TanStack Query staleTime 默认 5 分钟，gcTime 10 分钟
- Storybook 用 nextjs framework，启用 Tailwind v4
- vitest 配 jsdom 环境，setup file 引 `@testing-library/jest-dom`

**子任务可由 subagent 并行执行**：3a–3e 完全独立可并行；3f 必须等 3a–3e 完成（依赖 i18n / shadcn 等已就绪后才能写组件）。完成后集中验证。

---

### Stage 4 · 移动端布局基线

**入场条件**：stage 0 完成（需要 `--lv-*` token）。

**文件清单**：
- 改：`frontend/components/Navbar.tsx`
  - 桌面端（≥ 1024px）保持现状
  - 移动端（< 768px）改底部 tab bar，4 项：首页 / 发现 / 历史 / 我（"我"对应已登录头像 dropdown 或登录入口）
  - 高度 56px + `safe-area-inset-bottom`
  - **play 路由特例**：play/* 路径下移动端隐藏 tab bar（沉浸态），nav 折叠为右上角图标（这个真正实现在 stage 5d）
- 增：`frontend/lib/use-viewport.ts` 提供 `useIsMobile()` hook（matchMedia 版，避免 hydration mismatch）
- 改：`frontend/app/globals.css` 顶部加 viewport 基础规则（`100dvh` helper class、safe-area helpers）
- 改：`frontend/app/layout.tsx` viewport meta 设 `width=device-width, initial-scale=1, viewport-fit=cover`

**验收口径**：
- [ ] 375px 打开 `/discover` 看到底部 tab bar，触摸目标 ≥ 44×44px
- [ ] 1280px 打开 `/discover` 仍是顶部 navbar（无回归）
- [ ] iOS Safari 模拟器看 home indicator 不遮挡 tab bar（safe-area 生效）
- [ ] tab bar 当前页高亮正确

**典型决策默认走法**：
- tab bar 图标用 lucide-react（已存在 → 检查 → 没有就装 `lucide-react`）
- 底部 tab 高亮策略：当前路由前缀匹配（/play 高亮"首页"无意义，play 直接隐藏 bar）
- "我" 入口未登录显示登录图标，已登录显示用户名首字字母圆形 avatar

---

### Stage 5 · 视觉迁移 page train

> **C 路线唯一例外**：每个子阶段（5a–5d）改完前我**停下来发截图 + 待验项**给用户。5e 是删除操作不需要视觉 review。

#### Stage 5a · login

**入场条件**：stage 2 / 3 / 4 全部完成。

**文件清单**：
- 改：`frontend/app/login/page.tsx` + 相关 `frontend/components/auth/LoginModal.tsx`
- 参考：Linear 登录页（github.com/linear 风格）—— 纯黑底，logo 居中，单一 CTA，无装饰
- 用：lv-* token 全套；shadcn Dialog（如果是 modal）；RHF + Zod 表单；next-intl t()
- 删：所有 inline `text-[Xrem]`、所有旧 `--color-accent` 引用

**验收口径**：
- [ ] 9 档字号合规（grep 该文件无 `text-[`）
- [ ] 无中二文案（无"继续你的故事 / 那些没结束的世界"——按照 visual-principles §哲学 §9）
- [ ] 375px + 1280px 双断点截图通过
- [ ] PR 自检表全绿
- [ ] **stop-the-line**：用户看截图后 OK 才能进 5b

#### Stage 5b · admin workshop

**入场条件**：5a 完成。

**文件清单**：
- 改：`frontend/app/admin/page.tsx`、`admin/worlds/`、`admin/scripts/`、`admin/generate/world/`、`admin/generate/script/`
- 改：`frontend/components/admin/**`（含 workshop / ImageGallery / GenerationLoadingScreen / PhaseIndicator 等约 10+ 组件）
- 参考：Linear settings + Vercel dashboard
- 用：TanStack Query 替 useEffect；RHF + Zod 表单；shadcn Dialog/Drawer/Toast；next-intl
- 删：全部 `--ta-*` / `text-[Xrem]` / inline fontSize

**验收口径**：同 5a。

#### Stage 5c · worlds/[id]

**入场条件**：5b 完成。

**文件清单**：
- 改：`frontend/app/worlds/[id]/page.tsx`、`worlds/[id]/start/page.tsx`
- 改：`frontend/components/WorldCard.tsx`、`WorldExperiencePanel.tsx`、`WorldModeCard.tsx`、`ScriptSelectionCard.tsx`、`landing/LandingExperience.tsx`、`Navbar.tsx`（如果 stage 4 后还有遗留）
- 参考：Letterboxd 影片页 + Apple TV+ show 详情
- 用：lv-* / Framer Motion 入场 / TanStack Query / next-intl
- 保留 cinematic hero 哲学，封面 16:10

**验收口径**：同 5a + 卡片字段表合规（visual-principles §7.1，5 个文字位）。

#### Stage 5d · play/[id]

**入场条件**：5c 完成。

**文件清单**：
- 改：`frontend/app/play/[id]/page.tsx` + `frontend/components/`（GameHeader / ChatPanel / MessageBubble / ActionInput / QuickActions / StreamingStatusRail / EndingScreen / EndingCinematic / GameLoadingScreen / IdentityPanel / PauseOverlay / JumpToLatestButton / ContextDrawer / SectionNav / StickyBottomBar / UnifiedSidePanel / case-hologram/* 全部）
- 不找外部 ref —— 保留现有沉浸框架，只做 token / 字号 / 字体迁移
- 移动端：double-pane → 单栏 + 底抽屉（visual-principles §12.8）
- case-hologram：teal → 暖金，保留交互结构

**验收口径**：同 5a + visual-principles §12 全部条款合规 + 移动端单栏布局 OK + 流式输入不抖动。

#### Stage 5e · 删旧 token

**入场条件**：5a–5d 全部完成 + 全局 grep 确认无旧 token 引用。

**说明**：5a–5d 每页迁移时**当场移除该页的 `eslint-disable-next-line` 注释**（因为 inline 都改完了）。5e 是**兜底验证 + 删 globals.css 旧块**，不再大规模清注释。

**文件清单**：
- 改：`frontend/app/globals.css`
  - 删除 `@theme inline { --color-* --font-size-* --radius-* --duration-* ... }` 整块
  - 删除 `:root { --ta-* }` 块（如有）
  - 保留 `@import "tailwindcss"` 和 `.lv-theme` 块
- 改：`docs/plans/frontend-refactor-2026-05.md` 阶段 5 标完成
- 验：全站 grep 确认无遗漏 disable 注释

**验收口径**：
- [ ] 全站 grep 无 `--font-size-` / `--ta-` / `--color-accent` 引用
- [ ] 全站 grep 无 `text-\[` arbitrary
- [ ] 全站 grep 无 `eslint-disable-next-line.*stage5x` 残留
- [ ] `npm run lint:strict` 通过
- [ ] 全站冒烟：landing / discover / login / admin / worlds/X / play/X / history 各点一遍正常

---

### Stage 6 · play 沉浸表面专属规范

**入场条件**：stage 5d 完成（实施过程中得到豁免边界的现实数据）。

**文件清单**：
- 增：`docs/design/play-mode-spec.md`，内容：
  - 豁免清单：max-width 760（不豁免 type scale / accent / motion / 9 档字号 / 9 档间距 / 6 档 z-index）
  - case-hologram 规范：清单看板，禁止脉冲/扫光/扫描线/霓虹辉光堆叠
  - 流式状态轨道规格（高度 32px，颜色 `--lv-ink-3`）
  - 输入框规格（56px 高，pill 圆角，placeholder 给具体动作示例）
  - 移动端单栏 + 底抽屉模式
  - 结局动画 cinematic B 例外应用边界

**验收口径**：
- [ ] play-mode-spec 与 visual-principles §12 不冲突
- [ ] play-mode-spec 反映 stage 5d 的实际实现（不是理想化文档）

---

### Stage 7 · PWA + 收尾

**入场条件**：stage 5e 完成。

**文件清单**：
- 增：`frontend/public/manifest.json` + `frontend/public/icons/`（72/96/128/144/152/192/384/512 共 8 档）
- 增：`frontend/app/sw.ts` + `frontend/next.config.ts` 加 PWA 配置（用 `@ducanh2912/next-pwa` 或 `serwist`）
- 改：`frontend/app/layout.tsx` 引 manifest / theme-color meta
- 增：splash screen（lv-bg + 中央 logo）
- 文档同步：
  - `docs/plans/frontend-refactor-2026-05.md` 全部阶段标完成
  - 我的 memory 更新（项目状态记录）

**验收口径**：
- [ ] iOS Safari "加到主屏" 后启动看到 splash + 全屏（无 Safari chrome）
- [ ] Android Chrome 安装 PWA 流程通过
- [ ] Lighthouse PWA 评分 ≥ 90
- [ ] 离线打开 landing 页不白屏（基础缓存生效）

**典型决策默认走法**：
- PWA 库选 serwist（更现代，Tailwind v4 + Next 16 兼容好）
- 图标用单一 source（`logo.svg`）通过 sharp 一次性生成 8 档 PNG
- service worker 缓存策略：静态资源 cache-first，API stale-while-revalidate

---

## 4. 工程基线

| 项 | 命令 | 备注 |
|---|---|---|
| 启 dev server | `cd frontend && npm run dev` | 端口 3000，被占用切 3001 |
| 跑 test | `cd frontend && npm test` | stage 3 后可用 |
| 跑 lint | `cd frontend && npm run lint` | stage 2 后严格 |
| 跑 build | `cd frontend && npm run build` | 每阶段末跑一次 |
| 跑 storybook | `cd frontend && npm run storybook` | stage 3 后可用 |
| 截图 | dev server + Chrome devtools 切 iPhone SE (375) / 1280 width | stage 5 stop-the-line 用 |

---

## 5. 跨阶段不变量（v2.2 永久红线，每阶段自检）

每阶段末跑一遍这张清单。任意一条 fail = 当场修复，不带病推进：

- [ ] 字号只用 9 档（display/h1/h2/h3/narrative/body/meta/caps/micro），无 `text-[Xrem]` 破例
- [ ] 颜色用 `var(--lv-*)`，无旧 `--color-accent` / `--font-size-*` / `--ta-*`
- [ ] 一屏 ≤ 4 档字号（micro 不计），accent 装饰一屏 ≤ 1 处
- [ ] 圆角只用 16 / 10（仅表单）/ 9999
- [ ] 间距 9 档，无 5/7/9/10/11 中间档
- [ ] z-index 6 档，无 99/999/9999
- [ ] hover/transition ≤ 250ms（cinematic 例外）
- [ ] 卡片字段 ≤ 5（visual-principles §7.1）
- [ ] 文案克制（无"翻阅你的足印 / 继续你的故事"等中二）
- [ ] 三态完整（loading / empty / error）
- [ ] 触摸目标 ≥ 44px
- [ ] 焦点环可见、对比度 ≥ 4.5:1
- [ ] `prefers-reduced-motion` 关闭长动效
- [ ] 所有文案走 i18n（page train 阶段开始）
- [ ] 后端协议零变更（无 `frontend/lib/api/` 之外的 fetch 改动）

---

## 6. 风险与回退

| 风险 | 缓解 | 回退路径 |
|---|---|---|
| Tailwind v4 与 `.lv-t-*` 工具类 specificity 冲突 | 测试 stage 0 优先在 `/dev/type` 验证 | 类内 `!important` 单点压制 |
| Framer Motion + Next 16 RSC 不兼容 | 用 `motion/react`（专门为 RSC 设计），全部 wrap 在 client component | 退回 CSS transition |
| shadcn 视觉与 cinematic 冲突 | 装的 5 组件全部 retheme 到 `--lv-*`，验收时对比 `/dev/type` | 不用 shadcn，回退手写 |
| next-intl 与 Next 16 App Router 路由冲突 | 装好后先在一个非关键页（如 dev/type）试 | 退回硬编码中文 |
| stage 5 page train 某页改完用户不满意 | stop-the-line 立刻调 | 该页回退到上次 commit 状态（项目无 git → 我维护一份"上次稳定" backup 副本） |
| 工期超出 4–5 周 | 阶段独立可合入，超期则砍 stage 6 + 7 | 优先保 stage 0–5（核心目标） |

---

## 7. 不在本 plan 内的内容

- token 数值（颜色 hex / 间距 px）→ `frontend-spec.md` v2.2
- 视觉哲学（极简优先 / 不中二 / accent 克制）→ `visual-principles.md` v2.2
- 阶段产品级动机 → `docs/plans/frontend-refactor-2026-05.md`
- 后端 / 引擎 → `docs/ARCHITECTURE.md` + `docs/modules/`

本 plan **只回答**：每阶段做什么文件、用什么验收标准、在哪些点停下让用户看。

---

> 维护：jie / Claude Code
> 最后更新：2026-05-08
> 状态：草案 → 等用户 review
