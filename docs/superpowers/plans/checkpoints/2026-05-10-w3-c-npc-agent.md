# Checkpoint: W3-C NPC Agent v2 Injection

**Date**: 2026-05-10
**Task**: §7.1 NPC Agent 注入扩展（Task 5.1 / 5.2 / 5.3）

## Status: DONE

---

## Files Modified

| File | Change |
|------|--------|
| `backend/engine/memory_manager.py` | Added 3 instance methods to `MemoryManager` class: `find_relevant_lore`, `find_npc_shared_events`, `find_npc_rumors` |
| `backend/engine/prompts.py` | `build_npc_system` signature extended with 3 new optional kwargs (`relevant_lore`, `involved_shared_events`, `relevant_rumors`); 3 prompt sections appended when non-empty |
| `backend/engine/npc_agent.py` | `NPCAgent.run()` extended with matching 3 kwargs; forwarded to `build_npc_system` |
| `backend/engine/orchestrator.py` | In `npc_tasks` loop: calls 3 new `self.memory_manager.*` methods, adds results to each NPC task kwargs |

## Files Created

| File | Content |
|------|---------|
| `backend/tests/test_memory_manager_v2_recall.py` | 17 unit tests for `find_relevant_lore`, `find_npc_shared_events`, `find_npc_rumors` |
| `backend/tests/test_npc_agent_v2_injection.py` | 8 integration tests for `build_npc_system` v2 prompt rendering |

---

## memory_manager API

**Class method** (not module function) — `MemoryManager` is a class. All 3 new helpers are instance methods:

```python
def find_relevant_lore(self, npc_knowledge: list[str], lore_pack: dict | None, *, top_k: int = 3) -> list[dict]
def find_npc_shared_events(self, npc_name: str, shared_events: list[dict] | None) -> list[dict]
def find_npc_rumors(self, npc_name: str, events_data: list[dict] | None, triggered_event_ids: set[str] | None = None) -> list[str]
```

Called in orchestrator as `self.memory_manager.find_relevant_lore(...)` etc.

---

## Tests

```
tests/test_memory_manager_v2_recall.py  17 passed
tests/test_npc_agent_v2_injection.py    8 passed
Total new tests: 25 passed
```

Full regression: **502 passed**, 14 pre-existing errors (SQLAlchemy infrastructure — missing `npc_relations` table in test DB, unrelated to this task).

---

## Design Notes

### find_relevant_lore
- Uses keyword substring matching (query terms from `npc_knowledge` split on whitespace vs block heading+body lowercased).
- Returns enriched dicts carrying `key`, `name` (from parent dimension) plus `heading`, `body`, `_score`.
- TODO comment in code: upgrade to embedding cosine similarity via `services/embedding_service.py`.

### find_npc_shared_events
- Filters `shared_events` by `involved_npcs` containment.
- Outputs only `perceptions[npc_name]` view — other NPCs' perceptions never included (information isolation).
- Missing `perceptions[npc_name]` → `knows/believes/feels` default to `""`.

### find_npc_rumors
- Skips events in `triggered_event_ids` (fired events are no longer rumours).
- Deduplication via `seen: set[str]`.

### Prompt Sections (build_npc_system)
Three sections appended after "## 导演指令", each omitted entirely when the list is empty/None:
- `## 相关世界规则（如对话涉及，可参考避免编造）`
- `## 涉及你的过往事件（你的视角）`
- `## 你听说的传闻（话题相关时可自然提及，不必每轮都说）`

### Backward Compatibility
- All 3 new params default to `None` in `build_npc_system` and `NPCAgent.run()`.
- Existing callers with no v2 args are unaffected.

---

## Concerns / Notes

None. Implementation straightforward; all tests pass.
