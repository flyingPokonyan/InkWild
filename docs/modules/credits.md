# 积分系统（Credits）模块技术说明

> 状态截至 2026-05-29。覆盖 Phase 1（计量 + L2 拦截 + admin）+ Phase 2（L3 持仓预留 + 可靠结算 + 对账 + cache-aware + 失败退款）落地后的形态。设计依据：[`../plans/2026-05-29-credits-phase1-design.md`](../plans/2026-05-29-credits-phase1-design.md) + [`../plans/2026-05-29-credits-phase2-hardening-design.md`](../plans/2026-05-29-credits-phase2-hardening-design.md)。

积分系统是**架在已有成本轨道（`token_usage` / `usage_recorder`）之上的"用户可见 + 可拦截"镜像**。它在两个动作边界（游玩回合、生成任务）做 L3 持仓预留 + 真实成本结算，把"能不能开始这个动作"和"这个动作实际花了多少"两件事落到钱包与台账上。

边界划分：
- 它**不做**逐 LLM 调用的成本分析——那是 `cost-rate-moderation.md` 的 cost guardrail（`token_usage` 表 + `cost_guardrail.py`），两者各自独立记录、互不依赖。
- 它**不做**充值 / 签到 / 订阅等"赚取"侧（Phase 1/2 范围外，见 §8）。
- 紧密耦合上下游：`api/game.py::_stream_with_credits`（游玩边界）、`services/generation_task_service.py`（生成边界）、`llm/router.py::_accumulate_usage` + `services/metered_image_generator.py`（用量累加器喂数点）、`services/pricing_lookup.py`（每模型单价）。

## 1. 能力矩阵

### A. 计量与计费（"真实成本 → 积分"）

| 能力 | 状态 | 实现 |
|---|---|---|
| cost-pegged：扣费 = 真实成本 × 倍率 | ✅ | `credit_pricing.cost_fen_to_units`，倍率 `CreditConfig.billing_multiplier_milli`（1000=平进平出） |
| 分数级精度（sub-fen 不取整成 0） | ✅ | `credit_pricing.usage_to_cost_fen` 返 float，结算才 round |
| 内部定点单位（1 积分 = 10000 units） | ✅ | `models/credit.py::CREDIT_UNIT_SCALE` |
| cache-aware：命中按 cached 单价计 | ✅ | `usage_to_cost_fen(cache_hit_tokens/cache_miss_tokens)` + `ProviderModel.cached_input_price_cents_per_million_tokens` |
| cached 单价为 null → 回退全价（行为不变） | ✅ | `usage_to_cost_fen` 内 `cached_raw is not None` 判定 |
| provider 未上报 cache 拆分 → 全算 miss | ✅ | `usage_to_cost_fen` 内 `hit==0 and miss==0` 分支 |
| 每模型单价从 `provider_models` 查 | ✅ | `services/pricing_lookup.get_pricing_for` |
| 单价未填 → cost 为 0 → 不扣 | 🟡 | by-design fallback；依赖 admin 在模型后台填真价 |
| 配图计费（按张） | ✅ | `usage_to_cost_fen(image_count)`，`metered_image_generator` 喂 `image_count=1` |
| 分析口径（cost_guardrail / cost_cents）也 cache-aware | 🟡 | 计费已 cache-aware，分析口径仍按 miss 计；两套数未对齐（§8 P2） |

### B. 钱包、台账与不变式（"账本真相"）

