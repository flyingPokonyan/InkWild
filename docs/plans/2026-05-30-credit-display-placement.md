# 积分展示补全（PC + 移动 + Play）

> 设计日期 2026-05-30。目标：把用户积分余额补到缺失的展示位——移动端（全程缺）和 Play 页
> （两端都缺，且这是积分真正被回合回扣、会抛 `credits_insufficient` 的地方）。桌面浏览主流程
> 已有，不动。

## 背景 / 现状

积分后端已就绪：`GET /api/credits/balance`（`balance / lifetime_granted / lifetime_spent`）
+ `GET /api/credits/transactions`，按 action 粒度回扣（每回合 / 每次生成一行 ledger），余额不足时
SSE 抛 `credits_insufficient`。

前端已有 `CreditBalanceChip`（金色药丸 → 点开 `Drawer` 看余额 + 累计 + 流水），目前**只挂在
`ProductNav` 右上角**。覆盖现状：

| | 浏览页 | Play 页 |
|---|---|---|
| 桌面 | ✅ ProductNav chip（仅 `/`、`/discover`、`/history`、`/workshop`） | ❌ 无 |
| 移动 | ❌ 无（ProductNav 在 ≤768px `display:none`；MobileTopBar 各页自管 right 槽，无一页塞 chip） | ❌ 无 |

补充事实：
- `/worlds/[id]`（世界详情）是**刻意的无 chrome 沉浸海报**——桌面零顶栏、移动只有透明的返回+⋯。
  **本期不放 chip**（非消费点、破调性、不足有硬拦截兜底、真正该看余额的是 Play 页）。
- `/play/[id]` 头部是 `GameHeader`（`components/GameHeader.tsx`），桌面 + 移动共用。
- `getQueryClient()`（`lib/query-client.ts`）是浏览器单例，可在 React 外（store）调用做 invalidate。
- **全代码没有任何地方 invalidate 余额 query**——chip 现在只靠 30s staleTime，回合扣分后不会即时更新。

## 决策（已与用户确认）

1. **Play 页**：常驻轻量余额 chip（沉浸态低调，低余额变色）。
2. **移动浏览页**：`MobileTopBar` 右槽全局默认塞 chip（登录用户、且页面没自定义 right 时）。
3. **世界详情页**：不放。
4. **桌面浏览主流程**：已有，不动。

## 目标覆盖矩阵

| | 浏览页 | Play 页 |
|---|---|---|
| 桌面 | ProductNav chip ✅ 已有 | GameHeader chip 🆕 |
| 移动 | MobileTopBar chip 🆕 | GameHeader chip 🆕 |

两个新挂载点：**MobileTopBar**（移动浏览）+ **GameHeader**（Play，两端共用）；加共享组件扩展 + 一处数据刷新。

## 设计

### A. 扩展 `CreditBalanceChip`（复用，不另造）

`components/CreditBalanceChip.tsx`：

- 加 prop `variant?: "chip" | "plain"`，默认 `"chip"`：
  - `"chip"`（现状）：金色填充药丸（`--lv-accent-soft` 底 + `--lv-accent` 字），用于 ProductNav + MobileTopBar。
  - `"plain"`：无填充背景、更小（icon 12 + 数字）、低对比，用于 Play 页沉浸态。仍是按钮，点击开同一个 Drawer。
- 加**低余额着色**（两 variant 共用），按 `balance.balance` 决定主色：
  - `> LOW_BALANCE_THRESHOLD` → `--lv-accent`（金，正常）
  - `0 < balance ≤ LOW_BALANCE_THRESHOLD` → `--lv-warn`（琥珀 `#c9a36a`）
  - `≤ 0` → `--lv-danger`（珊瑚红 `#ef8276`）
  - `LOW_BALANCE_THRESHOLD` 用模块常量，初值 `50`，加注释「可调，未来可换成"约 N 回合"启发式」。
- Drawer 内容、查询逻辑（`useQuery(CREDIT_BALANCE_QUERY_KEY)`）保持不变。

### B. 移动浏览页 — `MobileTopBar`

