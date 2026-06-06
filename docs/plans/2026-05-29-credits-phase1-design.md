# 积分系统 Phase 1 设计（Credits — 计量 + 拦截）

> 创建：2026-05-29 · 状态：设计待评审 · 范围：Phase 1（计量 + 硬拦截 + admin 管理）
> 作者协作：brainstorming 产出，落地见后续 implementation plan。
> 与代码冲突时以代码为准。

## 1. 背景与目标

InkWild 尚未上线，准备引入积分（credits）机制，为后续变现（充值/订阅）打底。
**核心原则：经济系统要在规模化之前建好** —— 用户习惯一旦锚定"无限免费"，将来上闸门代价极高。

成本轨道已成熟：`TokenUsage` 表逐调用记录 `cost_cents`（admin 可配每模型单价），
`usage_recorder` 是统一计量 sink，`UsageContext`（含 `user_id`）随 `await`/`create_task` 传播。
**积分 = 在已有成本轨道上加一层"用户可见 + 可拦截"的镜像。**

### 关键产品决策（已确认）

| 决策 | 选择 | 理由 |
|---|---|---|
| 积分单位 | **cost-pegged**：1 积分 = 固定一小段真实成本 | 最贴成本、自平衡；成本随 admin 定价自动跟随 |
| 拦截 | **开（gate ON）**，L2 严谨度 | 控成本、防滥用；上线前用 admin 兜底 |
| 拦截实现 | 入口**预检（余额 ≥ 动作预估额）** + 动作后**按真实结算** | 把"拦"的决定点前移到动作开始前；后扣保证真实 |
| 接入点 | **两个动作边界**：游玩回合、生成任务（配图含在生成任务内） | 远少于"每个调用点"；可靠结算 |
| 赚取 | Phase 1 仅"注册初始额度 + admin 手动发放"；签到/充值后期 | 先把骨架搭起来 |

## 2. Phase 1 范围

### IN ✅

- 钱包 + 单张 append-only 台账；注册发放 + 存量 backfill。
- 每个耗 token 动作按真实成本扣积分（细精度，cost-pegged）。
- L2 硬拦截：余额不足以覆盖该动作**预估额**时，动作开始前拒绝。
- 用户端：余额展示 + 流水（按动作分组、按 play/creation 归类；配图成本含在生成任务的 creation 扣减内）+ "积分不足"态。
- Admin：查用户余额/流水 + 手动增减积分（审计）+ 编辑经济参数（倍率/初始额/预估额/模型价格），作为逃生阀与运营手段。

### OUT 🔵（Phase 2+）

- 签到 / 连签 / 任务奖励等自助赚取。
- 充值 / 付费 / 订阅。
- L3 持仓预留（彻底消除跨局并发泄漏）。
- 生成失败退款策略。
- 经济参数（比例/初始额/预估额）后台可编辑（Phase 1 走 config）。
- 逐回合级流水明细（Phase 1 按"一局/一次生成"为一条；逐回合需额外打 turn 标记）。

## 3. 数据模型

新增两张表；`TokenUsage` **不改动**（仍是逐调用成本分析）。
`credit_ledger` 是**积分变动的唯一真相**（append-only）；`credit_wallets.balance_units` 是**缓存余额**，可由台账重算对账。

### 3.1 `credit_wallets`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid pk | |
| `user_id` | uuid, **unique**, FK users.id, index | 每用户一行 |
| `balance_units` | BigInteger, default 0 | 当前余额（内部单位）；允许小幅为负（见 §6 单动作超支） |
| `lifetime_granted_units` | BigInteger, default 0 | 累计发放 |
| `lifetime_spent_units` | BigInteger, default 0 | 累计消耗（绝对值） |
| `created_at` / `updated_at` | datetime | |

> 不含 `held_units`（L2 不需要持仓）。升级到 L3 时再加该列 + 预留/释放逻辑。

