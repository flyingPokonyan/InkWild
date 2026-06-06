# Checkpoint: W3-B events_data_builder

**Date**: 2026-05-10
**Task**: Task 3.2-3.4 — events_data schema + builder + tests

## Status: DONE

### Files modified

- **Created** `backend/schemas/events_data.py`
  - `EventKind`, `TriggerNPCIntent`, `TriggerConditional`, `EventEffects`, `EventRumor`, `EventDataEntry`

- **Created** `backend/services/events_data_builder.py`
  - `build_events_data(description, ip_canon, characters, locations, shared_events, lore_pack, llm_router, *, target_count, batch_size, concurrency) -> list[EventDataEntry]`
  - Imports `engine.condition_dsl.parse` for DSL validation
  - Batch splitting: `⌈target_count/batch_size⌉` batches, concurrent with `asyncio.gather(return_exceptions=True)`
  - Validation order: parse condition_dsl → npc_name ref → rumors filter → npc_mood_changes filter
  - Single-batch failure isolated; total dedup by id (first occurrence wins)
  - Helpers `_collect_stream_text` + `_extract_json_from_text` copied from `research_pack_builder` pattern

- **Created** `backend/tests/test_events_data_builder.py`
  - 9 tests covering: basic generation, DSL parse failure, invalid npc_name, rumor knower filtering, npc_mood_changes key filtering, batch splitting, single-batch failure isolation, dedup by id, total LLM failure

### Tests

```
tests/test_events_data_builder.py  9 passed
Regression (condition_dsl + events_data + shared_events + relations): 67 passed
```

### Concerns / Notes

- `condition_dsl` string in trigger may contain locations (e.g., `location_is('X')`) — per spec decision, only `trigger.npc_name` / `rumors.knower_npcs` / `npc_mood_changes` keys are strictly validated. `location_is('X')` references are left to runtime `evaluate()` which returns `False` if location not found.
- `kind` field is passed through to `EventDataEntry` as-is; Pydantic validates the `Literal` type on construction — if LLM outputs an unknown kind string, Pydantic will raise a `ValidationError` caught by the `_validate_event` try/except, logging a warning and skipping the entry.
- Concurrency grouping: batches are processed in groups of `concurrency` size sequentially, passing `existing_ids` from prior groups to avoid id collisions in prompts.