`components/MobileTopBar.tsx`：

- 当前 `right` 槽完全由调用页提供。改为：**未传 `right` 且用户已登录时，默认渲染
  `<CreditBalanceChip variant="chip" />`**。
  - 取登录态：`useAuthStore((s) => s.user)`（MobileTopBar 已是 `"use client"`，可直接用）。
  - 页面已自定义 `right`（如 `/worlds/[id]` 的 ⋯）→ 保留页面优先，**不塞 chip**（与"世界详情不放"的决策一致，零冲突）。
- 效果：discover / history / workshop 等用 MobileTopBar 且没占 right 的页，移动端自动有余额 chip。

### C. Play 页（桌面 + 移动）— `GameHeader`

`components/GameHeader.tsx`：

- 在 header 右侧控件簇（drawer toggle / pause 那一侧）加 `<CreditBalanceChip variant="plain" />`，
  紧邻返回控件对侧。GameHeader 桌面 + 移动共用，一处覆盖两端 Play。
- 沉浸态：平时极简、低对比；低余额由 A 的着色自动变琥珀 / 珊瑚红提醒。
- 点击打开同一个流水 Drawer（复用现成）。

### D. Play chip 实时刷新（关键）

- 现状无任何 invalidate，常驻 chip 不刷新会误导（玩家扣了分还显示旧值）。
- 在 `stores/game.ts` 每回合 stream 到 `done`（以及结局结算）后，调用
  `getQueryClient().invalidateQueries({ queryKey: CREDIT_BALANCE_QUERY_KEY })`。
  - `CREDIT_BALANCE_QUERY_KEY` 从 `lib/credits.ts` 导入；`getQueryClient` 从 `lib/query-client.ts` 导入。
  - 落点：store 里现有的 "done 解锁" 处（grep `done` / "玩家已在 done 解锁" 注释附近，多个 action 路径都要覆盖：普通回合 / resume / retry）。

## 不在本期范围

- 不重做 `credits_insufficient` 硬拦截流程（`api/game.py` 抛 + `lib/sse.ts` 已识别 code）；chip 的
  低余额着色与它呼应即可。
- 充值 / 购买入口：当前无充值页，低余额态止于「视觉提醒」，不加「去充值」按钮。
- 世界详情页 `/worlds/[id]`：不动。
- `BottomTabBar`：不动（Play 页本就隐藏它；移动浏览靠 MobileTopBar 覆盖）。

## 影响面清单

| 文件 | 改动 |
|---|---|
| `frontend/components/CreditBalanceChip.tsx` | 加 `variant` prop + 低余额着色 + `LOW_BALANCE_THRESHOLD` 常量 |
| `frontend/components/MobileTopBar.tsx` | 未传 `right` 且登录时默认渲染 chip |
| `frontend/components/GameHeader.tsx` | 右侧加 `<CreditBalanceChip variant="plain" />` |
| `frontend/stores/game.ts` | turn `done` / 结算后 invalidate 余额 query |
| `frontend/i18n/zh.json` + `en.json` | 如新增低余额/文案 key（若需要） |

桌面浏览页（ProductNav）零改动。

## 测试（轻量 vitest）

- `CreditBalanceChip`：
  - `variant="plain"` 与 `"chip"` 渲染差异（无填充 vs 填充）。
  - 着色阈值：`balance > 50` 金 / `0 < balance ≤ 50` 琥珀 / `≤ 0` 珊瑚红。
- `MobileTopBar`：登录且未传 `right` → 渲染 chip；未登录 → 不渲染；传了 `right` → 用页面的，不塞 chip。
- 余额刷新：模拟 turn `done` 后 `CREDIT_BALANCE_QUERY_KEY` 被 invalidate（store 单测或对 `getQueryClient` 打桩）。

## 移动端自检（PR 必做）

- [ ] 375px：MobileTopBar chip 不挤压标题、触摸目标 ≥ 44px。
- [ ] Play 页 `GameHeader` chip 在 375px 不与返回/抽屉控件碰撞。
- [ ] 低余额着色在深色舞台底上对比足够。
