# Dashboard ↔ Backend API 契约

> 前端 dashboard mock 数据已定型（位于 `admin-frontend/lib/mock/experiment-mock.ts`），OpenClaw 在 Phase 1 实施后端时**必须按本契约实现** endpoint + payload shape。
>
> **TS 类型源头：`admin-frontend/lib/mock/experiment-mock.ts`**（导出的所有 type/interface 即为 wire shape）。
>
> 路由位置：`admin-frontend/app/experiments/page.tsx` + `[id]/page.tsx`（admin-frontend 服务端口 3001，不在 main `frontend/` 下）。

---

## 0. 落库现状（重要：哪些已有 / 哪些要新建）

**已有，无需 OpenClaw 重做**：
- `game_sessions` —— 每局会话元数据 + game_state（实验跑出来的就是真 session）
- `messages` —— 每轮对话（player / npc / narrator 内容）
- `case_board_history` —— 案件板增量操作
- `token_usage` —— **每笔 LLM 调用的 token + cost**（provider / model / agent role / cost_cents）。当前已是项目 cost guardrail 的数据源
- `generation_tasks` / `generation_task_events` —— 创作工坊批量生成的任务流

**OpenClaw 要新建**：
- `experiment_runs` —— 实验元数据 + 进度（按 (world, mode, archetype, model, seed) 组合 跟踪 pending/running/done/failed）
- `experiment_world_tier1_scores` —— Tier1 评分（含 reasoning + retry）
- `experiment_session_tier2_scores` —— Tier2 评分
- `experiment_turn_tags` —— 每轮 tag 标注
- `experiment_alerts` —— alert 流
- `experiment_session_reviews` —— 用户 review verdict + note

成本聚合：OpenClaw 写新表时**只存 session_id / world_id 关联**，cost 数据通过 `token_usage` JOIN 聚合得出，不冗余存。

---

## 1. 切换 mock → 真 API 的方式

前端**所有 component 都从 `admin-frontend/lib/data/use-experiment.ts` 导入数据**——这是唯一的数据访问点。Mock 数据本体在 `admin-frontend/lib/mock/experiment-mock.ts`，但 component 不要直接 import 它。

切换 mock → 真 API 只改一个文件：`admin-frontend/lib/data/use-experiment.ts`。

**步骤**：
1. OpenClaw 实施完后端 endpoint（见下面 §3）
2. 在 admin-frontend `.env` 设 `NEXT_PUBLIC_USE_MOCK_EXPERIMENT_DATA=false`（控制顶部 banner 显示）
3. 把 `use-experiment.ts` 里每个 hook 改成 TanStack Query 调真 endpoint：

```ts
// before:
export function useExperiment() {
  return mockSource().experiment;
}

// after:
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export function useExperiment(experimentId: string = "exp_2026_05_vps_eval") {
  const { data } = useQuery({
    queryKey: ["experiments", experimentId],
    queryFn: () => apiFetch<Experiment>(`/api/admin/experiments/${experimentId}`),
  });
  return data;
}
```

4. 加 loading / error state 处理（当前 mock 是同步返）
5. Component 调用方加 `if (!experiment) return <Skeleton />` 类似的 guard

Mock 数据**保留**作 dev fallback / Storybook 用 —— 当 OpenClaw 后端宕机时可以一行改回 mock。

---

## 2. 鉴权

所有 endpoint：
- 路径前缀：`/api/admin/experiments/`
- 鉴权：现有 admin user cookie（沿用 `get_current_admin_user` dependency）
- 写操作：调 `record_admin_action(...)` 落 `admin_audit_logs`

---

## 3. Endpoint 清单

