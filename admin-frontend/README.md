# admin-frontend

InkWild 管理控制台。独立站，部署到 `admin.inkwild.app`。

不复用主站 v2.2 视觉规范，桌面优先。设计基线见 `../InkWild Admin.html` 原型 + [`../docs/plans/admin-console-2026-05.md`](../docs/plans/admin-console-2026-05.md)。

## 模块（6 个）

| 路由 | 功能 |
|------|------|
| `/` | Dashboard 总览（KPI + 缺单价告警 + 最近事件） |
| `/users` | 用户管理（list / 抽屉详情 / 改 is_admin · can_create · status） |
| `/content` | 内容审核（**P6 延后未实施**） |
| `/models` | 模型管理（Providers / Models / Slot Bindings 三 tab + 增删改 Modal） |
| `/cost` | 成本分析（KPI + 趋势 + Provider/Model 拆分 + 异常 session） |
| `/audit` | 审计日志（命名空间筛选 + 时间范围 + payload 展开） |

## 本地跑

```bash
# 一次性
cp .env.example .env.local
npm install

# 日常
npm run dev   # 端口 3001
```

需要主站后端跑在 `http://localhost:8000`。

## 部署

1. **后端**（共享）：
   - 设置环境变量：
     ```bash
     SESSION_COOKIE_DOMAIN=.inkwild.app
     CORS_EXTRA_ORIGINS=https://admin.inkwild.app,https://inkwild.app
     ```
   - 部署即可。

2. **admin-frontend**（新）：
   - 设置环境变量：
     ```bash
     NEXT_PUBLIC_API_URL=https://api.inkwild.app
     NEXT_PUBLIC_MAIN_SITE_URL=https://inkwild.app
     ```
   - `npm run build && npm start`，部署到 `admin.inkwild.app`。
   - 任何静态托管都可以（Vercel / Cloudflare Pages / Nginx），无 SSR 强依赖。

3. **联调**：
   - 主站登录后 cookie 写到 `.inkwild.app`，admin 子域名自动复用。
   - 非 admin 用户访问 admin 任意页 → 跳回主站登录页。
   - `AuthGate` 见 `components/AuthGate.tsx`。

## 技术栈

- Next.js 16 + React 19 + TypeScript
- Tailwind v4（独立 config，不引主站 globals.css）
- TanStack Query（数据） + Recharts（图表） + lucide-react（图标）
- 设计令牌：oklch 色板 + 7px 圆角 + 13px 基准字号，全部在 `app/globals.css`

## 注意

- 不上 Framer Motion / next-intl / Storybook / shadcn — admin 不需要
- 没有移动端适配，桌面优先；平板能看就行
