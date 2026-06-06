# admin.inkwild.app 设计与实施计划

**Owner:** jie · **Started:** 2026-05-18 · **Status:** 锁定方向，待动手

独立 admin 子域名，承接所有"非用户"职能（模型 / 成本 / 审计 / 用户管理 / 内容审核 / 总览）。视觉、工程、部署都跟主站隔离。

---

## 1. 背景

权限拆分已落地：创作工坊（worlds / scripts）开放给普通用户走 `/api/workshop/*`，admin 只剩模型管理 + 分析 + 审计写入。但 admin 站 UI 严重滞后——`/admin` 还把工坊和模型混在一起，`/admin/analytics` 是一个裸 `<ul>`，审计日志后端有数据但前端零界面，用户管理 / 内容审核完全没有。

要做的事：起一个独立的 admin 站把这些补齐。

---

## 2. 锁定决策

| # | 决策 | 备注 |
|---|------|------|
| D1 | Admin 独立于主站视觉系统 | 不复用 v2.2 / `--lv-*` / `.lv-t-*`，桌面优先 |
| D2 | 独立 Next.js 子项目 `admin-frontend/`，部署到 `admin.inkwild.app` 子域名 | 不污染主站构建 |
| D3 | 视觉以 `InkWild Admin.html` 原型为基线 | 1:1 复刻色板/字号/密度/组件；3 处例外见 §5 |
| D4 | 删除 `backend/api/admin.py` 里 800+ 行重复工坊端点 | admin 也是 user，走 `/api/workshop/*` 即可；老 `/admin` 工坊前端页一并清理 |
| D5 | `can_create` 默认 `False`（白名单制） | 注册不自动给创作权，admin 站手动开 |
| D6 | 内容强制下架先静默 + 写审计 | 不通知作者，举报系统出来再升级 |
| D7 | Admin 不能撤销自己的 `is_admin` | safety lock，避免单点锁死 |
| D8 | 图表用 Recharts | 不手写 SVG |

---

## 3. IA（Sidebar 6 项）

1. **Dashboard 总览** — KPI 卡 + 告警条 + 最近事件
2. **用户管理** — list / 搜索 / 详情 / 改 is_admin · can_create · status
3. **内容审核** — 跨用户列出已发布 worlds/scripts / 强制下架 / 看 moderation flags
4. **模型管理** — Providers / Models / Slot Bindings 三 tab
5. **成本分析** — KPI + 30 天趋势 + Provider/Slot/Model 分布 + 异常 session
6. **审计日志** — list / 多维筛选 / payload 展开 / 复制

---

## 4. 视觉令牌（直接从原型抠出来落库）

```
背景:        #faf9f5
表面 (card): #ffffff
分割线:      rgba(0,0,0,0.06)
主文本:      #29261b
次要文本:    rgba(41,38,27,0.6)
弱文本:      rgba(41,38,27,0.45)
Accent:      #5B5BD6
Accent-soft: color-mix(in oklch, #5B5BD6 12%, white)
Success:     绿系（具体值原型抠）
Danger:      红系
Warning:     橙系
Info:        蓝系

字号: 13px 基准
圆角: 6-7px（卡片 / 输入框）/ 4px（badge / 小标签）
密度: regular（compact / comfy 可选，存 localStorage）
字体: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif
等宽: ui-monospace, "SF Mono", Menlo, monospace
数字: font-variant-numeric: tabular-nums（表格 + KPI 必加）
```

---

## 5. 跟原型不一样的 3 处

1. Tweaks 浮窗不进生产
2. 图表用 Recharts（视觉调到接近，不是像素级一致）
3. 用户管理 / 内容审核 原型没画，沿用同套视觉，**实现前先出 wireframe**

---

## 6. 技术栈

```
Framework:   Next.js 16 (SPA mode, output: 'export'), React 19, TypeScript
样式:        Tailwind v4，独立 config，不引主站 globals.css
数据:        TanStack Query
表单:        React Hook Form + Zod
组件库:      shadcn/ui (Dialog / Dropdown / Popover / Toast / Select / Tabs)
图表:        Recharts
路由:        Next.js App Router
图标:        lucide-react
不上:        Framer Motion / next-intl / Storybook / SSR
```

