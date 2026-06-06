# Checkpoint: W2-A — lore_dimensions + lore_pack builder

**Date:** 2026-05-10
**Task:** Plan §3 Task 2.1 + 2.2 — build_lore_dimensions + build_lore_pack

## Status: DONE

---

## Files modified

| Action | Path |
|--------|------|
| Created | `backend/schemas/lore_pack.py` |
| Created | `backend/services/lore_pack_builder.py` |
| Created | `backend/tests/test_lore_pack_builder.py` |

No existing files were modified.

---

## Implementation summary

### `schemas/lore_pack.py`
Four Pydantic v2 models:
- `LoreDimension` — dimension descriptor (key / name / why_relevant)
- `LoreContentBlock` — heading + body pair
- `LoreDimensionContent` — dimension key + name + list of content blocks
- `LorePack` — top-level container: list of LoreDimensionContent + generated_at ISO timestamp

### `services/lore_pack_builder.py`
- Reuses `_collect_stream_text` and `_extract_json_from_text` imported directly from `services.research_pack_builder` (no rewrite)
- Prompts are inlined (generation_prompt_builder.py untouched)
- `build_lore_dimensions`: single LLM call, parses `{"dimensions": [...]}`, graceful fallback to `[]` on any error
- `build_lore_pack`: creates `asyncio.Semaphore(concurrency)`, launches one coroutine per dimension, uses `asyncio.gather(return_exceptions=True)`, maps exceptions to empty-content `LoreDimensionContent`
- `generated_at` set via `datetime.now(timezone.utc).isoformat()` regardless of dimension count (including empty)

---

## Concurrency verification

Test `test_lore_pack_respects_concurrency_limit` confirms: with `concurrency=2` and 5 dimensions each sleeping 20ms, the peak in-flight count was ≤ 2.

Mechanism: `asyncio.Semaphore(concurrency)` wraps `async with semaphore:` inside `_build_single_dimension_content`. All tasks are submitted via `asyncio.gather` simultaneously, but the semaphore gates actual LLM calls.

---

## Tests

```
tests/test_lore_pack_builder.py::test_dimensions_returns_list                    PASSED
tests/test_lore_pack_builder.py::test_dimensions_empty_when_genre_simple         PASSED
tests/test_lore_pack_builder.py::test_dimensions_handles_invalid_json            PASSED
tests/test_lore_pack_builder.py::test_dimensions_handles_llm_exception           PASSED
tests/test_lore_pack_builder.py::test_lore_pack_concurrent_calls                 PASSED
tests/test_lore_pack_builder.py::test_lore_pack_single_dimension_failure_isolates PASSED
tests/test_lore_pack_builder.py::test_lore_pack_empty_dimensions_returns_empty_pack PASSED
tests/test_lore_pack_builder.py::test_lore_pack_respects_concurrency_limit       PASSED

8 passed in 0.48s
```

### Regression (M1 + new)
```
28 passed in 1.23s
(test_research_pack_builder, test_research_pack_schema, test_research_pack_merge, test_lore_pack_builder)
```

---

## Concerns / Notes

- `_collect_stream_text` and `_extract_json_from_text` are private (leading underscore) in `research_pack_builder`. They are imported as-is per the task spec. If the research_pack_builder module is ever refactored, these helpers should be promoted to a shared utility module.
- Passage matching (`_match_passages_for_dimension`) uses simple `dimension.key` keyword split + substring match. Sufficient for MVP; can be upgraded to embedding-based similarity when available.
- `build_lore_pack` with `return_exceptions=True` in `asyncio.gather` is belt-and-suspenders: `_build_single_dimension_content` already catches all exceptions internally, so the gather-level handler is a safety net only.
