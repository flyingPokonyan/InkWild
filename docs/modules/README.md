# 模块与子系统说明

这个目录存放 InkWild 各**功能模块/子系统的技术架构与能力说明**。

每篇文档以**能力矩阵**为核心——按子领域分组列出能力点（✅/🟡/🔵/❌ 状态符号），让读者一眼看到：模块现在能做什么、有哪些 gap、哪些可以优化。

读完顺序建议：先读 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) 顶层导航 + 系统级能力清单 → 跳到感兴趣的模块 → 看代码。

每篇文档遵循 [`_template.md`](./_template.md) 的章节结构。

## 引擎核心

| 文档 | 内容 |
|---|---|
| [orchestrator.md](./orchestrator.md) | `process_action` 主流水线 / 早流式 / 阶段 timing / narrative_arc 三幕 |
| [director.md](./director.md) | DirectorAgent / DIRECTOR_TOOL schema / parse retry / player_action |
| [npc.md](./npc.md) | NPC 演绎、记忆隔离、群像、关系、信息边界（**样板文档**） |
| [narrator.md](./narrator.md) | 叙事 weave + 早流式 prelude |
| [memory.md](./memory.md) | 隔离记忆、语义召回、reflection、info_propagation |
| [case-board.md](./case-board.md) | ops 序列、history、严格 clue_id 锚点 |
| [intent-system.md](./intent-system.md) | NPC 内驱目标、urgency → effect |
| [world-simulator.md](./world-simulator.md) | 时钟、世界事件、environment 变化 |
| [state-and-persistence.md](./state-and-persistence.md) | GameState、乐观锁、SessionLock |

## 横切关注

| 文档 | 内容 |
|---|---|
| [llm-router.md](./llm-router.md) | provider 抽象 + slot 绑定 + timeout/retry/identity |
| [sse-protocol.md](./sse-protocol.md) | 完整 SSE 事件清单 + 错误码 + 心跳约定 |
| [cost-rate-moderation.md](./cost-rate-moderation.md) | 成本 / 限流 / 内容审核三件横切 |
| [credits.md](./credits.md) | 积分：cost-pegged 计费、L3 持仓预留、可靠结算、对账、cache-aware |
| [auth-and-admin.md](./auth-and-admin.md) | 用户、admin、audit |

## 创作工坊

| 文档 | 内容 |
|---|---|
| [world-creator.md](./world-creator.md) | 五层模型、SSE 任务流、并发限制、草稿/发布原子性、图片 retry |

---

模板：[`_template.md`](./_template.md) — 写新模块文档时严格对照。