| Method | Path | 用途 | Response shape |
|---|---|---|---|
| GET    | `/`                                          | 实验列表 | `Experiment[]` |
| GET    | `/{exp_id}`                                  | 实验元数据 + KPI | `Experiment` |
| GET    | `/{exp_id}/worlds`                           | 世界列表（query: `layer` / `status`） | `World[]` |
| GET    | `/{exp_id}/worlds/{world_id}`                | 单世界详情 | `World` |
| POST   | `/{exp_id}/worlds/{world_id}/actions/regen`  | 触发重 generate | `{ status: "queued", task_id: string }` |
| POST   | `/{exp_id}/worlds/{world_id}/actions/discard`| 永久淘汰 | `{ ok: true }` |
| POST   | `/{exp_id}/worlds/{world_id}/actions/feature`| 标记 featured 候选 | `{ ok: true }` |
| GET    | `/{exp_id}/sessions`                         | session 列表（query: `mode` / `archetype` / `end_reason` / `world_id`） | `Session[]`（不含 transcript） |
| GET    | `/{exp_id}/sessions/{session_id}`            | session 详情 + transcript（如有） | `Session`（带 transcript） |
| POST   | `/{exp_id}/sessions/{session_id}/review`     | 写 review verdict / note | body `{ verdict: "approve"\|"reject"\|"pending", note?: string }` → `{ ok: true }` |
| GET    | `/{exp_id}/tags/counts`                      | tag 频次聚合 | `{ [TagId]: number }` |
| GET    | `/{exp_id}/tags/{tag_id}/sessions`           | 命中某 tag 的 session 列表 | `Session[]` |
| GET    | `/{exp_id}/alerts`                           | 最近事件流（query: `limit`） | `Alert[]` |
| GET    | `/{exp_id}/review-pack`                      | 30 局 review 包 | `{ top: Session[], bottom: Session[], random: Session[] }` |
| GET    | `/{exp_id}/featured`                         | Featured 候选名单 | `{ script: World[], free: World[] }` |
| GET    | `/{exp_id}/export/featured.md`               | 导出 featured markdown | `text/markdown` |
| GET    | `/{exp_id}/cost/daily`                       | 日累计成本（用于 SpendBarChart） | `Array<{ date: string, cost_cents: number }>` |
| GET    | `/{exp_id}/cost/by-agent`                    | 全局按 agent 角色聚合 | `Array<{ agent: AgentRole, calls, tokens_in, tokens_out, cost_cents, share }>` |
| GET    | `/{exp_id}/cost/by-archetype`                | 按 player archetype 聚合 | `Array<{ archetype, sessions, turns, cost_cents }>` |
| GET    | `/{exp_id}/cost/by-model`                    | 按 player model 聚合 | `Array<{ model, sessions, cost_cents }>` |
| GET    | `/{exp_id}/cost/top-worlds?limit=5`          | 最贵 N 个世界 | `Array<{ world_id, generation_cents, gameplay_cents, total_cents }>` |
| GET    | `/{exp_id}/cost/top-sessions?limit=5`        | 最贵 N 个 session | `Array<{ session_id, archetype, model, turns, cost_cents }>` |

---

## 4. Payload shape

**完整 TS 类型在 `frontend/lib/admin/experiment-mock.ts`**。下面是关键约定：

### 4.1 Experiment

```ts
{
  id: string,
  name: string,
  status: "running" | "paused" | "done" | "error",
  started_at: string,            // "2026-05-08 14:22" (人类可读，不要 ISO；后端可以返 ISO 由前端格式化)
  last_heartbeat: string,        // "12 分钟前"
  operator: string,              // "OpenClaw on VPS"
  progress: { session_total_planned, session_done, session_running, session_pending, session_aborted, generation_done, tier1_done, tier1_pass, tier1_pass_after_retry },
  cost: { spent_usd, budget_usd, avg_session_usd, hard_kills_24h },
  eta_days: number,
}
```

### 4.2 World

关键字段：
- `id / name / layer ("L1"|"L2"|"L3"|"L4") / source / cover_color / cover_emoji`
- `genre / era / modes (("script"|"free")[])`
- `synopsis / locations[] / npcs[] / playable[] / scripts[]`
- `tier1: { scores: Record<dim, number | "N/A">, total: number, reasoning: string, retried: bool, retry_reasoning?: string }`
- `tier1_retry?: { scores, total }`（重 generate 后的二次评分）
- `status: "generating"|"passed"|"tier1_failed"|"tier1_retried_pass"|"featured_candidate"|"discarded"`
- `featured_for: string[]`（"剧本" / "自由"）
- `session_count: { script, free }`
- `avg_tier2: { script: number|null, free: number|null } | null`

