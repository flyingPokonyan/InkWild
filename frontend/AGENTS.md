<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# 前端开发快速参考

## 当前状态（v2.3 cinematic gold · 2026-05）

**前端已按 v2.3 cinematic gold 视觉系统统一**：香槟金 `#dfc290` + 暖象牙 `#f5f2eb`，桌面 `<ProductNav>` + 移动 `<BottomTabBar>`，全局 Navbar 移除。
v2.2 typography 工具类 (`.lv-t-*`) 保留并继续推荐，机器仅锁旧 token 漂移（见下）。

主入口页面（已落地 v2.3）：`/`（landing）、`/discover`、`/history`、`/workshop`、`/login`、`/worlds/[id]`、`/play/[id]`。

> Admin 控制台（`admin-frontend/`，端口 3001）**不复用主站视觉系统**，桌面优先、冷蓝低圆角工程化后台，基线见 `../InkWild Admin.html` + `../docs/plans/admin-console-2026-05.md`。

## v2.3 约束

| 项 | 规则 |
|---|---|
| 主题色 | `--lv-accent: #dfc290`（globals.css :root 唯一定义，**禁止 per-page override**） |
| 背景 | `--lv-bg: #08080a`，舞台 `--lv-bg-stage: #050507`。统一，不分页改 |
| 导航 | 桌面用 `<ProductNav variant="transparent" 或 "solid" active="..." />`；移动端 `<BottomTabBar />`。layout.tsx 不再渲染顶部 Navbar |
| 字号 | 优先 `.lv-t-*` 工具类；hero/spotlight 等海报区段允许 inline `style={{ fontSize }}` |
| CSS 组织 | 重复样式用 `<style jsx global>` 局部块（参考 `app/workshop/page.tsx`、`components/ProductNav.tsx`），不每节点 inline 60 行 style 对象 |
| 数据 | 路由级页面只接 TanStack Query 真实数据；mock 仅用于 hero 字段（标题/题材），**禁止虚假指标数字** |
| 动效 | `motion/react`（Framer Motion） |

ESLint 唯一硬规则继续生效：禁 `--ta-*` / `--color-accent` / `--font-size-*` 旧 token。

## 必读文档

| 类别 | 文档 |
|---|---|
| 视觉原则 v2.3 | [`../docs/design/visual-principles.md`](../docs/design/visual-principles.md) |
| 设计令牌 v2.3 | [`../docs/design/frontend-spec.md`](../docs/design/frontend-spec.md) |
| Play 页例外清单 | [`../docs/design/play-mode-spec.md`](../docs/design/play-mode-spec.md) |
| 设计自审报告（v2.2 期备查） | [`../docs/design/audit-2026-05.md`](../docs/design/audit-2026-05.md) |
| 重构计划（已归档） | [`../docs/_archive/frontend-refactor-2026-05.md`](../docs/_archive/frontend-refactor-2026-05.md) |
| 字体样张（实物） | 开 `npm run dev` 后访问 `/dev/type` |

## 字号 9 档（必背）

```
display    clamp(48px,  9vw, 112px)  serif 400  Hero 大标题（每页 ≤1）
h1         clamp(28px,  4vw,  48px)  serif 500  页面主标题
h2         clamp(20px, 2.4vw,  28px) serif 500  区块/section 标题
h3         clamp(16px, 1.4vw,  18px) sans  600  卡片/小区块标题
narrative  clamp(15px,   1vw,  17px) sans  400  叙事正文（lh 1.85，不可改）
body       15px                      sans  400  UI 正文（按钮/表单/气泡）
meta       12px                      sans  400  辅助/时间戳/状态
caps       11px                      mono  500  大写小标签（uppercase + ls 0.2em）
micro      10px                      mono  500  极小标记（每页 ≤3）
```

写代码用工具类：`.lv-t-display` / `.lv-t-h1` / `.lv-t-h2` / `.lv-t-h3` / `.lv-t-narrative` / `.lv-t-body` / `.lv-t-body-long` / `.lv-t-meta` / `.lv-t-caps` / `.lv-t-micro`。

