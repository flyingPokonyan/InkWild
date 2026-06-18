# InkWild 文档索引

这层文档按“当前权威文档”和“过程资料”分开读。改代码时以当前实现和模块文档为准；旧 plan / spec 只作为背景和决策记录。

## 新人入口

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — 系统是什么、能力边界、顶层数据流。
2. [`modules/README.md`](modules/README.md) — 后端核心模块索引，按能力矩阵定位实现细节。
3. [`operations/quick-deploy.md`](operations/quick-deploy.md) — 从新 clone 到本地跑起来。
4. [`operations/deploy-and-config.md`](operations/deploy-and-config.md) — 生产部署、env、迁移、admin 初始化。

## 按任务阅读

| 任务 | 优先阅读 |
|---|---|
| 改游戏回合流程 / SSE / 多 Agent | [`modules/orchestrator.md`](modules/orchestrator.md), [`modules/sse-protocol.md`](modules/sse-protocol.md), [`modules/director.md`](modules/director.md), [`modules/npc.md`](modules/npc.md), [`modules/narrator.md`](modules/narrator.md) |
| 改记忆 / 案件板 / 状态持久化 | [`modules/memory.md`](modules/memory.md), [`modules/case-board.md`](modules/case-board.md), [`modules/state-and-persistence.md`](modules/state-and-persistence.md) |
| 改 LLM provider / 模型后台 / 成本限流 | [`modules/llm-router.md`](modules/llm-router.md), [`modules/cost-rate-moderation.md`](modules/cost-rate-moderation.md), [`operations/latency-ttft.md`](operations/latency-ttft.md) |
| 改创作工坊 / 生成 Agent / 参考型复刻 | [`modules/world-creator.md`](modules/world-creator.md), [`design/cover-art-spec.md`](design/cover-art-spec.md) |
| 改登录 / admin / audit | [`modules/auth-and-admin.md`](modules/auth-and-admin.md) |
| 改数据库 schema | [`data/schema.md`](data/schema.md), [`MIGRATION_NOTES.md`](MIGRATION_NOTES.md) |
| 改主站视觉 / Play 页 | [`../frontend/AGENTS.md`](../frontend/AGENTS.md)（前端唯一参考；旧 visual-principles / frontend-spec / play-mode-spec 已合并归档到 `_archive/`） |
| 改封面 / 生图产物 | [`design/cover-art-spec.md`](design/cover-art-spec.md) |
| 理解产品方向 | [`product/product-spec.md`](product/product-spec.md) |

## 目录含义

| 目录 | 用途 |
|---|---|
| [`modules/`](modules/) | 当前模块级技术文档，日常改代码最常用。 |
| [`operations/`](operations/) | 本地启动、生产部署、观测、备份、延迟优化。 |
| [`data/`](data/) | 数据库 schema 与迁移演进说明。 |
| [`design/`](design/) | 主站视觉规范、设计令牌、Play 页规范、封面图规范。 |
| [`product/`](product/) | 产品说明和玩法定位。 |
| [`plans/`](plans/) | 已落地或待落地的工程计划；读作背景，不自动等同当前实现。 |
| [`experiments/`](experiments/) | 评测、实验和外部验证方案。 |
| [`skill/`](skill/) | 项目相关的 AI agent skill 说明。 |
| [`superpowers/`](superpowers/) | 早期/外部工作流产出的 specs 和 plans，保留作历史上下文。 |
| [`_archive/`](_archive/) | 已归档旧文档。 |
| [`assets/`](assets/) | README、品牌和文档使用的静态资源。 |

## 维护约定

- 新的长期有效技术文档优先放进 `modules/`、`operations/`、`data/`、`design/` 或 `product/`。
- 一次性方案、阶段计划和探索记录放 `plans/` 或 `experiments/`，避免混进当前权威文档。
- 被替代的文档移动到 `_archive/`，不要留在入口路径里让读者误读。
- 文档和代码冲突时，以代码为准，并顺手更新对应文档的状态说明。