| 能力 | 状态 | 实现 |
|---|---|---|
| 每用户一钱包（缓存余额） | ✅ | `CreditWallet`（unique `user_id`） |
| append-only 台账（唯一真相） | ✅ | `CreditLedger`，每条存 `balance_after_units` 快照 |
| 扣减同时存真实成本 `cost_cents` | ✅ | `CreditLedger.cost_cents`（毛利可随时算） |
| 不变式 I1：`balance == Σ ledger.delta` | ✅ | 仅 settle/grant 改 balance 且同事务写台账；`reconcile` 校验 |
| 不变式 I2：`held == Σ 活跃 holds.estimate` | ✅ | reserve/settle 同步增减；`reconcile` 校验 |
| 余额允许小幅为负（单动作超支） | ✅ | `balance_units` 有符号 BigInteger，下个动作被 gate 挡 |
| units ↔ 积分换算 | ✅ | `credit_pricing.units_to_credits / credits_to_units` |
| 对账 + 修复入口 | ✅ | `credit_service.reconcile(user_id, repair)` |
| 按动作粒度一条流水（不逐回合） | ✅ | settle 每动作写一条 debit；逐回合明细未做（§8） |

### C. 拦截与持仓（L3 gate，"开始前先占额"）

| 能力 | 状态 | 实现 |
|---|---|---|
| 原子预留：`available = balance − held` 一次 UPDATE 判定 | ✅ | `credit_service.reserve`（`WHERE balance−held>=estimate ... RETURNING`） |
| 关闭跨动作并发超支泄漏 | ✅ | held 在 reserve 时即增，第二个并发动作被挡 |
| 余额不足 → `InsufficientCredits` → SSE `credits_insufficient` | ✅ | `reserve` raise；`api/game.py` / `generation_task_service` 捕获 |
| 各动作预估额可配 | ✅ | `CreditConfig.estimate_game/world/script_units` |
| 单动作超支上限 = 单动作量（不累积） | ✅ | 预留封顶后真实成本可略超，settle 后 held 释放 |
| fail-mode 开关（open/safe） | ✅ | `CreditConfig.gate_fail_mode`；`api/game.py::_gate_blocks_on_error` |
| 子系统异常默认 fail-open（不砸游玩） | ✅ | reserve 异常 → 读 fail_mode，默认放行 + 埋点 |
| 同 session 串行（不靠积分） | ✅ | 由 `SessionLock` 保证（见 state-and-persistence.md） |

### D. 可靠结算与恢复（"算力花了就别漏扣"）

| 能力 | 状态 | 实现 |
|---|---|---|
| holds 表兼作结算 outbox | ✅ | `CreditHold`（status held/settled/settle_failed） |
| 真实用量累加器（独立于 best-effort sink） | ✅ | `llm/usage_context.UsageAccumulator` + `router._accumulate_usage` 同步喂 |
| settle 释放预留 + 按实扣（一事务） | ✅ | `credit_service._settle_core` |
| settle DB 失败 → 存 `usage_json` 转 `settle_failed` | ✅ | `settle_hold` except 分支 |
| sweep 重放 `settle_failed` | ✅ | `sweep_holds`（周期 + admin 触发） |
| 重放超 `CREDIT_SETTLE_MAX_ATTEMPTS` → 释放保底 | ✅ | `sweep_holds` gave_up 分支（防 held 永久泄漏） |
| 孤儿 hold（崩溃）超 TTL → 从 token_usage 重建扣费 | ✅ | `_reconstruct_entries_from_usage` + `sweep_holds` |
| 重建无果 → forgive 释放 | ✅ | `sweep_holds` orphan_forgiven 分支 |
| 周期 sweep（轻量 asyncio，无新框架） | ✅ | `main.py::_credit_sweep_loop`（300s） |

### E. 发放与赚取（"积分从哪来"）

| 能力 | 状态 | 实现 |
|---|---|---|
| 注册初始发放（懒创建，幂等） | ✅ | `get_or_create_wallet`（首次访问发 `signup_grant`） |
| 注册端点处早触发钱包 | 🔵 | 当前无注册端点；上线做注册流时加（§8 P2） |
| 存量用户 backfill 发放 | ✅ | 迁移 `d4e5f6a7b8c9`（`backfill_grant`） |
| admin 手动增减（逃生阀，审计） | ✅ | `credit_service.grant` + `api/admin_credits.py::adjust` |
| 签到 / 连签 / 任务奖励 | ❌ | Phase 2+，未做（§8） |
| 充值 / 付费 / 订阅 | ❌ | Phase 2+，未做（§8） |
| 生成失败退款（完全失败免费） | ✅ | `settle_hold(delivered=False)` → 不扣 + delta=0 信息行 |

