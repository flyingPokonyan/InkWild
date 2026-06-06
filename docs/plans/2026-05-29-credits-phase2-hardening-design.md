# 积分系统 Phase 2 设计（健壮性硬化）

> 创建：2026-05-29 · 状态：设计待评审 · 范围：纯健壮性 / 正确性硬化（**不含变现功能**）
> 前置：[`2026-05-29-credits-phase1-design.md`](2026-05-29-credits-phase1-design.md)（计量 + L2 拦截 + admin）已上线。
> 与代码冲突时以代码为准。

## 1. 背景与目标

Phase 1 已落地：cost-pegged 计量、两动作边界（游玩回合 / 生成任务）的 L2 预检 + 真实结算、append-only 台账、admin 管理与可编辑经济参数。本期**不加任何新产品功能**（充值 / 签到 / 逐回合明细等仍在 OUT），只把已有经济引擎做扎实，为正式上线收钱打底。

Phase 1 自审暴露的健壮性缺口：

| # | 缺口 | 风险 |
|---|---|---|
| 1 | **跨动作并发泄漏**：L2 只读 `balance >= estimate`，无持仓预留 | 余额刚够一次预估额的用户可同时开多个动作（多标签页 / 同时"游玩+生成"），每个 gate 都过 → 超支远超"单动作"上限。`SessionLock` 只串行单 session，挡不住跨 session/跨任务 |
| 2 | **结算不可靠**：settle 在 `finally` + fail-open 只记日志 | DB 抖动 / 进程崩溃 / SSE 客户端中途断连 → 真实用量不入账，**静默漏扣**。无重试 / outbox |
| 3 | **无对账入口**：模型注释称"可对账"但无实现 | `balance` 一旦与台账漂移无法发现、无法修 |
| 4 | **计费精度**：输入恒按 cache-miss 单价 | 命中 prompt 缓存时**高估**，在多扣用户。`token_usage` / usage 事件已带 cache 命中列却没用于计费 |
| 5 | **生成失败一律扣**：Phase 1「按实际扣不退」 | 完全失败（0 交付）仍扣费，体验差 |
| 6 | **fail-open 偏松**：gate/settle 出错一律放行 | 上线收钱后需可收紧为 fail-safe |

## 2. 范围

### IN ✅

- **L3 持仓预留**（`held_units` + `credit_holds` 表）：原子预留预估额，关闭跨动作超支泄漏。
- **可靠结算**：`credit_holds` 兼作结算 outbox；settle 失败可重放，进程崩溃留下的孤儿 hold 由 sweep 恢复。
- **完全失败退款**：动作 0 交付 → 不扣（释放预留）；部分交付 → 按真实消耗扣。
- **用户流水语义在新模型下定稿**：按动作一条净额；持仓**永不写台账**；完全失败写一条 delta=0「未扣费」信息行；`cost_cents` 仍仅 admin 可见。
- **cache-aware 计费**：命中部分按 `cached_input_price` 计（缺配置则回退全价 = 现行为）。
- **对账**：`balance == Σ ledger.delta` 与 `held_units == Σ 活跃 holds.estimate` 两条不变式的校验 + 修复（admin 端点 + 轻量周期任务）。
- **fail-mode 开关**：`gate_fail_mode = open | safe`（admin 可编辑，默认 open）；漏计 / 结算失败 / 孤儿 / 漂移结构化埋点。

### OUT 🔵（仍属后期）

- 充值 / 付费 / 订阅 / 签到等**赚取**入口。
- 逐回合 / 逐调用级流水明细（用户端维持按动作粒度）。
- 把 `gate_fail_mode` 默认切到 `safe`（真正收钱前不切）。
- `TokenUsage` 分析口径的 cache-aware 重算（与计费口径对齐留作 follow-up，见 §6）。

## 3. 架构总览

单一核心抽象：**`credit_holds` 表既是持仓记录，又是可靠结算 outbox。** 一个动作的生命周期：

```
reserve(预留)  →  执行动作  →  settle(释放 + 按实扣)
                              └─ 失败/崩溃 → sweep(扫描恢复)
```

两条不变式贯穿全程，使一切可对账：