### 3.2 `credit_ledger`（append-only）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid pk | |
| `user_id` | uuid, FK, index | |
| `delta_units` | BigInteger, signed | + 发放 / − 扣减 |
| `balance_after_units` | BigInteger | 应用本条后的余额快照（审计/展示） |
| `kind` | String(32) | `signup_grant`/`backfill_grant`/`admin_adjust`/`debit_game`/`debit_world_gen`/`debit_script_gen`/`debit_image_gen`；Phase2 扩 `checkin`/`purchase`/`refund` |
| `category` | String(16), nullable | `play`/`creation`/`grant`/`adjust`（`image` 预留给独立配图入口；Phase 1 配图成本归入 creation）；由 kind 派生、冗余存便于查询 |
| `ref_type` | String(16), nullable | `session` / `task` |
| `ref_id` | uuid/str, nullable | session_id 或 task_id |
| `cost_cents` | Integer, nullable | 该笔扣减对应的真实成本（分），对账/透明用 |
| `note` | Text, nullable | admin 调整原因等 |
| `actor_user_id` | uuid, nullable | 做调整的 admin（手动发放时） |
| `created_at` | datetime, index | |

索引：`(user_id, created_at desc)`（流水查询）。

### 3.3 单位、换算与计费倍率

- 内部 `*_units` 整数，**1 积分 = `CREDIT_UNIT_SCALE`（默认 10,000）units**（4 位小数，杜绝浮点漂移）。
- **积分价值锚（售价，未来充值用）**：1 积分 = ¥0.01（即 ¥10 = 1000 积分）。Phase 1 不卖，仅作锚定，不入代码。
- **计费倍率 `BILLING_MULTIPLIER`（核心经济变量）**：一个动作扣的积分 = 真实成本 × 倍率。
  - `credit_units = round(真实成本(分, 细精度) × BILLING_MULTIPLIER × CREDIT_UNIT_SCALE)`
  - **毛利 = 1 − 1/倍率**。Phase 1 初始 **= 1**（平进平出，反正还不卖）；上线开卖前调高（admin 可改）。
- 台账每条扣减**同时存** `cost_cents`（真实成本）与 `delta_units`（实扣积分）→ 真实毛利随时可见。
- ⚠️ 真实成本用 `tokens × 每模型单价` **细算**（分数级），不用取整的 `cost_cents`（否则便宜调用变 0）。实现：抽 `estimate_usage_cost(...) -> float` 核心；现有 `estimate_usage_cost_cents` 在其上取整（行为不变）。复用 `pricing_lookup`，DRY。
- Phase 1 输入按单一（cache-miss）价计费（与现有成本计算一致，最简）；cache-aware 计费（用 `cache_hit/miss_tokens` 列）是后续优化。

## 4. 机制与数据流

### 4.1 钱包创建 + 初始发放

- **新用户**：注册（`auth_service` 建 user）时建钱包 + 发 `CREDIT_SIGNUP_GRANT_UNITS`（`kind=signup_grant`），幂等（每用户仅一次）。
- **存量用户**：Alembic backfill 建钱包 + 等额发放（`kind=backfill_grant`）。
- **兜底**：gate / 读余额时 `get_or_create_wallet`，防遗漏。

### 4.2 动作边界：预检（gate）+ 结算（settle）

两个边界，逻辑同构：

```
1. 入口预检（动作开始前）：
   estimate = CREDIT_ESTIMATE_<action>_UNITS
   if wallet.balance_units < estimate:  # L2：要求够覆盖预估额
       raise InsufficientCredits        # → SSE 错误，动作不执行
2. 执行动作（LLM/图像调用照常发生；TokenUsage sink 照常记录）
   过程中把真实用量累加到「本动作用量累加器」（见 §4.3）
3. 结算（动作结束，finally —— 出错也结算已花部分）：
   actual_units = usage_to_credit_units(累加用量, pricing)
   if actual_units > 0:
       原子扣减 wallet.balance_units，写 credit_ledger 扣减行
```