### 4.3 Session

关键字段：
- `id / world_id / mode / archetype / model / seed / judge_model`
- `started_at / ended_at / end_reason / turn_count / total_cost_cents`（**cents 整型**，不是 USD float）
- `cost: CostBreakdown`（详细 per-agent / per-provider / per-model 拆分，见 §4.5）
- `tier2_scores: { 推理, NPC, 结局, 代入, 重玩 }`（dimension keys 是中文，**不要改**）
- `tier2_total_weighted: number`
- `tags_count: number`（per-turn tag 总数）
- `issues_noted: string[]`（judge 自由文本）
- `exemplar_quote: string`
- `transcript_status: "full" | "summary"`
- `transcript: TranscriptTurn[] | null`（summary 模式为 null）

### 4.5 CostBreakdown

每个 session + 每个世界（生成阶段）都有 `cost: CostBreakdown`：

```ts
{
  by_agent: Array<{ agent: AgentRole, calls, tokens_in, tokens_out, cost_cents }>,
  by_provider: Array<{ provider: string, calls, cost_cents }>,
  by_model: Array<{ model: string, calls, cost_cents }>,
  cache_hit_rate: number,    // 0-1
  total_cents: number,
  total_tokens_in: number,
  total_tokens_out: number,
}
```

`AgentRole` 枚举：
- `creator` / `image` / `research` / `tier1_judge` —— 生成阶段
- `game` —— 游戏 agent（director / npc / narrator 合并；`token_usage` 当前只在 `purpose=game` 外层包，没有内部 phase 拆分，所以统一计为一类）
- `player` —— 自动玩 agent（gpt-5.5 / haiku）
- `judge` —— Tier2 评分

聚合来源：JOIN `token_usage` 表（按 session_id / world_id + purpose），不重复存。OpenClaw 的 player / judge call 必须各自套 `usage_context(purpose="player"|"judge", ...)`，使其落入 `token_usage` 自然分桶。

`TranscriptTurn`：
- `turn: number`
- `speaker: "narrator" | "player" | "system" | "judge_inline" | "npc-{name}"`
- `text: string`
- `tags?: TagId[]`

### 4.4 Tag

固定 12 个 ID（**不要新增**，新增必须报用户审批）：
- `npc_voice_break / info_leak / case_board_error / prelude_mismatch / ending_misfire / free_drift / image_not_used / npc_homogeneous / moderation_hit / stress_break / runtime_anomaly / other`

### 4.5 Alert

`{ time, level: "info"|"success"|"warning"|"danger", icon: string, msg: string, target?: string }`

---

## 5. 行为约定

- **list endpoints 默认返完整列表**，前端做 client-side 筛选。如果 session 数突破 1000，再考虑分页（不是 v1 必需）
- **写操作返回最新整体 state** 是 nice-to-have，前端会主动 refetch
- **transcript 是大 payload**，列表 endpoint 必须 strip 掉 `transcript` 字段（设为 null）。详情 endpoint 才包含
- **错误格式**沿用项目惯例：`{ code: 0, data, message: "ok" }` 包裹

---

## 6. OpenClaw 必须实施的事

在 Phase 1 plan.md 里明确以下内容：

1. **DB schema**：新增 `experiment_runs / experiment_world_scores / experiment_session_scores / experiment_session_reviews / experiment_alerts` 表（具体 schema OpenClaw 设计，写 Alembic migration）
2. **API endpoint**：按本契约实施 `backend/api/admin_experiments.py`
3. **数据写入**：OpenClaw 实验跑动中往这些表写：每生成完 1 个世界、每完成 1 局 session、每打分完 1 次 → 写库 + 发 alert
4. **现有业务表的复用**：`game_sessions / messages / case_board_history / token_usage` 复用（player 跑出来的就是真 session），实验元数据用新表关联

---

## 7. 不在本契约的事（不要做）

- `experiment_runs` 业务逻辑层（OpenClaw 自己设计编排，本契约只关心**对外暴露的 shape**）
- 通知 / 推送（dashboard 用轮询）
- 实时 WebSocket（轮询足够）
- 多用户 review 协作（单管理员）
- 历史快照 / 时间旅行