- **I1**：`wallet.balance_units == Σ credit_ledger.delta_units`
- **I2**：`wallet.held_units == Σ (credit_holds WHERE status='held').estimate_units`

`balance` 只在 **settle** 变动并写一条台账；持仓只动 `held_units` / `credit_holds`，**不碰台账**。这正是选 `held_units` 而非 provisional-debit 的理由：台账保持每动作一条净额，对账干净，用户流水无预留/释放噪音、余额不闪烁。

## 4. 数据模型（单个 Alembic 迁移）

### 4.1 `credit_wallets` 加列

| 列 | 类型 | 说明 |
|---|---|---|
| `held_units` | BigInteger, NOT NULL, default 0 | 当前预留中的总额；`available = balance_units − held_units` |

### 4.2 新表 `credit_holds`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid pk | |
| `user_id` | uuid, FK, index | |
| `action` | String(16) | `game` / `world` / `script` |
| `ref_type` | String(16), nullable | `session` / `task` |
| `ref_id` | String(64), nullable | session_id / task_id |
| `estimate_units` | BigInteger | 预留额（= 该动作预估额） |
| `charged_units` | BigInteger, nullable | settle 后实扣（完全失败 = 0） |
| `usage_json` | JSON/Text, nullable | settle 失败时缓存的累加器快照，供重放 |
| `status` | String(16) | `held` / `settled` / `settle_failed` |
| `attempts` | Integer, default 0 | settle 重试计数 |
| `last_error` | Text, nullable | |
| `created_at` | datetime, index | 预留时刻；孤儿判定用 |
| `settled_at` | datetime, nullable | |

索引：`(status, created_at)`（sweep 扫描）、`(user_id, status)`（对账）。

### 4.3 `provider_models` 加列

| 列 | 类型 | 说明 |
|---|---|---|
| `cached_input_price_cents_per_million_tokens` | Integer, nullable | 命中 prompt 缓存的输入单价；**null ⇒ 回退到 `input_price`（行为不变）** |

### 4.4 `credit_config` 加列

| 列 | 类型 | 说明 |
|---|---|---|
| `gate_fail_mode` | String(8), default `'open'` | `open`（出错放行+埋点）/ `safe`（出错拦截） |

### 4.5 结构化常量（非 admin 可调，放代码）

- `CREDIT_HOLD_TTL_SECONDS = 1800`：`held` 超此时长无 settle 视为孤儿（远超最长动作）。
- `CREDIT_SETTLE_MAX_ATTEMPTS = 5`：settle 重放上限，超则保底处理（见 §5.4）。

## 5. 机制与数据流

### 5.1 Gate（reserve）—— 取代 `can_afford`

`reserve(db, user_id, action, ref_type, ref_id) -> hold_id`：

```sql
-- 先 get_or_create_wallet（懒发放沿用 Phase 1）
UPDATE credit_wallets
  SET held_units = held_units + :estimate
  WHERE user_id = :u AND balance_units - held_units >= :estimate
  RETURNING id;                      -- 0 行 ⇒ raise InsufficientCredits
INSERT INTO credit_holds(..., estimate_units=:estimate, status='held');  -- 同一事务
```

并发的第二个动作因 `balance − held` 已减少而被拦 → 泄漏关闭（**I2** 维持）。

### 5.2 Settle（释放 + 按实扣）—— `finally`，带 `delivered: bool`

```
hold = 取 status='held' 的 hold
if not delivered:                      # 完全失败（0 交付）→ 免费
    tx:
        held_units -= estimate
        hold.status='settled', charged_units=0, settled_at=now
        # delta=0 信息行（用户可见"失败·未扣费"）：
        ledger(delta=0, balance_after=当前 balance, kind=f"{debit_kind}_failed",
               category, ref_*, cost_cents=round(已消耗真实成本) 或 null)
    return 0
actual = price(accumulator)            # cache-aware × 倍率，见 §6
tx (重试至多 CREDIT_SETTLE_MAX_ATTEMPTS):
    held_units -= estimate
    if actual > 0:
        balance_units -= actual; lifetime_spent_units += actual
        ledger(delta=-actual, balance_after=新 balance, kind=debit_kind,
               category, ref_*, cost_cents=round(cost_fen))
    # actual==0 且 delivered：仅释放预留，不写台账行
    hold.status='settled', charged_units=actual, settled_at=now
on 持久失败:
    hold.status='settle_failed', usage_json=快照, attempts++, last_error=...
    # 不释放 held_units —— 余额保持被占用，等 sweep 重放（失败朝"保护余额"倾斜）
```