- **游玩回合**：`game_service` 的 action / retry 入口（已被 `SessionLock` 包裹、已设 `usage_context`）。预检在 orchestrator 启动前；结算在回合结束 finally。`kind=debit_game`，`category=play`，`ref=session`。
- **生成任务**：`generation_task_service` 任务起止。`kind=debit_world_gen`/`debit_script_gen`，`ref=task`。配图（`image_gen`）成本天然累加在该任务内，结算时一并计入；如有独立配图入口再单独接（Phase 1 假设无）。

### 4.3 本动作真实用量累加器

结算必须拿到动作的**真实 token/图像用量**，且**不能依赖 best-effort sink**（sink 可能丢）。

- 方案：在动作边界 push 一个**可变累加器**到 contextvar（随 `usage_context` 同生命周期）；
  在 usage 事件产生处（router/sink 观测点）**同步**累加该动作用量（与 best-effort 的 DB 写解耦）；结算时读取。
- 实现细节（router 是否已向边界透出 usage 事件 / 用 contextvar 累加器）在 implementation plan 阶段定。

### 4.4 Admin 手动增减（逃生阀 + 运营）

- `credit_service.grant(user_id, delta_units, kind='admin_adjust', note, actor_user_id)`：原子改余额 + 写台账（`delta` 可正可负）。
- 走 `get_current_admin_user` + `record_admin_action`（审计）。

## 5. 接口

### 5.1 用户端（新 `api/credits.py`，`get_current_user`）

- `GET /api/credits/balance` → `{ balance, lifetime_granted, lifetime_spent }`（units→积分换算后返回）。
- `GET /api/credits/transactions?cursor=...` → 流水：发放行 + 按动作粒度的扣减行，倒序分页，带 `category`。

### 5.2 Admin（`api/admin_users.py` 扩展，`get_current_admin_user` + 审计）

- `GET /api/admin/users/{user_id}/credits` → 钱包 + 近期台账。
- `POST /api/admin/users/{user_id}/credits/adjust` → `{ delta_credits, note }` → `admin_adjust`，审计。
- 用户列表带余额（扩展现有 admin_users 列表）。
- `GET/PUT /api/admin/credits/config` → 读取/更新经济参数（倍率、初始额、各预估额、模型价格），审计。

### 5.3 SSE 错误

- 新错误码 `credits_insufficient`（payload 带 `version: 1`，遵循 sse-protocol）。
- 游玩 action / 生成任务在预检失败时发该错误；前端据此显示"积分不足"态。

## 6. 并发与正确性

- **原子扣减**：`UPDATE credit_wallets SET balance_units = balance_units - :x ...`（DB 级，非读-改-写），避免并发丢更新；`balance_after` 用 RETURNING 或同事务回读。
- **单动作超支（可接受）**：用户余额够预估额时开了动作、但真实成本超过余额 → 余额小幅为负，**下一个动作被拦**。超支上限 = 单个动作量，不累积。
- **同局并发**：已被 `SessionLock` 串行化，主泄漏路径不存在。跨局/跨任务并发的残留泄漏在 Phase 1 接受（L3 持仓可彻底消除，后期）。
- **对账**：`wallet.balance_units == Σ credit_ledger.delta_units`（台账为真相，钱包为缓存）；提供重算/校验入口。

## 7. 错误处理与边界

- **预检失败** → `credits_insufficient` SSE 错误，动作**不执行**。
- **结算在 finally**：动作中途出错也结算已消耗部分（算力已花）。真实用量为 0（调用前就失败）则不扣。
- **生成失败**：Phase 1 **按实际消耗扣、不退款**（开放产品问题，Phase 2 可加失败退款）。
- **缺钱包**：gate / 读余额时 `get_or_create_wallet` 兜底。
- **积分子系统自身报错（如 DB 抖动）**：Phase 1 **fail-open**（放行动作 + 记日志），避免基础设施抖动直接砸坏游玩体验；Phase 2 收紧（涉及真实金钱时）。
- **best-effort sink 不变**：`TokenUsage` 仍独立记录用于成本分析；积分结算走独立可靠路径。

## 8. 前端

### 8.1 主站（最小，Phase 1）

