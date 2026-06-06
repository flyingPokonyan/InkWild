# 积分体验三件套：开局 loading 提前 + 抽屉重组 + 流水刷新

> 设计日期 2026-05-30。三个独立但相关的改动：
> Q1 开局 loading 提前结束；Q2 积分入口分场景重组（桌面头像下拉 / 移动 chip / play 本局抽屉）；
> Q3 回合后流水实时刷新。

## 总体 IA：两类视图，一套内容组件

抽出 **`CreditWalletView({ scope, sessionId })`** 作为唯一内容组件（余额 + 累计获得/消耗 + 流水列表），
所有入口都渲染它 → 移动端 / 桌面 / play 天然一致。
- `scope="all"`：完整「我的积分」（全部流水）。
- `scope="session"`：「本局积分」（仅本局流水，需 `sessionId`）。

## Q1 — 开局 loading 提前（纯后端）

**根因**：setup 页 `markReady` 等 `state_update`，而后端把完整 `state_update` 放在开局旁白流式**之后**
才发（开局序列：导演算状态 → 内部 `state_ready`(不发前端) → 旁白流式 → `state_update`）。

**改法**：在开局流式路径里，导演算好初始 `game_state` 后、**旁白开始流式之前**，先给前端发一个
`state_update`（携带初始 game_state + 当前可用 quick_actions，可为空）。前端 `onStateUpdate` 据此提前
`markReady` → setup 页提前跳转；落到 play 页 `gameState` 已在手，舞台直接渲染，旁白在 play 页流出来。

- 落点：`backend/api/game.py` 开局/start 流式端点对应的 orchestrator 开局路径（实现时定位精确行；
  参考 `engine/orchestrator.py` 中 `apply_state_updates` 之后、`yield {"type":"narrative"}` 之前）。
- 约束（CLAUDE.md）：SSE payload 带 `version:1`；`state_ready` 是内部事件、**不能**直接发前端——
  这里发的是正常的 `state_update`（前端已识别），不是 `state_ready`。
- 幂等：前端 `onStateUpdate` 会被调用两次（提前的初始态 + 结尾的最终态），都是 `set({gameState})`，幂等安全。
- 前端 play 页 / `start-game-gate` / loading 护栏**一行不动**。

## Q2 — 积分入口重组

| 场景 | 入口 | 打开 |
|---|---|---|
| 桌面 · 非 play | **头像下拉**（移除顶栏独立 chip）：下拉显示余额数字（按 level 着色）+「我的积分」行 | 完整视图（vaul 底部抽屉，scope=all） |
| 移动 · 非 play | **保留 MobileTopBar chip** | 完整视图（scope=all） |
| Play · 桌面+移动 | **GameHeader plain chip** | **本局**抽屉：复用案件板 overlay shell（桌面右面板 / 移动底 sheet），scope=session |

- 桌面：`ProductNav` 顶栏移除 `<CreditBalanceChip />`；头像下拉里加余额行 +「我的积分」入口，点击开完整抽屉。
- 移动：`MobileTopBar` 的默认 chip 不变（移动端没头像下拉，chip 即自然落点；与桌面"各自导航露出余额"一致）。
- Play：`GameHeader` 的 plain chip 点击 → 本局抽屉（案件板同款 overlay）。

## Q3 — 流水刷新

**根因**：上轮只 invalidate 了余额 query，没 invalidate 流水 query → 余额动了、流水要刷页面才出。

**改法**：`stores/game.ts` 回合 `done` 时，除 `CREDIT_BALANCE_QUERY_KEY` 外也 invalidate 流水 query。
流水 query key 带上 `scope`/`sessionId`（如 `["credits","transactions",scope,sessionId]`），保证本局抽屉
也实时刷新。

## 后端配套（本局流水过滤）

- `GET /api/credits/transactions` 加可选 `session: str | None` 参数 → `WHERE ref_id == session AND ref_type=="session"`。
- 确保 play 扣费 ledger 带 `ref_type="session"/ref_id=session_id`，**含开局那笔**：现在开局
  `_stream_with_credits(..., session_id=None, ...)`（`api/game.py`），session 此刻刚创建——需要把新建的
  session_id 透传给 reserve，使开局扣费也带 ref。否则本局抽屉缺第一条。

## 组件结构

| 文件 | 改动 |
|---|---|
| `frontend/components/CreditWalletView.tsx` | 🆕 内容组件（从现 `CreditBalanceChip` Drawer body 抽出），props `scope` / `sessionId` |
| `frontend/components/CreditBalanceChip.tsx` | chip 触发器 + 抽屉；`variant` chip/plain；`scope`/`sessionId`；play 用 overlay shell |
| `frontend/components/PlayOverlayDrawer.tsx` | 🆕 从 `UnifiedSidePanel` 抽的共享 overlay shell（scrim + 桌面右面板/移动底 sheet）；干净就抽并让案件板也用，不干净就按同 token 复刻 |
| `frontend/components/GameHeader.tsx` | plain chip 改为开本局抽屉（scope=session, sessionId） |
| `frontend/components/MobileTopBar.tsx` | 默认 chip 不变（scope=all） |
| `frontend/components/ProductNav.tsx` | 移除顶栏独立 chip；头像下拉加余额行 +「我的积分」入口 |
| `frontend/lib/credits.ts` | 流水 query key 带 scope/sessionId；`fetchCreditTransactions(session?)` 支持 session 过滤 |
| `frontend/stores/game.ts` | done 时 invalidate 余额 + 流水 |
| `frontend/i18n/zh.json` + `en.json` | 新增「本局积分」标题 key |
| `backend/api/credits.py` | transactions 加 `session` 过滤参数 |
| `backend/api/game.py` | 开局扣费透传 session_id 作 ref；开局流式提前发 state_update |

## 不在本期范围

- 不重做 `credits_insufficient` 硬拦截流程。
- 不新增移动端头像/「我的」中心（移动端积分继续走 MobileTopBar chip）。
- 不改充值（无充值页）。

## 测试（轻量）

- `CreditWalletView`：scope=all / session 各拉对应 query key。
- `lib/credits`：`creditLevel`（已有）；transactions query key 带 scope/sessionId 的形态。
- 后端 `test_credits`：transactions `session` 过滤只返回该 session 的行。
- 手验：开局 loading 提前（进 play 看旁白流）；play 本局抽屉只显示本局、回合后自动刷新；桌面头像下拉显示余额；移动 chip 一致。