台账写入规则（决定用户流水形态）：

| 情形 | 台账行 |
|---|---|
| delivered=True, actual>0 | 一条 debit（−actual） |
| delivered=True, actual=0 | 不写 |
| delivered=False（完全失败） | 一条 delta=0「失败·未扣费」行 |

**`delivered` 判定**：
- 生成任务：`generation_task_service` 给出"是否产出≥1 个可交付成果（世界/剧本/图）"；报错于产出任何成果之前 ⇒ `delivered=False`。
- 游玩回合：`_stream_with_credits` 记录"终止前是否发过内容/叙事事件"；正常完成或发过内容 ⇒ True，未发任何内容即报错 ⇒ False。

### 5.3 接入点改造

- **游玩**（`api/game.py` `_stream_with_credits`）：进流前 `reserve`，`finally` 内 `settle_hold(hold_id, acc, delivered=...)`。gate/settle 仍走独立 DB session、受 `gate_fail_mode` 约束。
- **生成**（`generation_task_service`）：`_credit_gate` → `_credit_reserve`，`_credit_settle` 传 `delivered`。

### 5.4 Sweep（崩溃 / 失败恢复）

轻量 asyncio 周期任务（`main.py` lifespan 内起，复用 `usage_recorder` 的 fire-and-forget 模式，**不引入 Celery/APScheduler**）+ admin 手动触发端点。每轮（默认 ~300s）：

- `status='settle_failed'`（已有 `usage_json`）→ 重放：按快照算 actual，应用 debit + 释放预留，标 `settled`。超 `CREDIT_SETTLE_MAX_ATTEMPTS` → 保底：用快照 actual 强制结算（宁可扣已知真实成本，不留 held 永久泄漏）+ 高优日志。
- `status='held'` 且 `now − created_at > CREDIT_HOLD_TTL_SECONDS`（孤儿，来自进程崩溃）→ 先尝试从 `token_usage` 按 `ref_id` + 时间窗重建真实成本扣除；无记录则释放预留（forgive，与 fail-open 一致）。标 `settled`。

> 孤儿恢复保证 **`held_units` 不会因崩溃永久泄漏**，否则会长期挤占该用户可用余额。

## 6. cache-aware 计费

usage 事件已带 `cache_hit_tokens` / `cache_miss_tokens`（`deepseek.py` / `openai_compatible.py` 已填），仅累加器与定价没用。

- `UsageAccumulator.add` + `llm/router.py:_accumulate_usage` 增 `cache_hit_tokens` / `cache_miss_tokens`。
- `usage_to_cost_fen` 改为：
  ```
  miss = cache_miss_tokens 若有，否则 (input_tokens − cache_hit_tokens) 再 clamp(≥0)，缺则全算 miss
  cached_price = pricing.cached_input_price ?? pricing.input_price        # null ⇒ 全价（行为不变）
  token_fen = (miss*input_price + cache_hit_tokens*cached_price + output_tokens*output_price)/1e6
  return token_fen + image_count*image_price
  ```
- 缺 cache 字段（provider 未上报）⇒ 全部按 miss 计 = Phase 1 行为，安全回退。

> **口径一致 follow-up**：`engine/cost_guardrail` 与 `estimate_usage_cost_cents`（分析口径）目前各算各的成本。本期实现时尽量抽共享的 cache-aware 核心，避免计费成本与分析成本两套数；若一次做不完，分析口径对齐留作独立 follow-up（OUT）。

## 7. 对账

`reconcile(db, user_id | all, repair=False) -> 报告`：

- `expected_balance = Σ ledger.delta`（I1 权威源）；`expected_held = Σ holds(status='held').estimate`（I2 权威源）。
- 与 `wallet.balance_units` / `held_units` 比对，输出 `balance_drift` / `held_drift`。
- `repair=True`：按权威源校正 wallet（balance ← Σledger，held ← Σ活跃holds），写日志。
- 入口：`GET /api/admin/credits/reconcile?user_id=`（dry-run 报告，可全量）、`POST /api/admin/credits/reconcile`（修复，审计）。sweep 周期任务顺带跑漂移检查并埋点。

