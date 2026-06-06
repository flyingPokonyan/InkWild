# 归档目录

只保留有**追溯价值**的文档。被新文档完全替代的旧内容已删除（不是 git repo，删了就没了——但 ARCHITECTURE + modules/* 已经覆盖现状，留也是包袱）。

## 当前留存

### `decisions-2026-04-30.md`

原 `superpowers/plans/2026-04-30-launch-readiness-roadmap.md`。包含：

- **Phase 0 → Phase 3 演进记录**：每个阶段的任务清单、状态符号 ✅❌、完成情况
- **2026-05-08 范围调整决策**：哪些任务砍掉了 + 砍的理由（一人开发 / 触发条件不满足 / 等）
- **Phase 0 已落地内容的中文摘要**（第 9-46 行）

未来当你看到"为什么 X 没做"或"为什么砍了 Y"时，先来这里查。

### `frontend-refactor-2026-05.md`

原 `docs/plans/frontend-refactor-2026-05.md`。2026-05-08 启动到 2026-05-23 v2.3 cinematic gold 收尾，
覆盖了从"四种视觉年代杂烩"到统一 `.lv-theme` v2.3 的整个迁移，含：

- 7 个阶段（type system / docs / eslint / 基础设施 / 移动端 / page train / play 专属 / PWA）的产物
- 关键决策：ESLint 最小约束（仅锁旧 token）、Storybook 砍掉用 dev 路由代替、admin 控制台独立项目
- v2.2 → v2.3 色板换皮记录（accent 改香槟金、accent-2 苔绿 → 银雾、danger 暖珊瑚）

视觉规范现以 `docs/design/visual-principles.md` v2.3 + `frontend-spec.md` v2.3 为准。

### `ip-fidelity-phase1-zhuyu-baseline.md`

封面图 prompt 早期 baseline 测试记录。当前生图范式见 `docs/plans/cover-image-prompt-redesign-2026-05.md` 和 `docs/design/cover-art-spec.md`。

## 已删除（被新文档完全替代）

| 旧文件 | 替代品 |
|---|---|
| `tech-design.md` | `docs/ARCHITECTURE.md` + `docs/modules/*` |
| `世界引擎.md` | `docs/modules/orchestrator.md` 等引擎核心模块文档 |
| `世界生成Agent.md` | `docs/modules/world-creator.md` |
| `generation-agent-product-guide.md` | `docs/modules/world-creator.md` |
| `generation-agent-technical-guide.md` | `docs/modules/world-creator.md` |
| `superpowers/plans/2026-04-30-phase-0-pre-launch-blockers.md` | TDD 步骤已全做完，无追溯价值 |
| `superpowers/specs/`（空目录） | — |