## 规则与约定

**ESLint 唯一硬规则（CI 卡死）：**
- ❌ 不引用旧 token：`var(--font-size-*)` / `var(--ta-*)` / `var(--color-accent)`

**约定级（不上 lint，PR 走查 + 设计师眼睛把关）：**
- 不写 `text-[Xrem]` arbitrary 字号 class（用 `.lv-t-*` 工具类。`text-[var(--lv-ink-3)]` 设颜色 OK）
- 不写 inline `style={{fontSize: 数字}}`（`var(--lv-t-*)` 算合规）
- 不写 `gap-5/7/9/10/11`、`z-[99/999/9999]`、`rounded-[...]` 任意值
- 移动端不依赖 hover 表达状态
- 触摸目标不小于 44px

> 治理硬度调整 2026-05-09：v2.2 早期把全部破例值锁 lint，实战发现机器拦不出审美且误伤合理写法（如 `text-[var(--lv-ink-3)]` 设颜色），改为最小约束。详见 visual-principles §14.5、`eslint.config.mjs` 头注释。

## 基础设施层（已就位）

新页面/重构页面用这套，不要每页重新发明：

| 关注 | 库 | 备注 |
|---|---|---|
| 数据获取 | `@tanstack/react-query` | Provider 见 `components/QueryProvider.tsx`，已挂 layout |
| 表单 | `react-hook-form` + `zod` + `@hookform/resolvers` | — |
| 动效 | Framer Motion (`motion/react`) | 统一预设在 `lib/motion.ts`（`lvStaggerContainer` / `lvStaggerItem` / `lvFadeUp` 等） |
| i18n | `next-intl` | 文案 `t('xxx')`，文件 `i18n/zh.json` + `i18n/en.json` |
| 复杂交互组件 | Radix (`@radix-ui/react-dialog/popover/toast`) + `vaul` (Drawer) + `cmdk` (Command Menu) | 不引入 shadcn 整套，simple 组件继续手写 |
| PWA | `@serwist/next` (serwist) | sw 源在 `app/sw.ts`，manifest `public/manifest.webmanifest` |
| 错误上报 | `@sentry/nextjs` | DSN 用 `NEXT_PUBLIC_SENTRY_DSN`，配置 `sentry.*.config.ts` + `instrumentation*.ts` |
| 单测 | `vitest` + `@testing-library/react` + jsdom | `npm run test`；测试文件就近 `lib/*.test.ts` |

## 客户端 vs 服务端

- 谨慎 `"use client"`，只在需要交互或浏览器 API 时用
- 客户端状态：Zustand（`stores/`）
- 服务端状态：TanStack Query
- 流式：`fetch + ReadableStream`，不用 `EventSource`（cookie 认证约束）

## 移动端检查项（每个页面 PR 必做）

- [ ] 375px 单手能用（Chrome DevTools 切到 iPhone SE）
- [ ] 用 `100dvh` 不用 `100vh`
- [ ] `safe-area-inset-{top,bottom}` 处理刘海屏
- [ ] 触摸目标 ≥ 44px
- [ ] 不依赖 hover 的状态切换
- [ ] play 页移动端单栏 + 底部抽屉（不是双栏挤压）
- [ ] navbar 移动端用底部 tab bar（首页 / 发现 / 创作 / 我；历史已并入「我」页预览 + `/history` 全量页），桌面端顶部

## Dev 命令

```bash
npm install
npm run dev          # 端口 3000，被占用会自动切 3001
npm run dev:fresh    # 清 .next 再 dev（HMR 异常时用）
npm run build        # 生产构建
npm run lint         # ESLint（仅锁旧 token）
npm run lint:strict  # 同上 + max-warnings=0
npm run test         # vitest 单测
npm run test:watch   # vitest watch 模式
```

dev server 默认开 Turbopack，本机 `darwin/arm64` native binding 缺失会自动回退；如报错就显式：

```bash
npx next dev --webpack
```
