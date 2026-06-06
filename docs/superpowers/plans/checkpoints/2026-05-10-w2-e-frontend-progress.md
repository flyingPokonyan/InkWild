# W2-E Frontend SSE 反馈协议 + 进度条 Checkpoint

Date: 2026-05-10

## Status: DONE

---

## Files modified

| File | Change |
|------|--------|
| `frontend/lib/admin-sse-events.ts` | 新增 `ProgressMeta` 类型、`ProgressEventData` 类型；更新 `AdminProgressEvent.meta` 从 `Record<string, unknown>` 改为 `ProgressMeta`；dispatcher 内 cast 更新为 `Partial<ProgressEventData>` |
| `frontend/components/admin/editor/DraftEditorShell.tsx` | 新增 `StageStatus`、`StageState` 类型；`STAGE_KEYS` 常量（12 个）；`STAGE_LABEL_ZH` 映射；`stages` state（`Map<string, StageState>`）；`streaming`、`completedStages`、`currentStageInfo` 派生值；`onProgress` callback 驱动状态机；主体区域顶部进度条 UI |
| `frontend/lib/admin-progress-state.ts` | 修复 `meta` 类型 cast（从 `Record<string, unknown>` 改为 `ProgressMeta`）；新增 `stage_label` 字段已收录在 `ProgressMeta` |

---

## 12 个主阶段 key 清单

```
research_pack     收集研究素材
world_base        构建世界基础
lore_dimensions   扩展世界维度
lore_pack         生成世界设定
character_roster  规划角色阵容
characters        创建角色档案
shared_events     设计共享事件
relations_pack    构建角色关系
events_data       生成事件数据
playable          可玩性校验
critic            品质审核
images            生成配图
```

---

## 状态机转移规则

| SSE code | 转移动作 |
|----------|---------|
| `started` | `status → "running"`, `startedAt = Date.now()` |
| `completed` / `repair_completed` / `review_adjusted` | `status → "completed"`, `completedAt = Date.now()`, `payloadSummary = meta.payload_summary` |
| `subtask_started` | 更新 `subtaskTotal = meta.subtask_total` |
| `subtask_completed` | `subtaskDone = max(prevDone, meta.subtask_index + 1)` 或 `prevDone + 1` |
| `heartbeat` | 不改状态 |
| `onError` 触发 | 当前 `running` 阶段 `status → "failed"` |

---

## TypeScript / ESLint 检查结果

- tsc errors: **0**
- eslint errors: **0**
- `grep -nE "text-\[[0-9]"` 命中: **0**
- `grep -nE "color-accent|font-size-|--ta-"` 命中: **0**

---

## UI 实现说明

- 进度条仅在 `streaming === true`（generationTask status 为 `pending/running`）时显示
- 目前 `showGenerationScreen` 在 `pending/running/failed` 时会提前返回 `GenerationLoadingScreen`，故进度条在编辑器正文区域实际显示于 SSE 流建立后但 `showGenerationScreen` 条件解除之前（即 streaming 状态切换窗口）；状态机本身在整个 SSE 流期间持续更新，可供后续将进度数据注入 `GenerationLoadingScreen` 使用
- 颜色全部使用 `var(--lv-*)` CSS 变量；字号全部使用 `.lv-t-*` 工具类（`lv-t-caps`、`lv-t-body`、`lv-t-meta`）
- 进度条高度使用 Tailwind 内置 `h-1` / `h-0.5`，宽度用 `style={{ width: \`${percent}%\` }}`（数字 percent 合规）

---

## Concerns / Notes

1. 当前 `showGenerationScreen` 早返回逻辑意味着进度条在编辑器主体中实际上很少可见（task running 时用户看到 GenerationLoadingScreen）。后续可考虑将 `stages` map 传入 `GenerationLoadingScreen` 以在加载界面显示更细粒度进度——但该扩展超出本 task scope，已预留 state。
2. `ProgressMeta.stage_label` 字段新增（后端可选填），兼容 `admin-progress-state.ts` 中已有的 `stageLabelOf` 函数。
3. 未引入任何新 npm 包。