### F. 接入点（"在哪扣"）

| 能力 | 状态 | 实现 |
|---|---|---|
| 游玩回合边界 reserve + settle | ✅ | `api/game.py::_stream_with_credits`（start/action/retry） |
| 游玩 delivered 判定（出过 narrative 或正常完成） | ✅ | `_stream_with_credits` 内 `saw_content` / `errored` |
| 生成任务边界 reserve + settle | ✅ | `generation_task_service::_credit_reserve` / `_credit_settle` |
| 生成 delivered 判定（task `status=='succeeded'`） | ✅ | `_credit_settle` 读 `GenerationTask.status` |
| 配图成本含在生成任务内结算 | ✅ | `metered_image_generator` 累加进同一 accumulator |
| 独立配图入口单独接 | 🔵 | Phase 1 假设无独立入口；有了再接 |
| 用量累加跨 await / create_task 传播 | ✅ | contextvar（`usage_accumulator()`） |

### G. 用户端 / Admin / 可观测

| 能力 | 状态 | 实现 |
|---|---|---|
| 用户余额 API | ✅ | `GET /api/credits/balance` |
| 用户流水 API（游标分页） | ✅ | `GET /api/credits/transactions` |
| 余额 chip + 流水抽屉 | ✅ | `frontend/components/CreditBalanceChip.tsx` |
| 完全失败行渲染为"未扣费" | ✅ | `CreditBalanceChip` delta=0 分支 + i18n `credits.notCharged` |
| `cost_cents` 不暴露给用户 | ✅ | `api/credits.py` transactions 不返 cost_cents（admin 才返） |
| admin 查钱包 + 台账 | ✅ | `GET /api/admin/users/{id}/credits` |
| admin 改经济参数（即时生效） | ✅ | `GET/PUT /api/admin/credits/config`（含 `gate_fail_mode`） |
| admin 对账 dry-run + repair | ✅ | `GET/POST /api/admin/credits/reconcile`（后端就绪） |
| admin-frontend 接 gate_fail_mode / reconcile UI | 🔵 | 后端就绪，前端 `/credits` 页未接（§8 P2） |
| 漏计 / 结算失败 / 孤儿 / 漂移埋点 | ✅ | structlog `credit.gate_failed` / `settle_failed` / `hold_orphaned` / `leak_detected` |

## 2. 关键能力实现要点

### 2.1 cost-pegged + cache-aware 计费（对应 A）

**问题**：积分要贴真实成本且不能被定价取整吃掉（便宜调用算 0 积分），prompt 缓存命中时还不能多扣用户。

**解决**：纯函数 `usage_to_cost_fen` 以**分数级 fen** 计成本；输入 token 拆 hit/miss，命中按 `cached_input_price` 计、未配置则回退全价（行为不变），provider 没报拆分就全算 miss。`cost_fen_to_units` 再套倍率 + scale 取整成 units。

**实现**：
- 计费核心：`services/credit_pricing.py::usage_to_cost_fen` / `cost_fen_to_units`
- 用量来源：`UsageAccumulator.entries`（每条带 `cache_hit_tokens` / `cache_miss_tokens`），由 `router._accumulate_usage` 在每个 usage 事件**同步**喂入
- 单价：`pricing_lookup.get_pricing_for` 返 4 个价（input/output/image/cached_input）

**取舍**：cache 字段事件本来就有（`deepseek.py` / `openai_compatible.py`），只是 Phase 1 没用于计费。分析口径（`cost_guardrail` / `token_usage.cost_cents`）仍按 miss 计，**两套成本数尚未对齐**（§8 P2）。

