# MIGRATION_NOTES

记录 Phase 0 + 1 的 breaking change，便于升级 / 回滚 / 排查历史问题时查阅。

---

## 封面图生成 pipeline 重构（2026-05-19）
**Before:** `services/visual_brief.py` 走 brief LLM 出 `WorldVisualBrief` (8 个英文物理字段) → `services/image_prompt_builder.py` 拼成 1100+ 字 dense Chinese-English mixed prompt → gpt-image-2 出图。结果是"AI 风光摄影"，不像电影海报。
**After:** `services/cover_brief.py` 派生 `CoverBrief` (world_name / world_name_english / genre_tag / typography_hint / ip_mode) → 4 个 prompt builder (hero / script / portrait / ending) 出 ~80-230 字自然语言 prompt → gpt-image-2 出"production-grade movie poster"风格图。
**数据迁移：** Alembic `9a8b7c6d5e4f`：
- drop `worlds.visual_brief` JSONB 列（新 pipeline 不再持久化 brief）
- drop `scripts.visual_brief` JSONB 列
- 加 `world_characters.gender` 字段（"男"/"女"/""）—— 原创世界角色 portrait 4-dim descriptor 依赖
- 加 `endings.cover_image` 字段（新增 ending card 类型）
**回滚：** 同时 revert 代码 + Alembic downgrade。注意：visual_brief JSONB 内容不可恢复（drop 即丢）。
**详见：** `docs/plans/cover-image-prompt-redesign-2026-05.md`。

---

## `X-Admin-Key` header 删除
**Before:** 所有 admin 接口靠请求头 `X-Admin-Key` 鉴权，密钥放 `.env`。
**After:** Admin 接口走 cookie session + `users.is_admin=true`，统一通过 `get_current_admin_user` 依赖；写操作必须调用 `record_admin_action` 写审计日志。
**数据迁移：** 自动（Alembic 给 `users` 加 `is_admin` 列），首批 admin 需手动 SQL 标记或通过 CLI 脚本。
**回滚：** 老的 `X-Admin-Key` middleware 已删除，回滚需 revert 路由 + 中间件代码并重设 admin_key env；但 `is_admin` 列可保留不影响。

---

## `seed_system.py` 删除
**Before:** Director 通过 `seed_system.py` 触发"种子事件"（硬编码触发条件 + 模板）。
**After:** 改用 `intent_system`：Director 输出的是结构化 intent，由统一的 intent 调度器消费，事件触发逻辑下沉到 `event_system` + `narrative_arc`。
**数据迁移：** 无需。运行时数据没有"种子"概念。
**回滚：** 需要找回 seed_system.py 旧实现并恢复 director prompt 里对应的 schema。强烈不建议——intent 框架已多处复用。

---

## 案件板从 director snapshot 改为 ops 序列 + `case_board_history` 表
**Before:** Director 每回合输出整张案件板的快照（全量覆盖），前端直接渲染。
**After:** Director 输出增量 ops（add/remove/update），由 `case_board` 模块应用到 `game_state.case_board` 当前快照；每条 op 写入 `case_board_history` 表，支持回放和审计。
**数据迁移：** 自动（Alembic 建 `case_board_history` 表）。已存在的 session 第一次进入会按当前 snapshot 重建一条初始 op。
**回滚：** 需要 revert director schema + case_board 应用逻辑，并允许丢弃 history 表。

---

## `memory_entries` 加 `related_npc` / `embedding` 列
**Before:** memory 条目仅有 content + importance + round 等字段，召回靠 importance + round 倒序。
**After:** 加 `related_npc`（关联 NPC 名）支持按 NPC 反思汇总；加 `embedding`（pgvector 或外部存储）支持语义召回（依赖 `EMBEDDING_ENABLED`）。
**数据迁移：** 自动（Alembic 加列，默认 NULL）。已有数据无 embedding，老逻辑会回落到 importance 排序。
**回滚：** 列保留 NULL 不影响老逻辑，可只 revert 代码。

---

## `game_sessions` 加 `version` 列（乐观锁，409 重试）
**Before:** 并发改 session 没有显式版本控制，依赖 SessionLock 串行化。
**After:** `version` 整数列，每次写自增；写时 WHERE version=X，冲突返回 409，前端按文档规则 retry。
**数据迁移：** 自动（Alembic 加列，默认 0）。
**回滚：** 列保留不影响老代码，可只 revert API 层乐观锁逻辑。

---

## `users` 加 `is_admin` 列
**Before:** 没有 admin 概念，权限靠 `X-Admin-Key`。
**After:** 布尔列 `is_admin`，结合 cookie session 做 admin 鉴权。
**数据迁移：** 自动（Alembic 加列，默认 false）。首批 admin 需手动 UPDATE。
**回滚：** 列保留不影响代码，可只 revert 鉴权逻辑（同 X-Admin-Key 项）。

---

## SSE payload 全部加 `version: 1`，旧前端会被拒
**Before:** SSE event payload 没有版本字段，前后端隐式协议。
**After:** 所有 SSE payload 必须带 `version: 1`；前端解析时校验，缺失或不匹配直接报错或丢弃。
**数据迁移：** 无需。
**回滚：** 前端容错放宽 + 后端去掉 version 字段；不建议，破坏未来灰度升级路径。

---

## LLM 内容审核从硬编码关键词改为 LLM 分类 + 本地 fallback
**Before:** `content_filter` 维护一份关键词黑名单，命中即拒，误伤多。
**After:** `moderation` 模块用便宜 LLM slot 分类（unsafe/safe + 类别 + 置信度）；LLM 不可用或超时时回退到本地关键词作为最后防线。
**数据迁移：** 无需。
**回滚：** 关键词黑名单仍保留作 fallback，可临时关闭 moderation slot 强制走老路径；但风控覆盖会下降。

---

## 新增表

- **`admin_audit_logs`**：所有 admin 写操作的结构化审计（actor/action/target/diff/timestamp）。
- **`case_board_history`**：案件板增量 ops 历史，支持回放与排查。
- **`npc_reflections`**：NPC 长期反思摘要（按 `NPC_REFLECTION_THRESHOLD` 触发）。
- **`npc_relations`**：NPC ↔ NPC 持久关系（read-only first pass，由 `WorldCharacter.initial_peer_relations` 播种）。
- **`generation_tasks`**：创作工坊 AI 生成任务主记录（kind/status/draft 关联/统计）。
- **`generation_task_events`**：生成任务的 SSE 事件流持久化（seq + payload），供断线续传 / 审计。
- **`world_drafts`**：世界草稿，发布后落到 `worlds`。
- **`script_drafts`**：剧本草稿，发布后落到 `scripts`。
- **`model_providers`**：LLM provider 配置（厂商/类型/凭据/端点）。
- **`provider_models`**：每个 provider 暴露的具体模型列表（含探测结果 + 能力标签）。
- **`model_slots`**：业务 slot → provider+model 的动态绑定（director / narrator / npc / compression / moderation / image / embedding 等）。
