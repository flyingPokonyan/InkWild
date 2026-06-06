# W4-C Checkpoint: WorldCreatorAgentV2 完整 12 阶段流水线

**Date**: 2026-05-10
**Status**: DONE

---

## Files Modified

| File | Action | LOC |
|------|--------|-----|
| `backend/services/world_creator_agent_v2.py` | Rewrite `create_world` (保留 `__init__`) | 417 |
| `backend/tests/test_world_creator_v2_pipeline.py` | Created (new integration tests) | 673 |
| `backend/tests/test_world_creator_v2_entry.py` | Updated 1 obsolete M1 test → M2 behavior | +9 / -9 |

Total new LOC: ~1017 (agent) + 673 (tests) = 1690

---

## 12 阶段实现概览

| Stage | Key | SSE Phase | Builder / Source |
|-------|-----|-----------|-----------------|
| A | research_pack | `research_pack` | `build_research_pack` (三路并发) |
| B | world_base | `world_base` | 单 LLM 内联 prompt → fallback 默认值 |
| C1 | lore_dimensions | `lore_dimensions` | `build_lore_dimensions` |
| C2 | character_roster | `character_roster` | `build_character_roster` |
| D1 | lore_pack | `lore_pack` | `build_lore_pack` (内部 4 路并发) |
| D2 | characters | `characters` | `build_characters_in_batches` (批内 4 路并发) |
| E1 | shared_events | `shared_events` | `build_shared_events` |
| E2 | relations_pack | `relations_pack` | `build_relations_pack` (纯 Python) |
| F | events_data | `events_data` | `build_events_data` (内部 3 路并发) |
| G | playable | `playable` | is_image_target filter，无 LLM |
| H | critic | `critic` | H1 shape + H2 light critic 并发 + H3 moderation |
| I | images | `images` | Placeholder URL（M5 Seedream 接入） |
| J | validating | `validating` | quality_warnings 汇总 |

每阶段均 emit `started` + `completed` progress_event，携带 `stage_index` / `total_stages` / `duration_ms`。

---

## Concurrency Points

```
A (research_pack) → B (world_base)
                         │
            ┌────────────┼────────────┐
           C1             C2
    lore_dimensions   character_roster
            │             │
            ▼             ▼
           D1             D2
       lore_pack       characters ←──── D2 也依赖 C2
            │             │
            └──────┬───────┘
                   ▼
           E1: shared_events  ── E2: relations_pack (instant)
                   │
                   ▼
            F: events_data (内部 3 路并发)
                   │
                   ▼
         G → H (H2: light_critic_lore ‖ light_critic_shared_events)
                   │
                   ▼
            I → J → result → done
```

并发实现方式：
- C1+C2: `asyncio.gather(collect_c1(), collect_c2())` in `_run_c1_c2_concurrent`
- D1+D2: `asyncio.gather(collect_d1(), collect_d2())` in `_run_d1_d2_concurrent`
- H2: `asyncio.gather(light_critic_lore, light_critic_shared_events, return_exceptions=True)`

---

## retry 覆盖

每个 LLM 阶段均用 `with_transient_retry(lambda: ..., max_attempts=3, on_retry=_make_retry_logger(phase))` 包裹。
- retry 只对 transient 异常（网络/5xx/timeout）生效
- on_retry callback 写 structlog warning，不 yield SSE（避免 async generator callback 复杂性）
- 各阶段 try/except 兜底：失败 → 返回空对象，不 crash 流水线

---

## record_intermediate 覆盖

每阶段 completed 后调 `self._record_intermediate(phase, snapshot)`：
- research_pack, world_base, lore_pack, characters, shared_events, events_data
- 失败不抛错（logger.warning）

---

## quality_warnings 汇总

H 阶段三路 warnings 合并到 `all_warnings: list[str]`：
1. `validate_world_shape(payload)` → shape_violation:* 前缀
2. `light_critic_lore` + `light_critic_shared_events` (并发)
3. `moderate_world_payload` → moderation_flag:* 前缀

最终写入 `result_event` payload 的 `quality_warnings` 字段。

---

## Images 阶段说明

Stage I 当前仅赋 `/static/placeholder-cover.png`，不实际调 Seedream。
注释标注 "M5 完整图片接入"。真实图片生成留 M5 acceptance 时接入。

---

## Tests

文件: `backend/tests/test_world_creator_v2_pipeline.py`

| Test | 验证点 |
|------|--------|
| `test_pipeline_emits_all_stages_in_order` | 13 个主阶段全部 emit `started` |
| `test_pipeline_emits_result_with_all_v2_fields` | result payload 含 research_pack / lore_pack / shared_events / events_data / world_characters / playable / quality_warnings |
| `test_pipeline_handles_research_pack_failure_gracefully` | research_pack 抛 RuntimeError → 降级空 pack，流水线跑完到 done |
| `test_pipeline_record_intermediate_called_per_stage` | record_intermediate ≥6 次，含 research_pack / world_base / lore_pack / characters |
| `test_pipeline_concurrent_c1_c2_stages` | roster_start 出现在 lore_dim_done 之前（并发验证） |
| `test_pipeline_quality_warnings_aggregated` | lore/se/moderation warnings 全在 result.quality_warnings |
| `test_pipeline_playable_filtered_from_image_targets` | playable 精确等于 is_image_target=True 的子集 |

### 测试结果

```
tests/test_world_creator_v2_pipeline.py: 7 passed
tests/test_world_creator_v2_entry.py: 6 passed (1 test updated: M1 placeholder → M2 phase check)
Full regression: 559 passed, 2 deselected, 54 deprecation warnings
```

---

## Concerns / Notes

1. **SSE event 格式**: `progress_event` helper 产出的 dict 是 flat 格式（`phase`/`code` 在顶层，`meta` 含 kwargs）。与 generation_feedback.py 实际签名一致，测试中针对两种访问路径做了兼容。

2. **_run_c1_c2_concurrent / _run_d1_d2_concurrent 事件顺序**: 并发任务完成后，events 按 c1 → c2 顺序 yield（不是真正交错）。前端 stages map 不依赖 subtask 顺序，M5 再做交错优化。

3. **subtask events**: 任务规范说"采纳折中方案 B"——只 emit 主阶段 started/completed，不 emit subtask。已按此实现。

4. **test_world_creator_v2_entry.py 改动**: 删除 M1 占位检查（`not_yet_implemented` warning），改为验证 v2 阶段 progress events 存在。原 M1 逻辑已由完整实现替代，旧测试逻辑 trivially invalid。