### 2.2 L3 持仓预留关闭并发泄漏（对应 C，两条不变式）

**问题**：Phase 1 的 L2 只读 `balance >= estimate`，余额刚够一次预估额的用户同时开多个动作（多标签页 / 同时游玩+生成）时每个 gate 都过 → 超支远超单动作量。`SessionLock` 只串行单 session，挡不住跨 session/跨任务。

**解决**：引入 `held_units` + `credit_holds`。reserve 用一条原子 `UPDATE ... WHERE balance−held>=estimate ... RETURNING` 同时判定 + 占额，0 行即拦截。`balance` 只在 settle 动，台账保持每动作一条净额。

**实现**：
- `credit_service.reserve`（原子预留 + 写 hold 行）
- `_settle_core`（释放 `held -= estimate` + 按实扣 `balance -= actual` + 写台账，一事务）
- 不变式：I1 `balance == Σ ledger.delta`、I2 `held == Σ 活跃 holds.estimate`，均由 `reconcile` 校验

**取舍**：选 held_units 而非 provisional-debit（预扣再退差），因为前者保持台账无"预留/退回"噪音、I1 始终干净，对账更可靠；代价是多一列 + 预留/释放生命周期。

### 2.3 可靠结算：holds 作为 outbox + sweep 恢复（对应 D）

**问题**：settle 在 SSE 流 `finally` 跑，可能遇到 DB 抖动、进程崩溃、客户端中途断连 → 真实用量不入账，静默漏扣。

**解决**：`credit_holds` 兼作结算 outbox。real-time settle 失败 → 存 `usage_json` 转 `settle_failed`，**保留预留**（朝保护余额倾斜）。周期 sweep + admin 触发负责恢复：
- `settle_failed` → 重放 `usage_json`；超 `CREDIT_SETTLE_MAX_ATTEMPTS`（5）次则释放保底，防 held 永久泄漏
- `held` 超 `CREDIT_HOLD_TTL_SECONDS`（1800s）= 孤儿（崩溃）→ 从 `token_usage` 按 ref_id 重建真实成本扣除；查不到则 forgive 释放

**实现**：
- `credit_service.settle_hold`（失败转 settle_failed）/ `sweep_holds`（两类恢复）/ `_reconstruct_entries_from_usage`
- 周期任务：`main.py::_credit_sweep_loop`（lifespan 内，复用 fire-and-forget 模式，不引新框架）

**取舍**：失败一律朝"保护余额"而非"放泄漏"倾斜——settle 失败宁可占着 held 等 sweep，也不直接放过。孤儿"宁可补扣也不白送"（先试 token_usage 重建）。

### 2.4 完全失败免费 + delivered 判定（对应 E/F）

**问题**：生成中途失败（已耗 token 但 0 交付）仍扣费体验差。

**解决**：settle 带 `delivered` 标志。`delivered=False`（完全失败）→ 释放预留、`charged=0`、写一条 **delta=0「未扣费」信息行**（用户能看到"为什么没扣"）；部分交付 → 按真实消耗扣。
- 生成：`delivered = (GenerationTask.status == 'succeeded')`
- 游玩：`delivered = 出过 narrative 事件 or 正常完成`

**实现**：`_settle_core` 的 `not delivered` 分支写 `kind=f"{debit_kind}_failed"` 零额行；判定见 `_stream_with_credits`（saw_content）与 `_credit_settle`（task status）。

### 2.5 对账（对应 B）

**问题**：余额是缓存，可能因 bug / 人工改库 / sweep 异常与台账漂移，且无从发现。

**解决**：`reconcile(user_id, repair=False)` 核对 I1（balance vs Σledger）、I2（held vs Σ活跃holds），报告 drift；`repair=True` 按权威源（台账 / hold 行）校正 wallet。`user_id=None` 全量。漂移即埋点 `credit.leak_detected`。

