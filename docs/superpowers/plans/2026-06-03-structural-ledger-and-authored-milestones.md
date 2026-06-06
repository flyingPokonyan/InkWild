# Structural Ledger + Authored Milestones (S3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the world a persistent **structural ledger** overlaid on the seed spine, so committed structural facts (deaths, role/identity changes, allegiance shifts, world-truth flips) actually change what the Director/NPCs see — with the first commit path being **author-defined milestones** evaluated deterministically (no LLM).

**Architecture:** Add `structural_facts` to `GameState` (persisted). A new `engine/structural_ledger.py` owns (a) `apply_structural_overlay(world_data, facts)` — folds the ledger onto the seed's `base_setting` + `npc_descriptions` before prompt-build, and (b) `commit_structural_fact(state, fact)` — appends to the ledger + applies a bounded **one-order** cascade keyed by `kind`. Author milestones live in `world_data["structural_milestones"]` and are evaluated each tick by a new `_process_structural_milestones` in `world_simulator.py`, reusing the existing `condition_dsl` evaluator (same mechanism as `events_data`). The orchestrator applies the overlay right after the v2 `WorldSimulator.tick`, so a milestone committed this turn is visible to the Director the same turn. **No LLM. Free-mode arbiter is S4 (separate plan).**

**Tech Stack:** Python 3.12, async, structlog, pytest. Reuses `engine/condition_dsl.py` (`dsl_parse`/`evaluate`), `engine/state_manager.py`, `engine/world_simulator.py`, `engine/prompts.py` (consumes overlaid `world_data`).

> **Repo note:** 0-commit repo, commits held. Commit steps `git add` only the touched files; **confirm with the user before the first commit.**

> **Tests:** in container `talealive-backend-1`: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest <path> -v'`. Backend is bind-mounted (host edits seen immediately).

> **Spec:** [`../specs/2026-06-03-structural-evolution-pipeline-design.md`](../specs/2026-06-03-structural-evolution-pipeline-design.md) §2.2, §3.3, §3.4, §4. Builds on Plan 1 (`structural_change_proposed` field already exists).

> **Genre-neutrality (hard, spec §1.2):** zero genre-specific branches; `kind` is the only switch and it is mechanical, not narrative. Tests span ≥3 genres.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/engine/state_manager.py` | `GameState` | Add `structural_facts: list[dict]` field + `to_dict` line (from_dict is field-filtered, auto-handles it) |
| `backend/engine/structural_ledger.py` | **NEW** — overlay + commit/cascade | Create `apply_structural_overlay`, `commit_structural_fact`, `STRUCTURAL_KINDS` |
| `backend/engine/world_simulator.py` | per-tick rule engine | Add `_process_structural_milestones`, call it in `WorldSimulator.tick` |
| `backend/engine/orchestrator.py` | v2 turn path | Apply overlay to `world_data` right after the v2 tick (before prompt build) |
| `backend/tests/test_structural_ledger.py` | **NEW** | overlay (NPC + base_setting) + commit cascade (4 kinds), cross-genre |
| `backend/tests/test_structural_milestones.py` | **NEW** | milestone eval → commit, dedupe, bad-DSL safety |

**Structural fact shape** (one ledger entry):
```python
{
  "fact_key": str,        # stable key, e.g. "char.role.zhenhuan"
  "fact_text": str,       # human overlay text, e.g. "甄嬛已被册立为皇后。"
  "kind": str,            # one of STRUCTURAL_KINDS
  "target_ref": str | None,  # entity name for entity_*/relation_*; None for world_fact
  "effective_round": int,
  "provenance": str,      # "authored_milestone" (S3) | "free_arbiter" (S4)
}
```

**Authored milestone shape** (in `world_data["structural_milestones"]`):
```python
{
  "milestone_id": str,
  "fact_key": str, "fact_text": str, "kind": str, "target_ref": str | None,
  "trigger": {"condition_dsl": "world_state.<key> == true and ..."},  # reuses condition_dsl
}
```

---

## Task 1: Add `structural_facts` to GameState

**Files:**
- Modify: `backend/engine/state_manager.py` (GameState dataclass ~line 116; `to_dict` ~line 145)
- Test: `backend/tests/test_structural_ledger.py` (NEW)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_structural_ledger.py`:

```python
from engine.state_manager import GameState


def _state(**kw):
    base = dict(current_time="第1天·上午", current_location="主厅")
    base.update(kw)
    return GameState(**base)


def test_structural_facts_defaults_empty_and_roundtrips():
    s = _state()
    assert s.structural_facts == []
    s.structural_facts.append(
        {"fact_key": "char.role.x", "fact_text": "X 已登基", "kind": "entity_role_changed",
         "target_ref": "X", "effective_round": 3, "provenance": "authored_milestone"}
    )
    restored = GameState.from_dict(s.to_dict())
    assert restored.structural_facts == s.structural_facts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -k roundtrips -v'`
Expected: FAIL — `AttributeError: 'GameState' object has no attribute 'structural_facts'`.

- [ ] **Step 3a: Add the field**

In `backend/engine/state_manager.py`, in the `GameState` dataclass, after `world_state: dict = field(default_factory=dict)` (~line 102):

```python
    # Structural evolution ledger (spec §4). Each entry is a committed
    # structural fact overlaid onto the seed spine at prompt-build time:
    # {fact_key, fact_text, kind, target_ref, effective_round, provenance}.
    # Persisted (JSON-safe). Empty for worlds/sessions with no structural change.
    structural_facts: list[dict] = field(default_factory=list)
```

- [ ] **Step 3b: Add the to_dict line**

In `to_dict` (~line 145), after `"world_state": self.world_state,`:

```python
            "structural_facts": self.structural_facts,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -k roundtrips -v'`
Expected: PASS.

- [ ] **Step 5: Commit** (confirm with user first)

```bash
git add backend/engine/state_manager.py backend/tests/test_structural_ledger.py
git commit -m "feat(engine): add structural_facts ledger field to GameState

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `apply_structural_overlay` — fold the ledger onto the seed spine

**Files:**
- Create: `backend/engine/structural_ledger.py`
- Test: `backend/tests/test_structural_ledger.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_structural_ledger.py`:

```python
from engine.structural_ledger import apply_structural_overlay


def test_overlay_appends_entity_note_to_npc_descriptions():
    world = {
        "base_setting": "一座王朝后宫。",
        "npc_descriptions": "华妃年世兰：性烈，掌一宫。\n甄嬛：新晋。",
    }
    facts = [
        {"fact_key": "alive.huafei", "fact_text": "华妃年世兰已于第12回合被赐死，不在人世。",
         "kind": "entity_removed", "target_ref": "年世兰", "effective_round": 12,
         "provenance": "authored_milestone"},
    ]
    out = apply_structural_overlay(world, facts)
    # Original is not mutated.
    assert "已于第12回合被赐死" not in world["npc_descriptions"]
    # Overlay text reaches the spine the Director will read.
    assert "已于第12回合被赐死" in out["npc_descriptions"]


def test_overlay_appends_world_fact_to_base_setting():
    world = {"base_setting": "深空殖民船方舟七号。", "npc_descriptions": ""}
    facts = [
        {"fact_key": "world.capital", "fact_text": "叛军已占领中央舰桥，旧指挥链瓦解。",
         "kind": "world_fact_changed", "target_ref": None, "effective_round": 8,
         "provenance": "authored_milestone"},
    ]
    out = apply_structural_overlay(world, facts)
    assert "叛军已占领中央舰桥" in out["base_setting"]


def test_overlay_noop_when_no_facts():
    world = {"base_setting": "A", "npc_descriptions": "B"}
    out = apply_structural_overlay(world, [])
    assert out["base_setting"] == "A" and out["npc_descriptions"] == "B"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -k overlay -v'`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.structural_ledger'`.

- [ ] **Step 3: Create the module**

Create `backend/engine/structural_ledger.py`:

```python
"""Structural evolution ledger (spec §4): overlay committed structural facts
onto the seed spine, and commit new facts with a bounded one-order cascade.

Genre-neutral: behavior is keyed only by `kind` (a mechanical-consequence
enum), never by narrative category.
"""
from __future__ import annotations

import copy

import structlog

from engine.state_manager import GameState

logger = structlog.get_logger()