- `ProductNav` 余额 **chip**（桌面）；移动端在 header/合适处展示。
- 流水：vaul **抽屉** 或轻量 `/credits` 页，列近期流水（按局/按生成分组 + 归类）。Round 2 个人中心再收编。
- **"积分不足"态**：play action + generate 收到 `credits_insufficient` 时清晰提示（Phase 1 无充值 CTA，可显示"请联系管理员"占位）。
- 用 TanStack Query 取 balance/transactions；i18n（zh/en）。

### 8.2 admin-frontend

- 用户详情页加"积分"面板：余额 + 台账 + 增减表单（含原因）。
- "积分经济"设置页：编辑倍率 / 初始额 / 各预估额 / 模型价格，实时生效。

## 9. 配置与定价（实测数据推导，2026-05-29）

经济参数 **admin 后台可编辑**（DB 落地，改动即时生效、无需重启）：

| 配置 | 值 | 说明 |
|---|---|---|
| `CREDIT_UNIT_SCALE` | 10000 | 1 积分 = 1 万 units |
| `BILLING_MULTIPLIER` | **1** | 计费倍率 = 目标毛利（1−1/倍率）；初始平进平出，上线前调 |
| `CREDIT_SIGNUP_GRANT` | **500 积分** | ≈¥5 算力 ≈ 50 回合（倍率=1） |
| 回合预估额（L2 闸门） | 25 积分 | 略高于最坏单回合，挡明显欠费 |
| 世界生成预估额 | 70 积分 | |
| 剧本生成预估额 | 200 积分 | |

实测成本基线（真实 token × 确认价；¥7.2/$；play 主力 V4 Pro 输出 $0.87/M；配图 20 分/张）：

| 动作 | 真实成本 | 倍率=1 扣 |
|---|---|---|
| 游玩 1 回合 | ~10–18 分（看缓存计费） | ~10–18 积分 |
| 生成 1 世界 | ~45 分 | ~45 积分 |
| 生成 1 剧本 | ~130 分（配图主导） | ~130 积分 |
| AI 配图/张 | 20 分 | 20 积分 |

`provider_models` 价格需填（分/百万 token；当前全空 → cost_cents 一直为 0）：

| 模型 | 输入(分/M) | 输出(分/M) | 配图(分/张) |
|---|---|---|---|
| deepseek-v4-pro | 313 | 626 | — |
| deepseek-v4-flash | 101 | 202 | — |
| 配图模型（待确认具体模型） | — | — | 20 |

> 数据稀疏（1 用户/25 局/22 次生成），属估算；上线后真实计量自动收敛 —— 这正是 Phase 1 计量的意义。V4 Pro 价 2026-05-31 后维持当前水平（已确认）。

## 10. 迁移

- Alembic：建 `credit_wallets`、`credit_ledger`。
- Backfill：为所有存量用户建钱包 + `backfill_grant`。

## 11. 测试（轻量，覆盖核心路径）

- 换算精度：sub-cent 成本不丢；units↔积分换算正确。
- 并发原子扣减不丢更新。
- 发放幂等：注册仅发一次。
- gate：`balance < estimate` 拦截且动作**不执行**；`>=` 放行。
- 结算：真实扣减；出错路径结算已消耗部分。
- 对账：`wallet.balance == Σ ledger.delta`。
- admin 增减：审计 + 余额/台账更新。
- API：balance / transactions 分组与归类。
- SSE `credits_insufficient` 形状（带 `version:1`）。
- fail-open：积分子系统异常时游玩不被砸坏。

## 12. 已定 / 残留确认

**已定（2026-05-29，实测数据）**：计费倍率 = 1（admin 可调）、初始额 500 积分、配图 20 分/张、各预估额见 §9、`provider_models` 价格见 §9；生成失败「按实际扣不退款」+ 积分系统报错「fail-open」（§7）已认可；经济参数做成 **admin 可编辑**。

**残留小确认**：配图具体模型（Seedream / gpt-image-2 / grok-imagine-image）—— 仅影响真实成本核对，计费已按 20 分/张固定。