---

## 7. 部署 / Auth

- 子域名 `admin.inkwild.app`，构建产物独立部署（nginx / Vercel / Cloudflare Pages 任选）
- Cookie domain 设为 `.inkwild.app`，复用主站登录态
- Admin 站启动时拉 `/api/auth/me`，`is_admin === false` 直接踢回主站登录页
- API 请求继续打 `backend` 的 `/api/admin/*`（同域 / CORS 配 admin 子域）

---

## 8. 后端需新增接口

| 模块 | Endpoint |
|------|----------|
| 用户管理 | `GET /api/admin/users` (list + 搜索 + 筛选 + 分页) |
| | `GET /api/admin/users/{id}` (详情 + 登录方式 + session + 创作统计) |
| | `PATCH /api/admin/users/{id}` (改 is_admin / can_create / status，写审计) |
| 内容审核 | `GET /api/admin/content/worlds` (跨用户) |
| | `GET /api/admin/content/scripts` (跨用户) |
| | `POST /api/admin/content/worlds/{id}/withdraw` (绕 ownership) |
| | `POST /api/admin/content/scripts/{id}/withdraw` |
| 审计日志 | `GET /api/admin/audit-logs` (筛选 action / admin / time range / 分页) |
| | `GET /api/admin/audit-logs/{id}` |
| Dashboard | `GET /api/admin/dashboard/kpis` |
| | `GET /api/admin/dashboard/recent-events` |
| | `GET /api/admin/dashboard/active-sessions` (Redis 或 last_action_at 阈值) |
| 成本分析 | `GET /api/admin/analytics/cost-trend?days=30` (按日 bucket) |
| | `GET /api/admin/analytics/cost-by-model` |
| | `GET /api/admin/analytics/cost-by-slot` |
| | `GET /api/admin/analytics/expensive-sessions` |
| 现有保留 | `admin_models.py` 全套 / `admin_analytics.py` 两个聚合接口 |

---

## 9. 分期交付

按"垂直切片"做，每期 BE+FE 一起，不堆全 BE 再做 FE。

| Phase | 范围 | 估时 |
|-------|------|------|
| **P0** | `admin-frontend/` 脚手架 · AdminShell（Sidebar + Topbar）· 视觉 token · auth 重定向 | 0.5d |
| **P1** | 审计日志 BE + FE（最容易出价值的 E2E，验证整套链路） | 1d |
| **P2** | 模型管理 FE（BE 已完整，按原型复刻三 tab） | 1.5d |
| **P3** | 成本分析 BE 新接口 + FE | 1d |
| **P4** | Dashboard BE 聚合接口 + FE | 1d |
| **P5** | 用户管理（先 wireframe → 确认 → BE + FE，详情用右侧抽屉） | 1.5d |
| ~~P6~~ | ~~内容审核~~ — **延后**，等用户内容规模上来再做；前端 stub 页保留显示 "未实施" | — |
| **P7** | 子域名 + cookie domain + 部署 + 联调 | 0.5d |
| **P8** | 清理：删 `admin.py` 工坊端点 + 老 `/admin` 前端页 + 主站重定向 | 0.5d |

共 ~8.5 天有效开发时间。

---

## 10. 非范围（明确不做）

- 不做举报系统（用户没有举报入口）
- 不做审计日志回滚功能（实现复杂、价值低）
- 不做 admin 用户分角色（只有"是 admin"和"不是"两态；细化角色等真需要再说）
- 不做 admin 站 i18n（运营全中文）
- 不做 admin 站移动端（桌面优先，平板能看就行）
- 不做 admin 站 dark mode（一期不加，加了再说）
- 不做 Tweaks 浮窗（设计调试器，生产不要）
- 不做主站正在用的 Framer Motion / next-intl / Storybook 体系

---

## 11. 验收口径

- 6 个模块功能可用
- 所有 admin 写操作进 `admin_audit_logs`
- `admin.inkwild.app` 子域名可访问，非 admin 用户被踢
- 主站 `/admin` 路由整体下线（重定向到子域名或 404）
- 老的 `/api/admin/*` 工坊端点全部删除，无遗留调用
