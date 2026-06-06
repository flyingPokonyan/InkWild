# Checkpoint: W3-A shared_events_builder + relations_pack_builder

**Date**: 2026-05-10
**Plan ref**: `docs/superpowers/plans/2026-05-10-world-creator-v2.md` §3 Task 2.5 + 2.6
**Spec ref**: `docs/superpowers/specs/2026-05-10-world-creator-overhaul-design.md` §2.1, §4.1, §13 AC4

## Status: DONE

## Files Created

| File | Description |
|------|-------------|
| `backend/schemas/shared_events.py` | SharedEventPerception / SharedEvent / SharedEventsPack / ImportantRelation / RelationsPack |
| `backend/services/shared_events_builder.py` | build_shared_events — LLM 抽取 + 校验过滤 + 补充 + dedup |
| `backend/services/relations_pack_builder.py` | build_relations_pack — 纯 Python，无 LLM |
| `backend/tests/test_shared_events_builder.py` | 7 tests，覆盖 source_passage_ids 过滤、NPC 过滤、k_min 补充、title dedup、LLM 失败 fallback |
| `backend/tests/test_relations_pack_builder.py` | 6 tests，覆盖 event_tied 关系、no-self、同派系、敌对派系、max_faction_core_npcs、dedup |

## Tests

```
13 passed in 0.69s
```

回归（含上游 test_research_pack_builder / test_character_roster_builder / test_lore_pack_builder）：
```
38 passed in 1.58s
```

## Key Design Decisions

1. **source_passage_ids 严格过滤**：`_parse_events_from_data` 中过滤 valid_passage_ids 集合之外的 id，满足 AC4 验收。
2. **involved_npcs 严格过滤**：只保留在 characters.name 集合中的 NPC，防止 LLM 幻觉。
3. **补充策略**：条数 < k_min 时第二次 LLM 调用，传入 `valid_passage_ids=set()` 使补充 events 的 source_passage_ids 强制为空列表。
4. **relations 来源 1 dedup**：同 (target, kind) 只保留第一个 event_tied 关系（先入先出）；不做情感分析，默认 trust=2。
5. **max_faction_core_npcs**：按 roster 顺序取前 N 个，控制派系关系扇出。
6. **LLM API 模式**：复用 `research_pack_builder._collect_stream_text` + `_extract_json_from_text`，与已有风格一致。

## Concerns / Notes

- `build_shared_events` 不串入 v2_agent（M2-D 才接入），本 task 纯单元级别。
- `test_llm_failure_returns_empty` 中 boom generator 签名用 `**kw`（原 spec 样板 `*, **kw` 有语法错误，已修正）。
