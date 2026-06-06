# Stage 0 · v2.2 Token Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已经写好但未生效的 v2.2 token 体系（`.lv-theme` + 9 档 `.lv-t-*` 工具类）真正应用到页面 DOM，让 `/dev/type` 字体样张正确渲染，全站进入 lv-theme 色板。

**Architecture:** `frontend/app/globals.css` 已含完整 `.lv-theme` 块（line 1190+）+ 全部 token + 工具类 + 表单类 + 焦点环 + reduced-motion 规则。本阶段做三件事：① 给 `<body>` 挂 `lv-theme` class（替掉旧 Tailwind `bg-bg-primary` 色板）、② 加 viewport-fit=cover meta、③ 修剪 body 元素 selector 的旧 teal radial-gradient（与 `.lv-theme { background }` 冲突）。注释由 v2.1 校准到 v2.2。

**Tech Stack:** Tailwind v4、Next 16 App Router、CSS 自定义属性。

**Scope guard:** 不改 `.lv-theme` 块内容（已对齐 v2.2 spec），不删旧 `@theme inline` / `:root --ta-*` 块（stage 5e 删），不动业务页面。

---

## Task 1: 应用 `.lv-theme` 到 `<body>` + 加 viewport meta

**Files:**
- Modify: `/Users/jie/Desktop/code/pokonyan/talealive/frontend/app/layout.tsx`

**Why this matters:** 没有这步，`.lv-theme` 块里所有 `--lv-*` token 都不会生效——它们 scoped 在 `.lv-theme` 选择器下。`/dev/type` 页面写了 `className="lv-t-display"` 等工具类，但工具类规则本身也 scoped 在 `.lv-theme` 下，所以必须在某个祖先节点（最适合 `<body>`）挂 `lv-theme` 才能层叠生效。

- [ ] **Step 1.1: 阅读当前 layout.tsx 确认起点**

```bash
cat /Users/jie/Desktop/code/pokonyan/talealive/frontend/app/layout.tsx
```

Expected output (current, 38 行):
```tsx
import type { Metadata } from "next";

import { AuthBootstrap } from "@/components/AuthBootstrap";
import { Navbar } from "@/components/Navbar";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "TaleAlive",
    template: "%s | TaleAlive",
  },
  description: "AI 驱动的互动叙事引擎，每一个选择塑造独一无二的故事。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Noto+Serif+SC:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full flex flex-col bg-bg-primary text-text-primary" suppressHydrationWarning>
        <AuthBootstrap />
        <Navbar />
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 1.2: 编辑 layout.tsx — 加 Viewport import + viewport export + 改 body className**

Edit 1：替换 `import type { Metadata } from "next";` 为：

```tsx
import type { Metadata, Viewport } from "next";
```

Edit 2：在 `metadata` 常量声明**之后**、`RootLayout` 函数之前插入：

```tsx
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0a0a0c",
};
```

Edit 3：替换 body className：

旧：
```tsx
<body className="min-h-full flex flex-col bg-bg-primary text-text-primary" suppressHydrationWarning>
```

新：
```tsx
<body className="lv-theme min-h-full flex flex-col" suppressHydrationWarning>
```

**Why these specific class changes:**
- 加 `lv-theme` → 启用 `.lv-theme` 作用域下所有 `--lv-*` token 与 `.lv-t-*` 工具类
- 删 `bg-bg-primary text-text-primary` → 这是旧 `@theme inline` token 的 Tailwind 类，与 `.lv-theme` 的 `background: var(--lv-bg)` / `color: var(--lv-ink)` 冲突；移除让 lv 接管
- 保留 `min-h-full flex flex-col` → 这是布局工具类，不涉及色板，stage 5 时再评估

- [ ] **Step 1.3: 跑 build 验证 layout.tsx 改动 type-check 通过**

```bash
cd /Users/jie/Desktop/code/pokonyan/talealive/frontend && npm run build
```

Expected：
- 编译成功，0 type error
- 警告 / Sentry 相关警告可忽略
- 若失败：检查 Viewport import 路径（应为 `"next"`），检查 themeColor 类型（应为字符串）

- [ ] **Step 1.4: 起 dev server 准备视觉验证**

```bash
cd /Users/jie/Desktop/code/pokonyan/talealive/frontend && npm run dev
```

注意：dev server 启动后保留运行，下面任务用同一个进程。如果端口 3000 被占用，记下实际端口（通常自动切到 3001）。

---

## Task 2: 修 globals.css — 注释 v2.1 → v2.2 + 修剪 body radial-gradient 冲突

**Files:**
- Modify: `/Users/jie/Desktop/code/pokonyan/talealive/frontend/app/globals.css`

**Why this matters:**
- body 元素 selector（line 81-91）写了 `background: radial-gradient(...) #0c0c10`，这是旧 teal accent 的视觉残留。`.lv-theme` 的 `background: var(--lv-bg)` 因 class 选择器 specificity 高于 element selector 而胜出，**所以业务上没问题**——但留着是 dead code 制造混乱，且 `#0c0c10` 与 `--lv-bg: #0a0a0c` 不一致让人误以为 lv-theme 没生效。**移除以保持 single source of truth**。
- 注释 v2.1 → v2.2 是文档校准，避免新人读到 stage 0 已落地的代码却看到"v2.1"误以为没升级。