**实现**：`credit_service.reconcile` + `api/admin_credits.py::reconcile_credits / repair_credits`（POST 审计）。

## 3. 关键代码位置速查

| 文件 | 作用 |
|---|---|
| `backend/models/credit.py` | `CreditWallet` / `CreditLedger` / `CreditHold` / `CreditConfig` + `CREDIT_UNIT_SCALE` |
| `backend/services/credit_pricing.py` | 纯函数：用量 → fen（cache-aware）→ units 换算 |
| `backend/services/credit_service.py` | reserve / settle_hold / sweep_holds / reconcile / grant / get_or_create_wallet + 常量 |
| `backend/services/pricing_lookup.py` | 每模型单价查询（4 价） |
| `backend/llm/usage_context.py` | `UsageAccumulator` + per-action contextvar |
| `backend/llm/router.py::_accumulate_usage` | 在 usage 事件同步喂累加器（含 cache 拆分） |
| `backend/services/metered_image_generator.py` | 配图 `image_count` 喂累加器 |
| `backend/api/credits.py` | 用户端 balance / transactions |
| `backend/api/admin_credits.py` | admin 钱包 / 调整 / config / reconcile |
| `backend/api/game.py::_stream_with_credits` | 游玩边界 reserve + settle + delivered |
| `backend/services/generation_task_service.py` | 生成边界 `_credit_reserve` / `_credit_settle` |
| `backend/main.py::_credit_sweep_loop` | 周期 sweep 任务 |
| `frontend/components/CreditBalanceChip.tsx` + `frontend/lib/credits.ts` | 余额 chip + 流水抽屉 |

## 4. 配置项汇总

经济参数全部 **DB 落地（`credit_config` 单例 id=1）、admin 可编辑、即时生效**（无需重启）：

| 配置（CreditConfig 列） | 默认 | 含义 |
|---|---|---|
| `billing_multiplier_milli` | `1000` | 计费倍率 ×1000（1000 = 平进平出；毛利 = 1−1/倍率） |
| `signup_grant_units` | `500 * 10000` | 注册/backfill 发放额（500 积分） |
| `estimate_game_units` | `25 * 10000` | 游玩回合预留额（L3 闸门） |
| `estimate_world_units` | `70 * 10000` | 世界生成预留额 |
| `estimate_script_units` | `200 * 10000` | 剧本生成预留额 |
| `gate_fail_mode` | `open` | 子系统异常姿态：`open`=放行+埋点 / `safe`=拦截 |

| 代码常量（`credit_service.py`） | 值 | 含义 |
|---|---|---|
| `CREDIT_UNIT_SCALE` | `10000` | 1 积分 = 1 万 units（`models/credit.py`） |
| `CREDIT_HOLD_TTL_SECONDS` | `1800` | held 超此时长无 settle 即孤儿 |
| `CREDIT_SETTLE_MAX_ATTEMPTS` | `5` | settle 重放上限，超则保底释放 |
| `_CREDIT_SWEEP_INTERVAL_SECONDS` | `300` | sweep 周期（`main.py`） |

`provider_models` 单价列：`input_price_cents_per_million_tokens` / `output_price_cents_per_million_tokens` / `cached_input_price_cents_per_million_tokens` / `image_price_cents_per_image`（分/百万 token 或分/张；admin 后台填）。

## 5. 数据库 schema