# Mechanical-consequence kinds (spec §2.2). Open/extensible: a new kind is
# defined by the one-order cascade it needs, not by plot category.
STRUCTURAL_KINDS = {
    "entity_removed",       # death / permanent exit: drop from presence, mark gone
    "entity_role_changed",  # title / role / status change
    "relation_redefined",   # allegiance / alliance / relationship reframing
    "world_fact_changed",   # base_setting / location / world-truth flip
}

# Facts that describe an entity (rendered into npc_descriptions); the rest
# render into base_setting.
_ENTITY_KINDS = {"entity_removed", "entity_role_changed", "relation_redefined"}


def apply_structural_overlay(world_data: dict, structural_facts: list[dict]) -> dict:
    """Return a shallow copy of *world_data* with the ledger folded onto the
    seed spine. Entity facts append to ``npc_descriptions``; world facts append
    to ``base_setting``. Pure: never mutates the input. No-op when no facts so
    the prefix-cache snapshot stays byte-identical to the seed.
    """
    if not structural_facts:
        return world_data
    overlaid = dict(world_data)
    entity_lines: list[str] = []
    world_lines: list[str] = []
    for fact in structural_facts:
        text = str(fact.get("fact_text") or "").strip()
        if not text:
            continue
        if str(fact.get("kind")) in _ENTITY_KINDS:
            entity_lines.append(f"- {text}")
        else:
            world_lines.append(f"- {text}")
    if world_lines:
        overlaid["base_setting"] = (
            str(world_data.get("base_setting") or "")
            + "\n\n## 已发生的结构性变化（视为既成事实）\n"
            + "\n".join(world_lines)
        )
    if entity_lines:
        overlaid["npc_descriptions"] = (
            str(world_data.get("npc_descriptions") or "")
            + "\n\n## 人物状态的结构性变化（视为既成事实，优先于上文人设）\n"
            + "\n".join(entity_lines)
        )
    return overlaid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -k overlay -v'`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit** (confirm with user first)

```bash
git add backend/engine/structural_ledger.py backend/tests/test_structural_ledger.py
git commit -m "feat(engine): apply_structural_overlay folds ledger onto seed spine

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `commit_structural_fact` — append + bounded one-order cascade

**Files:**
- Modify: `backend/engine/structural_ledger.py`
- Test: `backend/tests/test_structural_ledger.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_structural_ledger.py`:

```python
from engine.structural_ledger import commit_structural_fact


def test_commit_appends_to_ledger_and_is_idempotent():
    s = _state(round_number=5)
    fact = {"fact_key": "alive.x", "fact_text": "X 已死。", "kind": "entity_removed",
            "target_ref": "X"}
    assert commit_structural_fact(s, fact) is True
    assert len(s.structural_facts) == 1
    assert s.structural_facts[0]["effective_round"] == 5
    # Same terminal fact again → idempotent no-op.
    assert commit_structural_fact(s, dict(fact)) is False
    assert len(s.structural_facts) == 1


def test_commit_entity_removed_drops_npc_location():
    s = _state(round_number=2)
    s.npc_locations = {"年世兰": "翊坤宫", "甄嬛": "永寿宫"}
    commit_structural_fact(
        s, {"fact_key": "alive.huafei", "fact_text": "年世兰已赐死。",
            "kind": "entity_removed", "target_ref": "年世兰"}
    )
    assert "年世兰" not in s.npc_locations
    assert "甄嬛" in s.npc_locations  # others untouched


def test_commit_relation_redefined_records_without_removing():
    # Generality: relationship structural fact (e.g. romance breakup / alliance).
    s = _state(round_number=4)
    s.npc_locations = {"里夫斯": "舰桥"}
    ok = commit_structural_fact(
        s, {"fact_key": "rel.reeves_carol", "fact_text": "里夫斯与卡萝结成同盟。",
            "kind": "relation_redefined", "target_ref": "里夫斯"}
    )
    assert ok is True
    assert "里夫斯" in s.npc_locations  # relation change does not remove presence
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -k commit -v'`
Expected: FAIL — `ImportError: cannot import name 'commit_structural_fact'`.

- [ ] **Step 3: Add the function**