- [ ] **Step 2.1: 移除 body 元素 selector 的 radial-gradient + 老色值**

打开 `/Users/jie/Desktop/code/pokonyan/talealive/frontend/app/globals.css` line 81-91 附近，找到：

```css
body {
  min-height: 100vh;
  background:
    radial-gradient(circle at 50% 0%, rgba(0, 166, 147, 0.04), transparent 50%),
    #0c0c10;
  color: #e8e4de;
  font-family: "IBM Plex Sans", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
}
```

替换为：

```css
body {
  min-height: 100vh;
  /* 背景与字体由 .lv-theme 接管（layout.tsx 中 body 挂了 lv-theme class）。
     旧 @theme inline 块仍存在，老页面通过 Tailwind utility class 自取 token，互不干扰。 */
}
```

**Why preserve `min-height: 100vh`:** `min-h-full` Tailwind 类映射到 `min-height: 100%`，依赖 html 高度完全打通；保留 body 的 `100vh` 作 fallback。

- [ ] **Step 2.2: 同步删除 html 的 background 兜底（line 78-80）**

找到：

```css
html {
  background: #0c0c10;
}
```

替换为：

```css
html {
  background: var(--lv-bg, #0a0a0c);
}
```

**Why fallback:** `--lv-bg` 是 scoped 在 `.lv-theme` 的，`<html>` 没挂 `lv-theme` 时无法拿到（fallback `#0a0a0c` 兜底，匹配新色值）。这避免页面切换 / 加载瞬间出现旧 `#0c0c10` 闪烁。

- [ ] **Step 2.3: 注释 v2.1 → v2.2，5 处 search-and-replace**

用 Edit replace_all：

| 旧 | 新 |
|---|---|
| `TaleAlive · v2.1 视觉系统 — canonical token source` | `TaleAlive · v2.2 视觉系统 — canonical token source` |
| `规范：docs/visual-principles.md v2.1` | `规范：docs/design/visual-principles.md v2.2` |
| `v2.1 排版工具类 (§1.2 §1.4)` | `v2.2 排版工具类 (§1.2 §1.4)` |
| `v2.1 表单控件基线 (§11)` | `v2.2 表单控件基线 (§11)` |
| `v2.1 加载脉冲 (§10.1)` | `v2.2 加载脉冲 (§10.1)` |
| `v2.1 焦点环 (§13)` | `v2.2 焦点环 (§13)` |
| `v2.1 PosterCard hover (§7.1)` | `v2.2 PosterCard hover (§7.1)` |
| `v2.1 Discover 网格 (§8.2)` | `v2.2 Discover 网格 (§8.2)` |
| `v2.1 Drawer 移动端从底部弹出` | `v2.2 Drawer 移动端从底部弹出` |
| `规范见 docs/visual-principles.md v2.1。` | `规范见 docs/design/visual-principles.md v2.2。` |

执行 9 次单独的 Edit 调用（不是 replace_all 一次）以避免误改其他位置。

- [ ] **Step 2.4: 也校准旧 deprecated 注释中的版本号**

`@theme inline` 块顶部约 line 4-9 写：

```css
/* ==========================================================================
   ⚠️  DEPRECATED — 留作向后兼容，新代码请用 .lv-theme 下的 --lv-* 令牌
   规范见 docs/visual-principles.md v2.1。
   这一组 @theme inline 暂时保留，因为 play page / admin workshop 仍在消费
   text-* / bg-* / rounded-* / radius-* 等 Tailwind 类（依赖这些 token）。
   Phase 2 页面级迁移完成后整组删除。
   ========================================================================== */
```

替换为：

```css
/* ==========================================================================
   ⚠️  DEPRECATED — 留作向后兼容，新代码请用 .lv-theme 下的 --lv-* 令牌
   规范见 docs/design/visual-principles.md v2.2。
   这一组 @theme inline 暂时保留，因为 play page / admin workshop 仍在消费
   text-* / bg-* / rounded-* / radius-* 等 Tailwind 类（依赖这些 token）。
   Stage 5e（见 docs/plans/frontend-refactor-2026-05.md）页面级迁移完成后整组删除。
   ========================================================================== */
```