> 正常情况下两条不变式恒成立；出现漂移即代表 settle/sweep 有 bug 或人工改过库 —— 对账是安全网 + bug 探测器。

## 8. fail-mode 与可观测

- gate / settle 子系统报错时读 `credit_config.gate_fail_mode`：`open` ⇒ 放行 + 埋点；`safe` ⇒ 拦截（发 `credits_insufficient`）。默认 `open`（收钱前）。
- 结构化日志（structlog）计数：`credit.gate_failed_open` / `credit.settle_failed` / `credit.hold_orphaned` / `credit.leak_detected`（对账漂移）。便于上线前观察泄漏面。

## 9. 错误处理姿态

失败一律**朝"保护余额"而非"放泄漏"**倾斜：

- gate 失败 → 按 `gate_fail_mode`（默认放行，无 hold）。
- settle DB 失败 → 保留 hold（占用余额）等 sweep 重放，不静默丢。
- 孤儿 hold → sweep 重建或释放，绝不永久占用。
- 积分子系统整体异常仍不得砸坏游玩 / 生成主流程（Phase 1 原则延续）。

## 10. 前端（最小）

- 用户流水维持现有 `CreditBalanceChip` 抽屉 + `/api/credits/transactions`；**无需新页面**。
- 新增展示：delta=0 的「失败·未扣费」行（i18n 文案 `kind.debit_world_gen_failed` 等；零额行视觉弱化，delta 显示"—"或"未扣费"）。
- 持仓 / 预留对用户不可见（不进台账，自然不出现在流水）。
- `cost_cents` 继续不返回给用户端。

## 11. 配置

| 配置 | 默认 | 位置 |
|---|---|---|
| `gate_fail_mode` | `open` | `credit_config`（admin 可编辑） |
| `cached_input_price_cents_per_million_tokens` | null（按需填） | `provider_models`（admin 可编辑） |
| `CREDIT_HOLD_TTL_SECONDS` | 1800 | 代码常量 |
| `CREDIT_SETTLE_MAX_ATTEMPTS` | 5 | 代码常量 |
| sweep 周期 | ~300s | 代码常量 |

## 12. 迁移

- 加 `credit_wallets.held_units`（default 0，存量无需 backfill）。
- 建 `credit_holds`。
- 加 `provider_models.cached_input_price_cents_per_million_tokens`（null）。
- 加 `credit_config.gate_fail_mode`（default 'open'）。

## 13. 测试（轻量，覆盖核心路径）

- 预留原子性：并发 reserve 不超订；`balance − held < estimate` 时第二个被拦。
- settle：释放预留 + 按实扣，事后 **I1 / I2 成立**。
- 完全失败免费（delivered=False）：不扣、释放预留、写 delta=0 行。
- 部分交付（delivered=True, actual>0）：按真实消耗扣。
- settle DB 失败 → 记 `settle_failed` + 缓存 usage_json；sweep 重放成功结算。
- 孤儿 hold（模拟崩溃：held 超 TTL）→ sweep 从 `token_usage` 重建或释放，`held_units` 归零。
- 对账：注入漂移后 `reconcile` 能检测并 `repair` 校正。
- cache-aware：命中部分按 cached_price 计；`cached_input_price` 为 null 时回退全价（无行为变化）。
- fail-mode：子系统异常时 `safe` 拦截、`open` 放行 + 埋点。

## 14. 已定决策（2026-05-29 brainstorming）

- 范围 = **纯健壮性硬化**，不含变现。
- 并发方案 = **`held_units` 持仓预留（L3）**（而非 provisional-debit / per-user 锁）—— 保持 I1 干净、流水无噪音。
- 失败退款 = **完全失败（0 交付）免费，部分交付按实扣**。
- 用户流水 = **按动作粒度**（不逐回合）；持仓不写台账；完全失败写 delta=0「未扣费」信息行；`cost_cents` 仅 admin。
- 周期 sweep **纳入本期**（轻量 asyncio，不引新框架）。
- `gate_fail_mode` 默认 `open`，做成 admin 开关，收钱前不切 `safe`。