Append to `backend/engine/structural_ledger.py`:

```python
def commit_structural_fact(state: GameState, fact: dict) -> bool:
    """Append a committed structural fact to the ledger and apply its bounded
    one-order cascade. Returns False (no-op) if a fact with the same fact_key
    and identical fact_text is already committed (idempotent). Unknown kinds
    are logged and still recorded (overlay renders fact_text), but apply no
    mechanical cascade.

    One-order only (spec §3.3, non-goal §7): no N-order ripple. NPCs improvise
    from the updated spine on subsequent turns.
    """
    fact_key = str(fact.get("fact_key") or "").strip()
    fact_text = str(fact.get("fact_text") or "").strip()
    if not fact_text:
        return False
    kind = str(fact.get("kind") or "").strip()
    target_ref = (str(fact.get("target_ref") or "").strip() or None)

    for existing in state.structural_facts:
        if existing.get("fact_key") == fact_key and existing.get("fact_text") == fact_text:
            return False

    if kind not in STRUCTURAL_KINDS:
        logger.warning("structural_commit_unknown_kind", kind=kind, fact_key=fact_key)

    entry = {
        "fact_key": fact_key,
        "fact_text": fact_text,
        "kind": kind,
        "target_ref": target_ref,
        "effective_round": int(getattr(state, "round_number", 0) or 0),
        "provenance": str(fact.get("provenance") or "authored_milestone"),
    }
    state.structural_facts.append(entry)

    # --- one-order cascade by kind ---
    if kind == "entity_removed" and target_ref:
        state.npc_locations.pop(target_ref, None)
        # Freeze the relation record (kept for history; overlay marks them gone).
        if target_ref in state.npc_relations:
            state.npc_relations[target_ref]["frozen"] = True
    # entity_role_changed / relation_redefined / world_fact_changed: rendered by
    # the overlay (and relation note); no further deterministic state mutation.

    logger.info(
        "structural.committed",
        fact_key=fact_key, kind=kind, target_ref=target_ref,
        round_number=entry["effective_round"], provenance=entry["provenance"],
    )
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py -v'`
Expected: PASS (all overlay + commit tests, ≥3 genres represented: 后宫/方舟/relation).

- [ ] **Step 5: Commit** (confirm with user first)

```bash
git add backend/engine/structural_ledger.py backend/tests/test_structural_ledger.py
git commit -m "feat(engine): commit_structural_fact with idempotent one-order cascade

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Authored milestone evaluation in the world tick

**Files:**
- Modify: `backend/engine/world_simulator.py` (add `_process_structural_milestones`; call it in `WorldSimulator.tick`)
- Test: `backend/tests/test_structural_milestones.py` (NEW)

> Reuses `engine/condition_dsl.py`: `dsl_parse` + `evaluate` (same as `_process_events_data`). Import names in world_simulator: check the existing `events_data` block (~line 120) for the exact aliases (`dsl_parse`, `dsl_evaluate`/`evaluate`).

- [ ] **Step 0: Confirm condition_dsl import aliases**

Run: `cd backend && grep -n "import.*condition_dsl\|dsl_parse\|dsl_evaluate\|from engine.condition_dsl" engine/world_simulator.py | head`
Expected: shows the alias names used in `_process_events_data`. Use the same in Step 3.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_structural_milestones.py`:

```python
from engine.state_manager import GameState
from engine.world_simulator import _process_structural_milestones


def _state(**kw):
    base = dict(current_time="第1天·上午", current_location="主厅", round_number=7)
    base.update(kw)
    return GameState(**base)


def test_milestone_commits_when_condition_met():
    s = _state()
    s.world_state = {"huafei_disgraced": True}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "alive.huafei", "fact_text": "华妃已赐死。",
         "kind": "entity_removed", "target_ref": "年世兰",
         "trigger": {"condition_dsl": "world_state.huafei_disgraced == true"}},
    ]}
    _process_structural_milestones(s, world)
    assert any(f["fact_key"] == "alive.huafei" for f in s.structural_facts)


def test_milestone_skipped_when_condition_unmet():
    s = _state()
    s.world_state = {"huafei_disgraced": False}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "alive.huafei", "fact_text": "华妃已赐死。",
         "kind": "entity_removed", "target_ref": "年世兰",
         "trigger": {"condition_dsl": "world_state.huafei_disgraced == true"}},
    ]}
    _process_structural_milestones(s, world)
    assert s.structural_facts == []


def test_milestone_not_recommitted_when_already_in_ledger():
    s = _state()
    s.world_state = {"flag": True}
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "k", "fact_text": "事已成。",
         "kind": "world_fact_changed", "target_ref": None,
         "trigger": {"condition_dsl": "world_state.flag == true"}},
    ]}
    _process_structural_milestones(s, world)
    _process_structural_milestones(s, world)  # second tick
    assert len([f for f in s.structural_facts if f["fact_key"] == "k"]) == 1


def test_milestone_bad_dsl_is_skipped_not_raised():
    s = _state()
    world = {"structural_milestones": [
        {"milestone_id": "m1", "fact_key": "k", "fact_text": "x", "kind": "world_fact_changed",
         "trigger": {"condition_dsl": "this is not valid (((", }},
    ]}
    _process_structural_milestones(s, world)  # must not raise
    assert s.structural_facts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_milestones.py -v'`
Expected: FAIL — `ImportError: cannot import name '_process_structural_milestones'`.

- [ ] **Step 3: Add the function + call it in tick**

In `backend/engine/world_simulator.py`, add (mirror `_process_events_data`, reuse its condition_dsl aliases from Step 0 — shown here as `dsl_parse`/`dsl_evaluate`):

```python
def _process_structural_milestones(state: GameState, world_config: dict) -> None:
    """Evaluate author-defined structural milestones; commit those whose
    condition_dsl is satisfied (spec §3.4). Deterministic, no LLM. Reuses the
    same condition_dsl evaluator as events_data. Robust: parse/eval errors are
    logged and skipped. Idempotency is handled by commit_structural_fact.
    """
    from engine.structural_ledger import commit_structural_fact

    milestones = world_config.get("structural_milestones") or []
    for ms in milestones:
        if not isinstance(ms, dict) or ms.get("disabled"):
            continue
        dsl_source = (ms.get("trigger") or {}).get("condition_dsl", "")
        if not dsl_source:
            continue
        try:
            expr = dsl_parse(dsl_source)
            met = dsl_evaluate(expr, state)
        except Exception:  # noqa: BLE001 — same defensive posture as events_data
            logger.warning(
                "structural_milestone_dsl_error",
                milestone_id=ms.get("milestone_id"), dsl=dsl_source, exc_info=True,
            )
            continue
        if not met:
            continue
        commit_structural_fact(
            state,
            {
                "fact_key": ms.get("fact_key"),
                "fact_text": ms.get("fact_text"),
                "kind": ms.get("kind"),
                "target_ref": ms.get("target_ref"),
                "provenance": "authored_milestone",
            },
        )
```