也找到 `:root` `--ta-*` 块上方的 deprecated 注释（约 line 1030-1034）：

```css
/* ==========================================================================
   ⚠️  DEPRECATED — 创作工坊老 token 系统（teal #00a693），暂留兼容
   规范见 docs/visual-principles.md v2.1。新代码请用 .lv-theme 下的暖金 accent。
   工坊页面 Phase 2 迁移到 lv-theme 后整组删除。
   ========================================================================== */
```

替换为：

```css
/* ==========================================================================
   ⚠️  DEPRECATED — 创作工坊老 token 系统（teal #00a693），暂留兼容
   规范见 docs/design/visual-principles.md v2.2。新代码请用 .lv-theme 下的暖金 accent。
   Stage 5b（见 docs/plans/frontend-refactor-2026-05.md）admin workshop 迁移到 lv-theme 后整组删除。
   ========================================================================== */
```

---

## Task 3: 视觉验证 `/dev/type` + 全站冒烟

**Why this matters:** Stage 0 的可验证 deliverable 是"`/dev/type` 9 档字号能正确渲染" + "老页面没有视觉回归"。CSS 改动没有 unit test 兜底，只能 visual verify。

- [ ] **Step 3.1: 浏览器打开 `/dev/type` 桌面断点**

URL: `http://localhost:3000/dev/type`（或实际 dev server 端口）。

**预期检查清单**（每条都要勾过）：
- [ ] 页面非空白，能看到 9 档字号样张
- [ ] `t-display` 用衬线字体（Cormorant Garamond + Noto Serif SC），字号约 112px（桌面）
- [ ] `t-h1` 衬线，约 48px
- [ ] `t-h2` 衬线，约 28px
- [ ] `t-h3` **无衬线**（Inter + PingFang SC），约 18px ← 重点：v2.2 改了 h3 用 sans
- [ ] `t-narrative` **无衬线**，约 17px ← 重点：v2.2 narrative 从 serif 改 sans
- [ ] `t-body` 无衬线 15px 固定
- [ ] `t-meta` 12px 灰文字（`--lv-ink-3`）
- [ ] `t-caps` mono 字体 + ALL CAPS + 字距明显（0.2em）
- [ ] `t-micro` mono 字体 + 10px

如果任何一档字号或字体不对，**立刻停下排查**——可能是 `.lv-theme` 没挂上、字体没加载、或工具类 specificity 被别的规则压制。

- [ ] **Step 3.2: 浏览器打开 `/dev/type` 移动断点（375px）**

Chrome DevTools → Toggle device toolbar → iPhone SE (375 × 667)。

**预期：**
- [ ] `t-display` 缩到约 48px（不是桌面的 112px）
- [ ] `t-h1` 缩到约 28px
- [ ] `t-narrative` 约 15px
- [ ] `t-body` / `t-meta` / `t-caps` / `t-micro` **不变**（固定档）
- [ ] 整页可纵向滚动，无横向滚动条

- [ ] **Step 3.3: 视觉冒烟测试老页面**

逐个打开下列页面，检查"页面渲染、能看到内容、没有控制台报错"——**不**要求视觉完美（这些页面 stage 5 才迁移）：

URL 清单（每个跑一遍，桌面 1280px）：
- `http://localhost:3000/` — landing
- `http://localhost:3000/login` — login
- `http://localhost:3000/discover` — 世界发现
- `http://localhost:3000/history` — 历史
- `http://localhost:3000/admin` — 创作工坊（需登录，登录失败则跳过）

**预期通过**：
- [ ] 所有页面背景均为深色（#0a0a0c 或 #0c0c10 区别人眼几乎看不出，OK）
- [ ] 无白屏 / 无 React error overlay
- [ ] 控制台无新增红色 error（warning 可忽略）

**预期可能发生但不算回归**：
- 某些组件 hover 颜色微变（旧 teal `--color-accent` → 新页面继承 lv-theme `--lv-accent` 暖金）—— stage 5 修
- body 背景的 teal 微光不见了（已删 radial-gradient）—— **预期行为**

如果出现严重视觉破坏（页面排版崩溃、文字消失、布局错位），停下排查 specificity 冲突。

- [ ] **Step 3.4: 关 dev server，跑 build 确认产线一致**

Ctrl+C 关 dev server，然后：

```bash
cd /Users/jie/Desktop/code/pokonyan/talealive/frontend && npm run build
```

**预期：**
- 编译成功
- 总 bundle 大小变化 < 1KB（CSS 只是改了 className 与极小注释，没有增量内容）
- 0 error

---

## Task 4: 同步更新 vision plan 文档

