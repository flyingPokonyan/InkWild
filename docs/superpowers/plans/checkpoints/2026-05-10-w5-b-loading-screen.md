# W5-B Checkpoint: GenerationLoadingScreen 12 阶段细粒度进度

**Date:** 2026-05-10
**Status:** DONE

---

## Files Modified

- `frontend/components/admin/GenerationLoadingScreen.tsx` — 主要改造
- `frontend/components/admin/editor/DraftEditorShell.tsx` — 传 `stages` prop + 导入类型

---

## Summary

### GenerationLoadingScreen.tsx

新增功能（保留全部现有 UI 不变）：

1. **导出类型** `StageStatus` 和 `StageState`（从 DraftEditorShell 迁入），供 shell 共用
2. **定义 STAGE_LIST**：12 个阶段 key→label 映射（中文）
3. **新增 `stages?: Map<string, StageState>` prop**
4. **12 阶段面板**（仅当 `stages` 非 undefined 时渲染）：
   - 整体进度条 `stagesCompleted / 12`（X/12 数字 + 细条）
   - 每阶段状态：`✓` completed / `●` running / `✕` failed / `○` pending
   - 颜色：completed → `--lv-accent`，running → `--lv-warn`，failed → `--lv-danger`，pending → `--lv-ink-5`
   - 子任务并发进度（running 且 subtaskTotal > 0 时：`N / M`）
   - payloadSummary（completed 阶段，`key: value · ...` 格式）
   - 当前运行阶段提示行

### DraftEditorShell.tsx

- 移除本地 `StageStatus` / `StageState` 类型定义，改从 `GenerationLoadingScreen` import
- `showGenerationScreen` 早返回时传入 `stages={stages}`

---

## 12 阶段中文 Label 映射

| key              | label        |
|------------------|--------------|
| research_pack    | 收集研究素材 |
| world_base       | 构建世界基础 |
| lore_dimensions  | 扩展世界维度 |
| lore_pack        | 生成世界设定 |
| character_roster | 规划角色阵容 |
| characters       | 创建角色档案 |
| shared_events    | 设计共享事件 |
| relations_pack   | 构建角色关系 |
| events_data      | 生成事件数据 |
| playable         | 可玩性校验   |
| critic           | 品质审核     |
| images           | 生成配图     |

---

## TS / ESLint / 视觉合规检查

```
npx tsc --noEmit          → 0 errors
npx eslint (两文件)        → 0 errors
grep text-\[[0-9] ...     → 0 命中（无任意字号 class）
grep color-accent|font-size-|--ta- → 0 命中（无旧 token）
```

---

## Design Decisions

- `--lv-warn` 用于 running 状态（token 已存在，非 `--lv-warning`）
- `--lv-danger` 用于 failed 状态
- 面板 background = `rgba(255,255,255,0.03)` + `border: 1px solid var(--lv-line-2)`（与黑底背景融合）
- 整体布局：stages 面板在现有动效 UI 的 content div 内，`text-left` 对齐，避免破坏中心动效视觉
- `lv-t-micro + tabular-nums + var(--lv-font-mono)` 用于 X/12 计数器（数字走 mono 合规）

---

## Concerns / Notes

- stages panel 仅当 prop 非 undefined 时渲染；如 DraftEditorShell 传入 `stages`（始终初始化为 12 pending），面板在生成开始就立即可见
- DraftEditorShell 中 `STAGE_LABEL_ZH` 与 `STAGE_LIST` label 略有差异（label 更详细）—— 两者独立用途，无需合并