Then call it inside `WorldSimulator.tick`, right after `_process_events_data(...)` is invoked (so milestones see this tick's world_state changes). Locate that call and add immediately after it:

```python
        _process_structural_milestones(state, world_data)
```

(Use the same `state` / world-config variable names as the surrounding `tick` body — check the `_process_events_data` call site for the exact local names.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_milestones.py -v'`
Expected: PASS (4 tests).

- [ ] **Step 5: Regression — world_simulator + ledger suites**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_milestones.py tests/test_structural_ledger.py -q && python -m pytest tests/ -k "world_sim or simulator" -q 2>&1 | tail -8'`
Expected: new suites PASS; world_simulator suite no new failures.

- [ ] **Step 6: Commit** (confirm with user first)

```bash
git add backend/engine/world_simulator.py backend/tests/test_structural_milestones.py
git commit -m "feat(engine): evaluate authored structural milestones each tick (no LLM)

Reuses condition_dsl; commits structural facts when author conditions met.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Apply the overlay in the orchestrator (after the v2 tick)

**Files:**
- Modify: `backend/engine/orchestrator.py` (v2 path: right after `game_state = tick_result.updated_state` at the v2 tick site ~line 1140)
- Test: manual real-run verification (see Task 6) — the unit behavior is covered by Tasks 2–4; this task is a 2-line wiring whose effect is observed end-to-end.

- [ ] **Step 0: Locate the v2 tick site**

Run: `cd backend && grep -n "tick_result.updated_state\|world_simulator.tick" engine/orchestrator.py`
Expected: the v2 path assignment `game_state = tick_result.updated_state` (the one inside the v2 turn method, ~line 1140, not the v1 ~451). Confirm by surrounding context (`§4.4` comment / `skip intent_advance`).

- [ ] **Step 1: Add the overlay application**

In `backend/engine/orchestrator.py`, immediately after the v2 `game_state = tick_result.updated_state` line, add:

```python
        # Structural ledger overlay (spec §4): fold committed structural facts
        # onto the seed spine BEFORE building the Director/NPC prompts, so a
        # milestone committed in this tick is visible to the Director this turn.
        # No-op (same object) when the ledger is empty → prefix-cache preserved.
        from engine.structural_ledger import apply_structural_overlay
        world_data = apply_structural_overlay(world_data, game_state.structural_facts)
```

- [ ] **Step 2: Verify import + no syntax error**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "import engine.orchestrator; print(\"OK\")"'`
Expected: `OK`.

- [ ] **Step 3: Regression — orchestrator import + changed-module suites**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_ledger.py tests/test_structural_milestones.py tests/test_director_agent.py tests/test_prompts.py -q 2>&1 | tail -6'`
Expected: PASS. (Orchestrator's pre-existing `FakeDirectorAgent.run_v2` failures remain, unrelated.)

- [ ] **Step 4: Commit** (confirm with user first)

```bash
git add backend/engine/orchestrator.py
git commit -m "feat(engine): overlay structural ledger onto world_data after v2 tick

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Real-run verification (no new code — evidence gate)

Like Plan 1, prompt/spine behavior must be observed, not just unit-tested.

- [ ] **Step 1: Drive a real turn where a milestone fires**

Write a throwaway harness (delete after) that:
1. Builds a `GameState` with `world_state` set so an authored milestone's `condition_dsl` is satisfied, and a `world_data` carrying that `structural_milestones` entry + matching `npc_descriptions`.
2. Calls `WorldSimulator().tick(state, world_data)` → assert the fact is now in `state.structural_facts` and (entity_removed) the NPC dropped from `npc_locations`.
3. Calls `apply_structural_overlay(world_data, state.structural_facts)` and prints the resulting `npc_descriptions` / `base_setting` to confirm the overlay text is present.
4. (Optional, costs an LLM call) Runs `DirectorAgent.run_v2` with the **overlaid** world_data + a player line referencing the changed entity, and confirms the Director treats the fact as real (e.g., does not address a removed NPC as present).

- [ ] **Step 2: Capture + report** the printed overlay and (if run) the Director output. Verdict PASS only if the committed fact visibly changes the spine the Director reads.

- [ ] **Step 3: Remove the throwaway harness.**

---

## Self-Review (plan-write time)

**Spec coverage:** §4 ledger → Task 1; §4 overlay (NPC + base_setting) → Task 2; §3.3 commit + one-order cascade (4 kinds) → Task 3; §3.4 authored milestones via condition_dsl → Task 4; "overlay before prompt, same-turn visibility, cache no-op when empty" → Task 5; real-run gate → Task 6. **Out of scope (S4/Plan 3):** free-mode arbiter, `structural_change_proposed` → commit wiring (S4 connects the Director's supported proposals to `commit_structural_fact`). Correctly absent here.

**Placeholder scan:** none. Tasks 4/5 use Step-0 greps to pin exact local names/aliases (real "how", not placeholder) since those weren't read at plan time.

**Type consistency:** ledger entry keys (`fact_key, fact_text, kind, target_ref, effective_round, provenance`) identical across Tasks 1–4. `STRUCTURAL_KINDS` defined in Task 2, used in Task 3. `apply_structural_overlay(world_data, facts)` / `commit_structural_fact(state, fact)` signatures consistent across Tasks 2,3,4,5.

**Genre-neutrality:** `kind`-only switching; tests cover 后宫 (entity_removed/role), 方舟 (world_fact), relationship (relation_redefined) — ≥3 genres.
```