```
credit_wallets (
  id, user_id UNIQUE,
  balance_units,            -- 缓存余额（可小幅为负）
  held_units,               -- L3 预留总额；available = balance - held
  lifetime_granted_units, lifetime_spent_units,
  created_at, updated_at
)

credit_ledger (              -- append-only，唯一真相
  id, user_id,
  delta_units,              -- + 发放 / − 扣减 / 0 失败信息行
  balance_after_units,      -- 应用本条后余额快照
  kind,                     -- signup_grant/backfill_grant/admin_adjust/debit_game/
                            --   debit_world_gen/debit_script_gen/debit_*_failed
  category, ref_type, ref_id,
  cost_cents,               -- 该笔真实成本（仅 admin 可见）
  note, actor_user_id, created_at
)
INDEX (user_id, created_at)

credit_holds (               -- 持仓 + 结算 outbox
  id, user_id,
  action,                   -- game/world/script
  ref_type, ref_id,
  estimate_units,           -- 预留额
  charged_units,            -- settle 后实扣
  usage_json,               -- settle 失败时缓存的用量快照（重放用）
  status,                   -- held/settled/settle_failed
  attempts, last_error,
  created_at, settled_at
)
INDEX (status, created_at), (user_id, status)

credit_config (id=1 单例)     -- 见 §4
```

迁移：`d4e5f6a7b8c9`（Phase 1：三表 + backfill）、`e7f8a9b0c1d2`（Phase 2：held_units + credit_holds + cached_input_price + gate_fail_mode）。完整 schema 见 `docs/data/schema.md`。

## 6. 测试覆盖

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/test_credit_pricing.py` | 各维度成本 + sub-fen 精度 + 倍率/换算 + cache-aware（命中/仅命中/null 回退/无拆分） |
| `tests/test_credit_service.py` | 发放幂等 + reserve 拦截 + settle 按实扣/释放 + 完全失败免费 + 无定价免费 + sweep 重放/孤儿（补扣 + forgive）+ reconcile 检测/修复；每例断言 I1/I2 |
| `tests/test_models_metadata.py` | `credit_holds` 等全表在 SQLite create |

> 注：并发原子性在 SQLite 下只能顺序验证（reserve 连续耗尽可用额 → 第三个被拦），真实并发争用未压测（§8 P3）。

## 7. 已知短板与未来扩展

### P1（上线前必须确认）

- **`provider_models` 单价务必填全**：未填则 `usage_to_cost_fen` 返 0、永远不扣。当前活跃 slot 已填（含 `grok-4.20-fast` 144/360），新增模型/换价时必须同步。
- **倍率上线前调高**：`billing_multiplier_milli=1000` 是平进平出（毛利 0），开卖前在 admin 后台调高。

### P2

- **注册端点处早触发钱包**：当前钱包懒创建（首次读余额/gate 时发放），尚无注册端点；做注册流时加一行 best-effort `get_or_create_wallet`，使"注册即有钱包、发放时间戳≈注册时刻"。
- **分析口径 cache-aware 对齐**：计费已 cache-aware，但 `cost_guardrail` / `token_usage.cost_cents`（分析口径）仍按 miss 计；两套成本数应抽共享核心对齐，避免毛利与分析打架。
- **admin-frontend UI**：后端 `gate_fail_mode` 开关 + reconcile 已就绪，admin `/credits` 页未接对应控件。
- **赚取侧（签到 / 充值 / 订阅）**：经济引擎已扎实，但"积分从哪充值/赚"完全未做，是真正变现的下一阶段。
- **`gate_fail_mode` 默认切 `safe` 的时机**：收钱前保持 `open`（基础设施抖动不砸游玩）；真正涉及金钱后应切 `safe`。

### P3

- **并发争用压测**：reserve 原子性靠 SQL `WHERE`，SQLite 单元测试只能顺序验证；Postgres 真实并发应补一组压测。
- **逐回合 / 逐调用流水明细**：用户端维持按动作粒度；逐回合需额外打 turn 标记，按需再做。
- **失败退款策略细化**：当前"完全失败免费、部分按实扣"；未来可按交付质量分级退款。
- **孤儿重建依赖 best-effort `token_usage`**：崩溃孤儿从 `token_usage` 重建，而该 sink 本身 best-effort，丢了就 forgive；可评估更强的 in-flight 持久化（成本高，当前不值）。