**Files:**
- Modify: `/Users/jie/Desktop/code/pokonyan/talealive/docs/plans/frontend-refactor-2026-05.md`

**Why this matters:** vision plan 声明 stage 0 已完成，现在终于真完成。把状态行从"已完成"改成更精确描述（"Stage 0 已应用 + 视觉验证通过"），让后续读者不会被误导。

- [ ] **Step 4.1: 找到 stage 0 状态行**

文件 line 105-112 附近，原文：

```markdown
### 阶段 0：Type System Spec（已完成）

- [x] 定 9 档字号（display/h1/h2/h3/narrative/body/meta/caps/micro）
- [x] 全部 clamp() 化，移动→桌面平滑过渡
- [x] 字体三套搭配（serif/sans/mono）法定用途定死
- [x] 字重 400/500（serif）、400/500/600（sans）
- [x] 样张页 `/dev/type` 上线，作为 single source of truth

**产物**：`globals.css` 已升级，`/dev/type` 可访问。
```

替换 `**产物**` 那行为：

```markdown
**产物**：`globals.css` 含完整 `.lv-theme` 块 + 9 档 `.lv-t-*` 工具类（line 1190+）。`<body>` 已挂 `lv-theme` class（layout.tsx），`/dev/type` 桌面 + 移动双断点验证通过（2026-05-08）。
```

- [ ] **Step 4.2: 改阶段 1 状态从"进行中"到"已完成"**

文件 line 114 附近，原文：

```markdown
### 阶段 1：文档统一（进行中）

- [ ] `docs/design/visual-principles.md` 升 v2.2（9 档 + clamp）
- [ ] `docs/design/frontend-spec.md` 升 v2.2（token 值表更新）
- [ ] `CLAUDE.md` + `frontend/AGENTS.md` 对齐新版本
- [ ] 本计划文档进入 `docs/plans/`
```

替换为：

```markdown
### 阶段 1：文档统一（已完成）

- [x] `docs/design/visual-principles.md` 升 v2.2（9 档 + clamp）
- [x] `docs/design/frontend-spec.md` 升 v2.2（token 值表更新）
- [x] `CLAUDE.md` + `frontend/AGENTS.md` 对齐新版本
- [x] 本计划文档进入 `docs/plans/`
- [x] `globals.css` 注释从 v2.1 校准到 v2.2
```

---

## Task 5: 收尾自检

- [ ] **Step 5.1: grep 验证 globals.css 无残留 v2.1 注释**

```bash
grep -n "v2\.1" /Users/jie/Desktop/code/pokonyan/talealive/frontend/app/globals.css
```

Expected: **空输出**（无匹配）。如果还有残留，回到 Task 2.3 / 2.4 补改。

- [ ] **Step 5.2: grep 验证 layout.tsx 不再含 bg-bg-primary**

```bash
grep -n "bg-bg-primary\|text-text-primary" /Users/jie/Desktop/code/pokonyan/talealive/frontend/app/layout.tsx
```

Expected: **空输出**。

- [ ] **Step 5.3: 跑跨阶段不变量自检**（master plan §5 部分子集，stage 0 适用项）

- [ ] `.lv-theme` 已挂 body（DOM Inspector 看 `<body class="lv-theme min-h-full flex flex-col">`）
- [ ] `/dev/type` 9 档全部正确渲染
- [ ] 老页面无视觉破坏
- [ ] `npm run build` 通过
- [ ] viewport meta 含 `viewport-fit=cover`（DevTools → Network → 主文档 → 看 head）

- [ ] **Step 5.4: 阶段总结**

写一段简短的 stage 0 完成报告（不写文件，直接在 Claude Code 输出给用户），包含：
- 改了哪 2 个文件、共改了多少处
- `/dev/type` 桌面 + 移动各贴 1 张截图描述（用文字说"display 112px serif"等观感）
- 老页面冒烟有无回归
- 进入 stage 1 / stage 2

---

## Self-Review Checklist

写完此 plan 后自检：

- [x] **Spec 覆盖**：master plan §3 的 stage 0 子节"文件清单"列了 4 项，本 plan task 1-4 全覆盖
- [x] **Placeholder 扫描**：搜索"TBD / TODO / fill in / similar to" — 无
- [x] **类型一致**：`Viewport` 类型 from "next" 在 task 1 一致；`lv-theme` className 拼写一致
- [x] **路径完整**：所有 file path 用绝对路径
- [x] **代码完整**：每个 step 给了完整的 before/after 代码块或 grep 命令
- [x] **可验证**：每个 step 有 expected 输出 / 视觉检查项

---

> 最后更新：2026-05-08
> 状态：草案 → 等用户选择执行模式
