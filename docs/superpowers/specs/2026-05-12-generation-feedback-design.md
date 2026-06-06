# 生成 Agent 反馈优化（2026-05-12）

## 范围

一次性修四件事，目标是让创作工坊的 AI 生成过程**可信、可读、可中断**：

1. 阶段列表单一来源 + 顺序对齐后端 `_STAGE_INDEX`
2. 刷新页面时 `stages` Map 从历史事件 hydrate（修复 0/12 卡死 bug）
3. 智能 per-stage 文案：completed 显示数量 + 2-3 代表项，running 显示当前活动；严格单行
4. 长 LLM 阶段补 heartbeat pulse，消除"看着像卡了"的体感

**Out of scope**：阶段耗时面板（item 3 of brainstorm），等到要做生成提速时再做。

---

## 1+2. 阶段列表单一来源 + hydrate

### 新文件

`frontend/lib/admin-generation-stages.ts`：

- 导出 `STAGE_LIST: Array<{ key: StageKey; label: string }>`，**顺序按后端 `_STAGE_INDEX` 对齐**：
  ```
  research_pack → world_base → lore_dimensions → character_roster
  → lore_pack → characters → shared_events → relations_pack
  → events_data → playable → critic → images
  ```
  （把 `lore_pack` 放到 `character_roster` 之后；`visual_brief` 折进 `images`；`validating` 不展示。）
- 导出 `StageKey` literal union
- 导出 `StageState`（从 `GenerationLoadingScreen.tsx` 搬过来），新增 `recentItems: string[]` 字段
- 导出 `initStagesMap()`
- 导出 `formatStageLine(stage, state)` formatter（见 § 3）

### 修改

| 文件 | 变更 |
|---|---|
| `frontend/components/admin/editor/DraftEditorShell.tsx:23-57` | 删 `STAGE_KEYS`/`STAGE_LABEL_ZH`/`initStagesMap`，全部从新模块 import |
| `frontend/components/admin/GenerationLoadingScreen.tsx:21-47` | 删本地 `STAGE_LIST` 和 `StageState`/`StageStatus`，从新模块 import |
| `frontend/lib/admin-progress-state.ts` | 抽出 `applyEventToStages(prev, event): Map`（实时 SSE 和 hydrate 共用）；新增 `hydrateStagesFromEvents(events): Map<StageKey, StageState>` |
| `frontend/components/admin/editor/DraftEditorShell.tsx:170-178` | `loadDraft()` 在 `setPhases(...)` 旁加一行 `setStages(hydrateStagesFromEvents(events))` |
| `frontend/components/admin/editor/DraftEditorShell.tsx:218-243` | 实时 SSE handler 改用共享的 `applyEventToStages`（避免逻辑两份） |

---

## 3. 智能 per-stage 文案

### Formatter 契约

```ts
function formatStageLine(
  stage: StageKey,
  state: StageState,
): { running?: string; completed?: string };
```

- `running` 在 `state.status === "running"` 时显示在 stage label 旁边
- `completed` 在 `state.status === "completed"` 时显示
- 两者都可能返回 `undefined`，调用方自行兜底（fallback = 不显示附加文案）

### 文案表

| 阶段 | running | completed |
|---|---|---|
| research_pack | "正在检索 & 整理参考素材…"（依赖 pulse） | "{n} 条素材 · {sample}" |
| world_base | "正在搭世界骨架…"（依赖 pulse） | "{world_name} · {sample} 等 {n} 地" |
| lore_dimensions | "正在规划世界维度…"（依赖 pulse） | "{n} 维度 · {sample}" |
| character_roster | "正在规划角色阵容…"（依赖 pulse） | "{n} 位身份 · {sample}" |
| lore_pack | "刚补完：{recentItems}" | "{n} 维度补全 · {sample}" |
| characters | "刚生成：{recentItems}" | "{n} 位 · {sample} 等" |
| shared_events | "正在编织共享历史…"（依赖 pulse） | "{n} 段历史 · {sample}" |
| relations_pack | "正在推导关系网…" | "{n} 位角色 · 共 {edge_count} 条关系" |
| events_data | "刚设计事件：{recentItems}" | "{n} 事件 · {clue_count} 线索 · {sample}" |
| playable | "正在筛选可玩视角…" | "选定 {n} 位 · {sample}" |
| critic | "正在打磨细节…" | "通过" 或 "修正 {repair_count} 处" |
| images | "刚画完：{recentItems}" | "{cover_count} 主图 · {avatar_count} 头像" |

### 单行强约束

所有 stage 行（label + running/completed 附加文案 + subtask 计数）**强制单行 + ellipsis**：

```css
white-space: nowrap;
overflow: hidden;
text-overflow: ellipsis;
max-width: 100%;
```

不在 formatter 里手动截断字符串（避免 CSS 和 JS 双重处理）。

### 前端 state 调整

`StageState` 加 `recentItems: string[]`，保留最近 **3 个** subtask 项（FIFO，超出 shift）。

