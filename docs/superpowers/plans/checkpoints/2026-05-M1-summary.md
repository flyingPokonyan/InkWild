# Milestone 1 完成总结 · 基础 + ResearchPack

> 日期：2026-05-10
> 范围：Plan §2 Task 1.0 - 1.11，全部 12 个 task

## 验收

- [x] 所有 task 单元测试 PASS
- [x] 在 `WORLD_CREATOR_V2_ENABLED=false` 下旧 v1 链路完全不受影响
- [x] 在 `WORLD_CREATOR_V2_ENABLED=true` 下生成任务跑出 ResearchPack（含 passages + IPCanon）
- [x] `generation_tasks.intermediate_state.research_pack` 字段被正确写入
- [x] 60K char description POST 返回 422
- [x] admin 在草稿编辑器看得到 ResearchPack（read-only）

## 实际工时

约 4 小时（含 conftest fixture aliasing + 11 task subagent dispatch + spot review + cross-task regression）。

并行执行带来的加速：实际并行峰值 3 路（批 1）+ 2 路（批 2/3/5），单 task 平均 5-15 min；串行估算 2-3 倍时间。

## 关键工程发现（M2-M5 复用）

1. **Python venv 路径**：`/Users/jie/Desktop/code/pokonyan/talealive/.venv/bin/python`
2. **测试命令**：`cd backend && <venv-python> -m pytest <file> -v`
3. **JSONB SQLite 兼容**：`_JSONB = JSON().with_variant(JSONB(), "postgresql")`
4. **LLMRouter API**：`stream_with_tools(messages, tools=[], system, max_tokens)` async generator，逐 `text_delta` 拼字符串。复用 `services/research_pack_builder._collect_stream_text` helper
5. **ResearchBroker 构造**：`(tavily, web_searcher, synthesizer)` —— 第三参是 synthesizer 不是 llm_router
6. **ResearchRequest 字段**：`stage / goal / query_candidates / max_queries`（不是 `queries`）
7. **v1 WorldCreatorAgent 属性**：`self.llm` / `self.image_gen` / `self.research_broker`（v2 注入时改名 broker）
8. **generation_feedback events**：用 `"type"` key 不是 `"event"`；helpers 签名 `(phase, code, **meta)`
9. **GenerationTask launch 入口**：`_run_world_generation`（不是 `launch_world_generation`，subagent 自查找）
10. **ORM JSON 字段 mutation**：必须 `dict(field or {})` 复制后 mutate 才能触发 dirty
11. **`_normalize_world_payload` 是显式白名单**：v2 新增字段（research_pack / lore_pack / shared_events / events_data）需要显式 `if payload.get("xxx") is not None: normalized["xxx"] = ...` 透传
12. **Pre-existing 测试失败**：`test_event_system::test_already_triggered_skipped` + `test_image_storage::test_get_image_storage_returns_oss_backend`，跟 v2 无关

## 文件清单

### 新建
- `backend/migrations/versions/531ec5f45068_world_creator_v2_fields.py`
- `backend/schemas/research_pack.py`
- `backend/services/research_pack_builder.py`
- `backend/services/world_creator_agent_v2.py`
- `backend/tests/test_world_creator_v2_migration.py`
- `backend/tests/test_world_creator_v2_settings.py`
- `backend/tests/test_research_pack_schema.py`
- `backend/tests/test_research_pack_builder.py`
- `backend/tests/test_research_broker_passages.py`
- `backend/tests/test_research_broker_summarize.py`
- `backend/tests/test_research_pack_merge.py`
- `backend/tests/test_admin_world_gen_validation.py`
- `backend/tests/test_world_creator_v2_entry.py`
- `backend/tests/test_intermediate_state.py`
- `frontend/components/admin/editor/sections/ResearchPackSection.tsx`
- 11 个 task checkpoint 文件 in `docs/superpowers/plans/checkpoints/`

### 修改
- `backend/tests/conftest.py`（加 3 个 alias fixture）
- `backend/models/world.py`（lore_pack/shared_events/events_data 字段）
- `backend/models/generation_task.py`（intermediate_state 字段）
- `backend/config.py`（4 个 settings）
- `backend/services/research_broker.py`（collect_passages + summarize_passages）
- `backend/services/research_pack_builder.py`（build_research_pack）
- `backend/services/generation_task_service.py`（_run_world_generation 切 v1/v2 + record_intermediate）
- `backend/api/admin.py`（描述/outline 长度 422 校验 + research_pack 透传）
- `frontend/app/admin/worlds/drafts/[id]/page.tsx`（注册 ResearchPackSection）

## 已知 caveat

1. `_normalize_world_payload` 加了 research_pack 透传（M1 修补），M2 加 lore_pack 字段时需要补同样的透传
2. v2 agent 还没接入 retry/checkpoint（M4 task 4.7 实现）
3. `ResearchPackSection` 仅在 draft.payload.research_pack 存在时渲染；老世界字段为 null，invisible（这是预期）

## M2 入场前需要做的

- 无前置任务。M2 可立即启动。
- M1 关键发现（上面 12 条）需要 baked-in 到 M2 dispatch prompt 模板里。

## 测试统计

- 新加测试：33 个（v2 相关）
- 总回归：390 PASS，2 deselected（pre-existing failure，无关）
- 前端 tsc：PASS（0 errors）