- subtask_completed 来事件 → push `meta.payload_summary.name | title | label | dim_label`（按 stage 取对应字段）
- hydrate 时 `applyEventToStages` 同步重建 recentItems
- 渲染时取最近 2 项拼 `、` 分隔

### 后端 payload 补充

每个 `completed` 事件 meta 增加 `sample: string[]`（2-3 个代表项）；其他字段按表中变量补：

| 事件 | 现有 meta | 新增 |
|---|---|---|
| `world_base.completed` | `world_name`, `location_count` | `sample` = 前 3 个 location name |
| `lore_dimensions.completed` | — | `dimension_count`, `sample` = 前 3 个 dim label |
| `character_roster.completed` | — | `role_count`, `sample` = 前 3 个 role_tag |
| `lore_pack.completed` | `dimension_count` | `sample` = 前 3 个 dim label |
| `lore_pack.subtask_completed` | `content_blocks` | `dim_label`（中文名）|
| `characters.completed` | `character_count` | `sample` = 前 3 个 character.name |
| `shared_events.completed` | `event_count` | `sample` = 前 2 个 event.title |
| `relations_pack.completed` | `npc_count` | `edge_count`（关系总数）|
| `events_data.completed` | `event_count` | `clue_count`, `sample` = 前 2 个 event.title |
| `events_data.subtask_completed` | `event_id` | `title` |
| `critic.completed` / `critic.repair_completed` | — | `repair_count`（仅 repair_* 事件）|
| `images.completed` | `image_count` | `cover_count`, `avatar_count` |
| `images.subtask_completed` | — | `label`（"cover" / "list" / 角色名）|

---

## 4. heartbeat pulse

### 后端 helper

`backend/services/world_creator_agent_v2.py` 新增：

```python
async def _run_with_pulse(
    self,
    phase: str,
    work: Coroutine[Any, Any, T],
    *,
    interval: float = 7.0,
) -> AsyncIterator[dict | tuple[Literal["result"], T]]:
    """Yields pulse progress events every `interval` seconds while `work` runs.
    Final yielded item is ('result', value) — caller unpacks the work result.
    Exceptions in work re-raise to caller."""
```

实现要点：
- 用 `asyncio.Queue` 汇流 work 完成和定时器 tick
- `pulse_task` 每 `interval` 秒往 queue 放一个 `("pulse", None)`
- `work_task` 完成时往 queue 放 `("result", value)` 或 `("error", exc)`
- finally 块 cancel 两个 task
- 调用方循环 `async for item in self._run_with_pulse(...)`：tuple 是终态，dict 是 pulse event 直接 yield 出去

### 应用范围

5 个长 LLM、当前只有 started/completed 两拍的阶段：
- `research_pack`
- `lore_dimensions`
- `character_roster`
- `shared_events`
- `visual_brief`

### Pulse 模板

`backend/services/generation_feedback.py` 新增：

```python
("research_pack", "pulse"): "正在整理参考素材…"
("lore_dimensions", "pulse"): "正在拓展世界各维度…"
("character_roster", "pulse"): "正在校准角色身份和密度…"
("shared_events", "pulse"): "正在编织共享历史的因果链…"
("visual_brief", "pulse"): "正在统一视觉语言…"
```

### 频率

全局 7s。调用方可覆盖。

### 前端行为

- pulse 事件 append 到 `phases`（驱动 headline 切换 + 时间线）
- **不进 stages 状态机**（不改变 ●/○ 状态，不影响进度条计算）
- `admin-progress-view.ts` 的 `PHASE_CODE_PROGRESS` 给 5 个阶段加 `pulse: 0.5` 项（让加权进度在 LLM 跑的中段不是 0）

---

## File impact summary

**新文件**：
- `frontend/lib/admin-generation-stages.ts`

**修改**：
- `frontend/components/admin/editor/DraftEditorShell.tsx`
- `frontend/components/admin/GenerationLoadingScreen.tsx`
- `frontend/lib/admin-progress-state.ts`
- `frontend/lib/admin-progress-view.ts`（pulse 权重）
- `backend/services/world_creator_agent_v2.py`
- `backend/services/generation_feedback.py`

---

## 决策记录

- **包含** `clue_count`（events_data）和 `cover_count`/`avatar_count`（images）—— 便宜且能看出"质量纵深"
- **不细化** critic repair 标签 —— 现状只有 count，没结构化数据，强行补成本高
- `sample` 列表统一 **2-3 个**，超出靠 CSS ellipsis
- Pulse 频率 **7s 全局统一**，单点配置便于调整
- 单行约束**只用 CSS**，formatter 不做字符截断

---

## Out of scope（follow-up）

- 阶段耗时面板（item 3）—— 数据已经在 `duration_ms`，留着等生成提速期接入
- SSE 重连对账（streamAdminEvents 建立后再 loadDraft 一次）—— hydrate 之后基本够用，缺 1-2 拍可接受
