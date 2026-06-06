# Generation & Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate four root-cause defects exposed by the 2026-05-23 VPS smoke runs: generator output drift (DSL syntax / endings shape / playable identity) and Director runtime tool_use instability on DeepSeek V4 Pro. Replace the experimental runner's `content_repair.py` band-aid with structural fixes inside the product code.

**Architecture:**
- Generator side: LLM emits a structured condition tree (not DSL string); backend serializes tree → existing DSL string for runtime evaluator (zero runtime change). Endings/playable identity get strict JSON Schema with required fields. Schema violations trigger generator-level regeneration with explicit feedback (max 2), then escalate to `needs_human_review`.
- Runtime side: a per-model capability matrix dispatches Director to JSON mode for reasoning models (DeepSeek V4 Pro, Qwen thinking) and to forced tool_use for strong tool models (Claude, GPT). Retry uses prompt mutation with the specific parse failure reason. No cross-model fallback in this iteration.
- Cleanup: existing `_canonicalize_function_style_ops` DSL normalizer and the runner's `content_repair.py` are deleted once root-cause fixes are validated.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, pytest-asyncio, jsonschema, existing LLMRouter abstraction.

**Out of scope:**
- Cross-model fallback chain (deferred per user decision).
- Migration of existing published worlds — only new generations follow strict schema; legacy DSL strings continue to work via the unchanged runtime parser.

---

## File Structure

**New files:**
- `backend/engine/condition_tree.py` — Tree dataclass + validators + serializer to DSL string.
- `backend/llm/model_capabilities.py` — Model ID → structured output capability lookup.
- `backend/services/generation_schema.py` — JSON Schema definitions for world/script/events/endings, with `validate()` helper that returns structured errors.
- `backend/tests/test_condition_tree.py`
- `backend/tests/test_model_capabilities.py`
- `backend/tests/test_generation_schema.py`
- `backend/tests/test_director_capability_routing.py`
- `backend/tests/test_events_data_builder_tree.py`
- `backend/tests/test_endings_full_schema.py`
- `backend/tests/test_playable_identity_sync.py`

**Modified files:**
- `backend/services/events_data_builder.py` — Switch prompt + validator to condition_tree; remove DSL string acceptance for new generations.
- `backend/services/world_creator_agent_v2.py` — `_generate_endings_v2` schema expanded; playable identity wired into world-setting prompt and validated.
- `backend/services/world_critic_service.py` — Hard fails on schema violation; surfaces structured errors for regen.
- `backend/services/generation_feedback.py` — New repair entry types for schema violations.
- `backend/llm/deepseek.py` — Add `tool_choice` parameter and `stream_json()` method.
- `backend/llm/router.py` — Forward `tool_choice` and `response_format`; expose `current_model_id()` for capability lookup.
- `backend/engine/director_agent.py` — Replace global `prefer_json_mode` flag with capability-based dispatch; add prompt-mutation retry.
- `backend/engine/condition_dsl.py` — Remove `_canonicalize_function_style_ops` (after smoke validation).
- `backend/models/token_usage.py` — Add `outcome` column (success / parse_failure / retried_success) and `retry_count` column.
- `backend/migrations/versions/<new>_add_token_usage_outcome.py` — Alembic migration.
- `backend/config.py` — Remove `director_prefer_json_mode` (replaced by capability matrix).
- `experiments/2026-05-vps-eval/runner/content_repair.py` — DELETED on VPS after smoke validates.
- `experiments/2026-05-vps-eval/runner/smoke_generation.py` — Stop calling `audit_and_repair_world`; assert clean generation.

---

## Phase 1 — Condition Tree

### Task 1.1: Define the condition tree dataclasses and DSL serializer

**Files:**
- Create: `backend/engine/condition_tree.py`
- Test: `backend/tests/test_condition_tree.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_condition_tree.py
import pytest
from engine.condition_tree import (
    ConditionTree,
    ConditionTreeError,
    serialize_to_dsl,
    validate_tree,
)
from engine.condition_dsl import parse as dsl_parse, evaluate


def test_serialize_func_call():
    tree = {"op": "func", "name": "time_after", "args": ["day_3"]}
    assert serialize_to_dsl(tree) == "time_after('day_3')"


def test_serialize_field_comparison():
    tree = {"op": "==", "left": {"field": "world_state.discovered"}, "right": True}
    # Booleans are encoded as 1/0 to match existing evaluator semantics.
    assert serialize_to_dsl(tree) == "world_state.discovered == 1"


def test_serialize_and_or_not():
    tree = {
        "op": "AND",
        "operands": [
            {"op": "func", "name": "time_after", "args": ["day_2"]},
            {
                "op": "OR",
                "operands": [
                    {"op": "func", "name": "location_is", "args": ["朝堂"]},
                    {"op": "NOT", "operand": {"op": "func", "name": "location_is", "args": ["密室"]}},
                ],
            },
        ],
    }
    dsl = serialize_to_dsl(tree)
    assert "AND" in dsl and "OR" in dsl and "NOT" in dsl
    # And it must round-trip through the existing parser without errors.
    dsl_parse(dsl)


def test_serialize_rejects_unknown_op():
    with pytest.raises(ConditionTreeError):
        serialize_to_dsl({"op": "XOR", "operands": []})


def test_validate_unknown_field_with_allowed_keys():
    tree = {"op": "==", "left": {"field": "world_state.unknown_flag"}, "right": True}
    errors = validate_tree(tree, allowed_world_state_keys={"discovered", "met_lead"})
    assert errors and "unknown_flag" in errors[0]


def test_validate_unknown_function():
    tree = {"op": "func", "name": "weather_is", "args": ["sunny"]}
    errors = validate_tree(tree)
    assert errors and "weather_is" in errors[0]


def test_validate_func_arg_count():
    tree = {"op": "func", "name": "time_after", "args": []}
    errors = validate_tree(tree)
    assert errors and "time_after" in errors[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_condition_tree.py -v
```

Expected: ImportError / ModuleNotFoundError for `engine.condition_tree`.

- [ ] **Step 3: Implement `condition_tree.py`**

```python
# backend/engine/condition_tree.py
"""Structured condition tree used by the generator pipeline.

Generators emit a JSON tree; we serialize it to the existing DSL string
(condition_dsl.py syntax) for storage and runtime evaluation. The runtime
evaluator is unchanged — this module exists only at the generator boundary.

Allowed shapes::

    {"op": "func", "name": "time_after" | "location_is" | "player_did", "args": [str]}
    {"op": "==" | "!=" | ">=" | "<=" | ">" | "<",
     "left":  {"field": "world_state.<key>"} | <int>,
     "right": <int> | <bool> | {"field": "world_state.<key>"}}
    {"op": "AND" | "OR", "operands": [<node>, <node>, ...]}     # >= 2 operands
    {"op": "NOT", "operand": <node>}
"""

from __future__ import annotations

from typing import Any

ConditionTree = dict[str, Any]


class ConditionTreeError(ValueError):
    """Raised on malformed tree at serialize time."""


_ALLOWED_FUNCS = {
    "time_after": 1,
    "location_is": 1,
    "player_did": 1,
}
_ALLOWED_CMP = {"==", "!=", ">=", "<=", ">", "<"}


def _is_field(node: Any) -> bool:
    return isinstance(node, dict) and "field" in node and len(node) == 1


def _serialize_operand(node: Any) -> str:
    if isinstance(node, bool):
        return "1" if node else "0"
    if isinstance(node, int):
        return str(node)
    if _is_field(node):
        field = str(node["field"])
        if not field.startswith("world_state."):
            raise ConditionTreeError(f"field must start with world_state.: {field!r}")
        return field
    raise ConditionTreeError(f"unsupported operand: {node!r}")


def _quote(s: str) -> str:
    if "'" in s:
        raise ConditionTreeError(f"single quote in func arg unsupported: {s!r}")
    return f"'{s}'"


def serialize_to_dsl(tree: ConditionTree) -> str:
    """Serialize *tree* into the existing DSL string format.

    Raises ConditionTreeError on malformed input.
    """
    if not isinstance(tree, dict) or "op" not in tree:
        raise ConditionTreeError(f"tree node must be a dict with 'op': {tree!r}")

    op = tree["op"]

    if op == "func":
        name = tree.get("name")
        args = tree.get("args") or []
        if name not in _ALLOWED_FUNCS:
            raise ConditionTreeError(f"unknown function: {name!r}")
        if len(args) != _ALLOWED_FUNCS[name]:
            raise ConditionTreeError(
                f"function {name!r} expects {_ALLOWED_FUNCS[name]} arg(s), got {len(args)}"
            )
        return f"{name}({', '.join(_quote(str(a)) for a in args)})"

    if op in _ALLOWED_CMP:
        left = _serialize_operand(tree.get("left"))
        right = _serialize_operand(tree.get("right"))
        return f"{left} {op} {right}"

    if op in {"AND", "OR"}:
        operands = tree.get("operands") or []
        if len(operands) < 2:
            raise ConditionTreeError(f"{op} requires >= 2 operands")
        parts = [f"({serialize_to_dsl(o)})" for o in operands]
        return f" {op} ".join(parts)

    if op == "NOT":
        operand = tree.get("operand")
        if operand is None:
            raise ConditionTreeError("NOT requires 'operand'")
        return f"NOT ({serialize_to_dsl(operand)})"

    raise ConditionTreeError(f"unknown op: {op!r}")


def validate_tree(
    tree: ConditionTree,
    *,
    allowed_world_state_keys: set[str] | None = None,
) -> list[str]:
    """Walk *tree*, collect human-readable issues. Returns empty list on success."""
    issues: list[str] = []
    _walk(tree, allowed_world_state_keys, issues, path="$")
    return issues


def _walk(
    node: Any,
    allowed_keys: set[str] | None,
    issues: list[str],
    *,
    path: str,
) -> None:
    if not isinstance(node, dict) or "op" not in node:
        issues.append(f"{path}: node must be dict with 'op'")
        return
    op = node["op"]
    if op == "func":
        name = node.get("name")
        args = node.get("args") or []
        if name not in _ALLOWED_FUNCS:
            issues.append(f"{path}: unknown function {name!r}; allowed={sorted(_ALLOWED_FUNCS)}")
            return
        if len(args) != _ALLOWED_FUNCS[name]:
            issues.append(
                f"{path}: function {name!r} expects {_ALLOWED_FUNCS[name]} arg(s), got {len(args)}"
            )
    elif op in _ALLOWED_CMP:
        for side in ("left", "right"):
            val = node.get(side)
            if _is_field(val):
                field = str(val["field"])
                if not field.startswith("world_state."):
                    issues.append(f"{path}.{side}: field must start with world_state.")
                    continue
                key = field.split(".", 1)[1]
                if allowed_keys is not None and key not in allowed_keys:
                    issues.append(
                        f"{path}.{side}: unknown world_state key {key!r}; allowed={sorted(allowed_keys)}"
                    )
            elif not isinstance(val, (int, bool)):
                issues.append(f"{path}.{side}: must be int / bool / field-ref")
    elif op in {"AND", "OR"}:
        operands = node.get("operands") or []
        if len(operands) < 2:
            issues.append(f"{path}: {op} requires >= 2 operands")
        for i, child in enumerate(operands):
            _walk(child, allowed_keys, issues, path=f"{path}.operands[{i}]")
    elif op == "NOT":
        child = node.get("operand")
        if child is None:
            issues.append(f"{path}: NOT requires 'operand'")
        else:
            _walk(child, allowed_keys, issues, path=f"{path}.operand")
    else:
        issues.append(f"{path}: unknown op {op!r}")
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_condition_tree.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/engine/condition_tree.py backend/tests/test_condition_tree.py
git commit -m "feat(engine): add condition tree serializer for generator-side DSL"
```

---

### Task 1.2: Round-trip property test against the existing DSL evaluator

**Files:**
- Test: `backend/tests/test_condition_tree_roundtrip.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_condition_tree_roundtrip.py
"""Round-trip: tree -> DSL string -> existing parser -> evaluator.

The generator-side tree must produce DSL that the unchanged runtime
evaluator (engine/condition_dsl.py) accepts and evaluates correctly.
"""
import pytest
from engine.condition_tree import serialize_to_dsl
from engine.condition_dsl import parse, evaluate


def _game_state(world_state: dict, location: str = "朝堂", day: int = 5,
                history: list[str] | None = None) -> dict:
    return {
        "world_state": world_state,
        "current_location": location,
        "world_clock": {"current_day": day},
        "player_action_history": history or [],
    }


@pytest.mark.parametrize("tree,state,expected", [
    (
        {"op": "func", "name": "time_after", "args": ["day_3"]},
        _game_state({}, day=5),
        True,
    ),
    (
        {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
        _game_state({"discovered": 1}),
        True,
    ),
    (
        {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
        _game_state({"discovered": 0}),
        False,
    ),
    (
        {
            "op": "AND",
            "operands": [
                {"op": "func", "name": "time_after", "args": ["day_3"]},
                {"op": "==", "left": {"field": "world_state.met_lead"}, "right": True},
            ],
        },
        _game_state({"met_lead": 1}, day=4),
        True,
    ),
    (
        {
            "op": "NOT",
            "operand": {"op": "func", "name": "location_is", "args": ["密室"]},
        },
        _game_state({}, location="朝堂"),
        True,
    ),
])
def test_tree_roundtrip(tree, state, expected):
    dsl = serialize_to_dsl(tree)
    parsed = parse(dsl)
    assert evaluate(parsed, state) is expected
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_condition_tree_roundtrip.py -v
```

Expected: all 5 parametrized cases PASS. If `evaluate()` signature differs, read `backend/engine/condition_dsl.py` and adjust the test's helper accordingly (the helper feeds the evaluator a game_state-shaped dict; field names must match what the evaluator reads — check `evaluate()` in condition_dsl.py before adjusting).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_condition_tree_roundtrip.py
git commit -m "test(engine): round-trip condition tree through DSL parser and evaluator"
```

---

## Phase 2 — Events data builder uses tree

### Task 2.1: Switch events_data_builder prompt to tree output

**Files:**
- Modify: `backend/services/events_data_builder.py` (prompt block at lines ~115-146)
- Test: `backend/tests/test_events_data_builder_tree.py`

- [ ] **Step 1: Read the existing prompt to anchor diffs**

```bash
sed -n '115,150p' backend/services/events_data_builder.py
```

Confirm the prompt currently asks for `"condition_dsl": "..."` strings.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_events_data_builder_tree.py
import json
import pytest
from services.events_data_builder import _validate_event
from schemas.events_data import EventDataEntry


CHAR_NAMES = {"林怀瑾", "苏婉", "陈默"}


def test_tree_input_is_accepted_and_serialized():
    """LLM emits structured condition_tree; validator serializes to DSL."""
    raw = {
        "id": "evt_001",
        "kind": "conditional",
        "summary": "时间到达 day_3 且玩家发现真相",
        "trigger": {
            "condition_tree": {
                "op": "AND",
                "operands": [
                    {"op": "func", "name": "time_after", "args": ["day_3"]},
                    {"op": "==", "left": {"field": "world_state.discovered"}, "right": True},
                ],
            },
            "probability": 0.8,
        },
        "effects": {"world_state_changes": {}, "spawn_clues": [], "npc_mood_changes": {}},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is False
    assert "time_after('day_3')" in entry.trigger["condition_dsl"]
    # Tree is preserved for audit.
    assert entry.trigger.get("condition_tree") is not None


def test_invalid_tree_disables_event_with_clear_reason():
    raw = {
        "id": "evt_002",
        "kind": "conditional",
        "summary": "bad tree",
        "trigger": {
            "condition_tree": {"op": "XOR", "operands": []},
            "probability": 0.5,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is True
    assert "XOR" in entry.disabled_reason or "unknown op" in entry.disabled_reason


def test_legacy_string_dsl_still_accepted():
    """Transition compat: pre-tree generations still parse if syntax is valid."""
    raw = {
        "id": "evt_003",
        "kind": "conditional",
        "summary": "legacy",
        "trigger": {
            "condition_dsl": "time_after('day_2')",
            "probability": 1.0,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is False


def test_legacy_bare_flag_string_disables_event():
    """The whole reason we're moving to trees: a bare flag string must fail."""
    raw = {
        "id": "evt_004",
        "kind": "conditional",
        "summary": "bad legacy",
        "trigger": {
            "condition_dsl": "world_state.x AND world_state.y",
            "probability": 1.0,
        },
        "effects": {},
        "rumors": [],
    }
    entry = _validate_event(raw, CHAR_NAMES)
    assert entry.disabled is True
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_events_data_builder_tree.py -v
```

Expected: first two tests FAIL — `_validate_event` currently only reads `condition_dsl` string.

- [ ] **Step 4: Modify the prompt block in `events_data_builder.py`**

Replace lines 115-146 with:

```python
请生成 {batch_n} 个不同类型的 events_data 条目，输出严格 JSON（不含 markdown）：
{{
  "events": [
    {{
      "id": "唯一字符串ID（统一前缀 evt_，例如 evt_001）",
      "kind": "conditional" 或 "npc_intent_driven",
      "summary": "事件简述",
      "trigger": {{
        // condition_tree 是结构化条件树（必填）。形态如下：
        //   时间/地点/动作判断: {{"op":"func","name":"time_after","args":["day_3"]}}
        //                       name 可选: "time_after" | "location_is" | "player_did"
        //   字段比较:          {{"op":"==","left":{{"field":"world_state.<key>"}},"right":true}}
        //                       op 可选: "==" "!=" ">=" "<=" ">" "<"
        //                       right 可以是 true/false/数字 或 {{"field":"world_state.<key>"}}
        //   组合:              {{"op":"AND","operands":[<节点>,<节点>,...]}}（>=2 项）
        //                       {{"op":"OR","operands":[...]}}
        //                       {{"op":"NOT","operand":<节点>}}
        // 若 kind=conditional: {{"condition_tree": {{...}}, "probability": 0.8}}
        // 若 kind=npc_intent_driven: {{"npc_name": "角色名", "condition_tree": {{...}}, "intent_payload": {{}}}}
      }},
      "effects": {{
        "world_state_changes": {{}},
        "spawn_clues": [],
        "npc_mood_changes": {{}}
      }},
      "rumors": [
        {{"text": "谣言内容", "knower_npcs": ["角色名"]}}
      ]
    }}
  ]
}}

condition_tree 正确示例（直接复制结构）：
  时间过 day_3：{{"op":"func","name":"time_after","args":["day_3"]}}
  发现真相标记：{{"op":"==","left":{{"field":"world_state.discovered_truth"}},"right":true}}
  两个条件都满足：{{"op":"AND","operands":[
    {{"op":"func","name":"time_after","args":["day_3"]}},
    {{"op":"==","left":{{"field":"world_state.met_lead"}},"right":true}}
  ]}}
  不在密室：{{"op":"NOT","operand":{{"op":"func","name":"location_is","args":["密室"]}}}}

禁止写法：不要输出 condition_dsl 字符串；不要写裸标记 "world_state.x AND world_state.y"；
不要用 AND(x,y) 函数式语法；不要在条件中使用未在 world_state 出现过的键。
npc_name 和 knower_npcs 必须使用上面角色列表中的名字。"""
```

- [ ] **Step 5: Modify `_validate_event` to consume tree**

Replace the validate block (lines 233-246) with:

```python
    # -- 1. validate condition (prefer tree, fall back to legacy string for compat) --
    from engine.condition_tree import (
        ConditionTreeError,
        serialize_to_dsl,
        validate_tree,
    )

    condition_tree = trigger.get("condition_tree")
    condition_dsl_str = trigger.get("condition_dsl", "")

    if isinstance(condition_tree, dict):
        tree_issues = validate_tree(condition_tree)
        if tree_issues:
            disabled = True
            disabled_reason = f"condition_tree_invalid: {tree_issues[0]}"
            logger.warning(
                "events_data_tree_invalid",
                event_id=eid,
                issues=tree_issues,
            )
        else:
            try:
                condition_dsl_str = serialize_to_dsl(condition_tree)
                trigger["condition_dsl"] = condition_dsl_str
                # condition_tree retained in trigger for audit.
            except ConditionTreeError as exc:
                disabled = True
                disabled_reason = f"condition_tree_serialize_error: {exc}"
                logger.warning(
                    "events_data_tree_serialize_error",
                    event_id=eid,
                    error=str(exc),
                )
    else:
        # Legacy path: validate the string directly.
        try:
            dsl_parse(condition_dsl_str)
        except (ConditionDSLParseError, Exception) as exc:
            disabled = True
            disabled_reason = f"dsl_parse_error: {exc}"
            logger.warning(
                "events_data_dsl_parse_error",
                event_id=eid,
                dsl=condition_dsl_str,
                error=str(exc),
            )
```

- [ ] **Step 6: Run test**

```bash
cd backend && python -m pytest tests/test_events_data_builder_tree.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 7: Run existing builder tests to verify no regression**

```bash
cd backend && python -m pytest tests/test_events_data_builder.py tests/test_world_simulator_events_data.py -v
```

Expected: PASS (legacy `condition_dsl` string path still works).

- [ ] **Step 8: Commit**

```bash
git add backend/services/events_data_builder.py backend/tests/test_events_data_builder_tree.py
git commit -m "feat(events): builder consumes condition_tree, serializes to DSL"
```

---

## Phase 3 — Endings full schema

### Task 3.1: Expand `_generate_endings_v2` to require full runtime shape

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py:2467-2555`
- Test: `backend/tests/test_endings_full_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_endings_full_schema.py
import pytest
from services.world_creator_agent_v2 import _validate_ending_payload


def test_validate_complete_ending_passes():
    ending = {
        "ending_type": "good",
        "title": "真相大白",
        "description": "玩家揭开真相，正义得到伸张",
        "soft_conditions": "玩家在 day_5 前发现关键线索",
        "priority": 1,
        "quality": "best",
    }
    assert _validate_ending_payload(ending) == []


def test_missing_ending_type_returns_issue():
    ending = {
        "title": "真相大白",
        "description": "...",
        "soft_conditions": "...",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("ending_type" in i for i in issues)


def test_invalid_ending_type_enum():
    ending = {
        "ending_type": "amazing",  # not in enum
        "title": "t",
        "description": "d",
        "soft_conditions": "s",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("ending_type" in i and "amazing" in i for i in issues)


def test_missing_soft_conditions_returns_issue():
    ending = {
        "ending_type": "good",
        "title": "t",
        "description": "d",
        "priority": 1,
        "quality": "best",
    }
    issues = _validate_ending_payload(ending)
    assert any("soft_conditions" in i for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_endings_full_schema.py -v
```

Expected: `ImportError: cannot import _validate_ending_payload`.

- [ ] **Step 3: Add validator and expand generator in `world_creator_agent_v2.py`**

Insert this helper at module level (above `_generate_endings_v2`, e.g. near the existing private helpers around line 2440):

```python
_ENDING_TYPE_ENUM = {"good", "normal", "bad", "hidden", "timeout"}
_ENDING_REQUIRED = ("ending_type", "title", "description", "soft_conditions", "priority")


def _validate_ending_payload(ending: dict) -> list[str]:
    """Return human-readable issues for a single ending dict; empty list = OK."""
    issues: list[str] = []
    if not isinstance(ending, dict):
        return ["ending is not a dict"]
    for field in _ENDING_REQUIRED:
        if field not in ending or ending.get(field) in (None, ""):
            issues.append(f"missing required field: {field}")
    et = ending.get("ending_type")
    if et and et not in _ENDING_TYPE_ENUM:
        issues.append(f"ending_type {et!r} not in {sorted(_ENDING_TYPE_ENUM)}")
    if "priority" in ending and not isinstance(ending["priority"], int):
        issues.append("priority must be int")
    return issues
```

Then rewrite the system prompt and post-processing inside `_generate_endings_v2` (current lines 2480-2551). Replace the system string and the post-processing loop:

```python
        system = (
            "你是剧本结局设计师。给剧本设计 3-5 个不同的结局，覆盖好/中/坏多种走向。\n"
            "输出严格 JSON（不含 markdown 代码块），结构：\n"
            '{\n'
            '  "endings": [\n'
            '    {\n'
            '      "ending_type": "good | normal | bad | hidden | timeout",\n'
            '      "title": "结局标题（玩家可见）",\n'
            '      "description": "结局完整描述（玩家可见，>=80 字）",\n'
            '      "soft_conditions": "用自然语言描述判定条件，供运行时 AI 主持人比对玩家走向",\n'
            '      "priority": 整数（数值越大越优先匹配，建议 0-10）,\n'
            '      "quality": "best | good | neutral | bad | worst"\n'
            '    }\n'
            '  ]\n'
            "}\n"
            "硬约束：\n"
            "- ending_type 必须从枚举里选；不要发明新类型。\n"
            "- soft_conditions 用一句话写明判定依据，能让 AI 主持人判断玩家是否走向此结局。\n"
            "- 不要遗漏任何字段；缺字段会导致运行时报错。"
        )
```

And replace the post-processing block (currently lines 2538-2551) with:

```python
            data = _extract_json_from_text(text) or {}
            raw_endings = data.get("endings") or []
            result: list[dict] = []
            for e in raw_endings:
                if not isinstance(e, dict):
                    continue
                normalized = {
                    "ending_type": str(e.get("ending_type") or "").strip(),
                    "title": str(e.get("title") or e.get("name") or "").strip(),
                    "description": str(e.get("description") or "").strip(),
                    "soft_conditions": str(e.get("soft_conditions") or e.get("condition") or "").strip(),
                    "priority": int(e.get("priority")) if isinstance(e.get("priority"), (int, float)) else 0,
                    "quality": str(e.get("quality") or "neutral").strip(),
                    # Keep `name` for backward-compat with admin UI which still
                    # reads it; identical to title.
                    "name": str(e.get("title") or e.get("name") or "").strip(),
                }
                issues = _validate_ending_payload(normalized)
                if issues:
                    logger.warning(
                        "ending_validation_failed",
                        title=normalized.get("title"),
                        issues=issues,
                    )
                    continue
                result.append(normalized)
            if not result:
                self._stage_errors["endings"] = ValueError("no valid endings after validation")
            return result
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_endings_full_schema.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run existing v2 generator tests for regression**

```bash
cd backend && python -m pytest tests/test_world_creator_v2_entry.py tests/test_world_critic_shape.py -v
```

Expected: PASS. If a test asserts the old 4-field ending shape, update it to expect the new shape — the old shape was wrong.

- [ ] **Step 6: Commit**

```bash
git add backend/services/world_creator_agent_v2.py backend/tests/test_endings_full_schema.py
git commit -m "feat(endings): require full runtime shape at generator output"
```

---

### Task 3.2: Add stage-level retry on endings validation failure

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py` (in `_generate_endings_v2`)

- [ ] **Step 1: Wrap the generate call in a retry-with-feedback loop**

Replace the `with_transient_retry` wrapper inside `_generate_endings_v2` with explicit retry that injects validation errors back into the prompt. Find the existing `try: text = await with_transient_retry(...)` block (~line 2526) and replace with:

```python
        last_issues: list[str] = []
        for attempt in range(3):
            repair_note = ""
            if last_issues:
                repair_note = (
                    "\n## 上次输出的问题\n"
                    + "\n".join(f"- {i}" for i in last_issues[:10])
                    + "\n请这次输出严格满足 schema。"
                )
            try:
                text = await _collect_stream_text(
                    self.llm,
                    system=system + repair_note,
                    messages=[{"role": "user", "content": user_content}],
                    max_tokens=2048,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("script_endings_v2_call_failed", attempt=attempt, error=str(exc))
                if attempt == 2:
                    self._stage_errors["endings"] = exc
                    return []
                continue

            data = _extract_json_from_text(text) or {}
            raw_endings = data.get("endings") or []
            result: list[dict] = []
            current_issues: list[str] = []
            for idx, e in enumerate(raw_endings):
                if not isinstance(e, dict):
                    current_issues.append(f"endings[{idx}] is not a dict")
                    continue
                normalized = {
                    "ending_type": str(e.get("ending_type") or "").strip(),
                    "title": str(e.get("title") or e.get("name") or "").strip(),
                    "description": str(e.get("description") or "").strip(),
                    "soft_conditions": str(e.get("soft_conditions") or e.get("condition") or "").strip(),
                    "priority": int(e.get("priority")) if isinstance(e.get("priority"), (int, float)) else 0,
                    "quality": str(e.get("quality") or "neutral").strip(),
                    "name": str(e.get("title") or e.get("name") or "").strip(),
                }
                issues = _validate_ending_payload(normalized)
                if issues:
                    current_issues.extend(f"endings[{idx}]: {i}" for i in issues)
                    continue
                result.append(normalized)
            if result and not current_issues:
                return result
            if result and len(result) >= 3:
                # Partial success: enough valid endings to ship; log the bad ones.
                logger.warning(
                    "script_endings_v2_partial",
                    valid=len(result),
                    dropped_issues=current_issues[:5],
                )
                return result
            last_issues = current_issues or ["no endings produced"]
            logger.warning(
                "script_endings_v2_retry",
                attempt=attempt,
                issues=last_issues[:5],
            )

        self._stage_errors["endings"] = ValueError(f"endings generation failed: {last_issues}")
        return []
```

- [ ] **Step 2: Add a test that exercises retry-with-feedback**

```python
# Append to backend/tests/test_endings_full_schema.py
import pytest
from unittest.mock import AsyncMock, patch
from services.world_creator_agent_v2 import WorldCreatorAgentV2  # adjust import to match real symbol


@pytest.mark.asyncio
async def test_endings_retry_injects_issues_into_prompt(monkeypatch):
    """First call returns malformed endings, second call sees the failure list."""
    calls: list[str] = []

    async def fake_collect(_llm, *, system, messages, max_tokens):
        calls.append(system)
        if len(calls) == 1:
            return '{"endings":[{"name":"x","description":"d","condition":"c","quality":"good"}]}'
        return (
            '{"endings":[{"ending_type":"good","title":"t","description":"d",'
            '"soft_conditions":"s","priority":1,"quality":"good"}]}'
        )

    monkeypatch.setattr(
        "services.world_creator_agent_v2._collect_stream_text",
        fake_collect,
    )
    # Build a minimal agent stub; only _generate_endings_v2 is exercised.
    agent = WorldCreatorAgentV2.__new__(WorldCreatorAgentV2)
    agent.llm = object()
    agent._stage_errors = {}
    agent._last_ip_pack = None
    agent._fidelity_mode = "none"
    agent._make_retry_logger = lambda _name: (lambda **_: None)

    from services.research_pack_builder import ResearchPack  # adjust if different
    pack = ResearchPack.model_validate({"ip_canon": {"ip_name": "", "must_have_characters": []}})

    result = await agent._generate_endings_v2(
        world_data={"era": "", "genre": ""},
        outline="",
        script_base={"name": "test", "script_setting": ""},
        characters=[],
        research_pack=pack,
    )
    assert len(result) == 1
    assert len(calls) == 2
    # Second prompt must include feedback about missing required fields.
    assert "missing required field" in calls[1] or "ending_type" in calls[1]
```

If `ResearchPack` import path differs, adjust based on actual location. The point is to assert retry happens with feedback.

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_endings_full_schema.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/world_creator_agent_v2.py backend/tests/test_endings_full_schema.py
git commit -m "feat(endings): stage-level retry with validation feedback"
```

---

## Phase 4 — Playable identity sync at generator

### Task 4.1: Inject playable names into world setting prompt; validate cross-ref

**Files:**
- Modify: `backend/services/world_creator_agent.py` and/or `world_creator_agent_v2.py` (the stage that writes `base_setting`)
- Test: `backend/tests/test_playable_identity_sync.py`

- [ ] **Step 1: Locate the world-setting stage**

```bash
grep -n "base_setting\|你叫" backend/services/world_creator_agent_v2.py | head -20
grep -n "_run_world\|_generate_world" backend/services/world_creator_agent_v2.py | head -20
```

Identify which method writes `base_setting`. In v2 it is part of the world-data stage (look for the prompt construction that produces world setting text). Confirm whether it runs before or after the `characters` and `playable` stages.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_playable_identity_sync.py
from services.world_creator_agent_v2 import _validate_player_identity_in_setting


def test_setting_references_known_playable_name():
    base_setting = "你叫林怀瑾，是工作室的核心剪辑师。"
    playable_names = ["林怀瑾", "苏婉"]
    assert _validate_player_identity_in_setting(base_setting, playable_names) == []


def test_setting_references_unknown_name_returns_issue():
    base_setting = "你叫张三，是工作室的实习生。"
    playable_names = ["林怀瑾", "苏婉"]
    issues = _validate_player_identity_in_setting(base_setting, playable_names)
    assert any("张三" in i for i in issues)


def test_setting_with_no_player_reference_passes():
    """If `base_setting` does not address the player by name, no constraint applies."""
    base_setting = "工作室位于上海陆家嘴某幢甲级写字楼的 32 层。"
    playable_names = ["林怀瑾"]
    assert _validate_player_identity_in_setting(base_setting, playable_names) == []


def test_setting_with_multiple_player_refs_all_must_be_known():
    base_setting = "你叫林怀瑾。在某些路径下，你也可以扮演苏婉。"
    issues = _validate_player_identity_in_setting(base_setting, ["林怀瑾"])
    assert any("苏婉" in i for i in issues)
```

- [ ] **Step 3: Implement the validator helper**

Add to `backend/services/world_creator_agent_v2.py` (module level):

```python
import re

_PLAYER_NAME_RE = re.compile(r"你叫(?P<name>[一-鿿A-Za-z0-9_·]{2,12})")


def _validate_player_identity_in_setting(
    base_setting: str,
    playable_names: list[str],
) -> list[str]:
    """If base_setting addresses the player by name (你叫 X), X must be in
    the playable name list. Returns human-readable issues; empty = OK.
    """
    issues: list[str] = []
    if not base_setting:
        return issues
    names_in_setting = {m.group("name") for m in _PLAYER_NAME_RE.finditer(base_setting)}
    allowed = set(playable_names)
    for name in names_in_setting:
        if name not in allowed:
            issues.append(
                f"base_setting references player name {name!r} which is not in "
                f"playable roster: {sorted(allowed)}"
            )
    return issues
```

- [ ] **Step 4: Wire validator into the v2 pipeline**

Inside the v2 generator (after both `playable` and world-data stages have completed — find the post-playable hook), call:

```python
identity_issues = _validate_player_identity_in_setting(
    world_data.get("base_setting", ""),
    [p.get("name", "") for p in (self._last_playable or [])],
)
if identity_issues:
    logger.warning("playable_identity_mismatch", issues=identity_issues)
    # Regenerate world setting once with explicit feedback.
    repair_note = (
        "上次的 base_setting 提到了不在可玩角色列表中的玩家名字。"
        "可玩角色名单：" + ", ".join(p.get("name", "") for p in self._last_playable)
        + "。请只用列表中的某一个名字作为玩家身份。"
    )
    # Call the world-data stage again with repair_note. Use the existing
    # generation_prompt_builder.build_world_prompt with repair_note kwarg.
    # If the v2 pipeline does not allow re-entry to one stage, set
    # self._needs_human_review = True and raise to abort publish.
```

The exact re-entry path depends on v2 internals. If `_run_world_data` exists as a discrete stage, call it again. If not, escalate to `needs_human_review` and let publish_service refuse to publish.

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_playable_identity_sync.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/world_creator_agent_v2.py backend/tests/test_playable_identity_sync.py
git commit -m "feat(generator): validate playable identity cross-reference in world setting"
```

---

## Phase 5 — Strict generation schema gate at publish

### Task 5.1: Central schema validator and publish-time gate

**Files:**
- Create: `backend/services/generation_schema.py`
- Modify: `backend/services/publish_service.py` (publish_world / publish_script entrypoints)
- Test: `backend/tests/test_generation_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_generation_schema.py
import pytest
from services.generation_schema import (
    validate_script_payload,
    validate_world_payload,
    SchemaValidationError,
)


def test_valid_script_passes():
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [
            {
                "id": "evt_001",
                "kind": "conditional",
                "summary": "...",
                "trigger": {"condition_dsl": "time_after('day_3')", "probability": 0.8},
                "effects": {},
                "rumors": [],
            }
        ],
        "endings_data": [
            {
                "ending_type": "good",
                "title": "t",
                "description": "d" * 80,
                "soft_conditions": "s",
                "priority": 1,
                "quality": "best",
            },
            {
                "ending_type": "bad",
                "title": "t2",
                "description": "d" * 80,
                "soft_conditions": "s",
                "priority": 0,
                "quality": "worst",
            },
        ],
    }
    validate_script_payload(payload)  # no exception


def test_script_missing_required_ending_field_raises():
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [],
        "endings_data": [
            {
                "title": "t",
                "description": "d",
                "quality": "best",
            }
        ],
    }
    with pytest.raises(SchemaValidationError) as exc:
        validate_script_payload(payload)
    assert "ending_type" in str(exc.value)


def test_script_with_disabled_event_raises():
    """A disabled event in published content means generation silently dropped logic."""
    payload = {
        "name": "test",
        "script_setting": "...",
        "script_type": "mystery",
        "events_data": [
            {
                "id": "evt_001",
                "kind": "conditional",
                "summary": "...",
                "trigger": {"condition_dsl": "bogus"},
                "effects": {},
                "rumors": [],
                "disabled": True,
                "disabled_reason": "dsl_parse_error: ...",
            }
        ],
        "endings_data": [
            {
                "ending_type": "good", "title": "t", "description": "d"*80,
                "soft_conditions": "s", "priority": 0, "quality": "best",
            },
            {
                "ending_type": "bad", "title": "t2", "description": "d"*80,
                "soft_conditions": "s", "priority": 0, "quality": "worst",
            },
        ],
    }
    with pytest.raises(SchemaValidationError) as exc:
        validate_script_payload(payload)
    assert "disabled" in str(exc.value)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_generation_schema.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `generation_schema.py`**

```python
# backend/services/generation_schema.py
"""Strict JSON Schema validation at the publish boundary.

The intent is to make schema violations loud at publish time rather than
silently produce a degraded experience at runtime. Validation runs after
the generator finishes and before the draft is promoted to a published
world/script row.
"""

from __future__ import annotations

from typing import Any

import jsonschema

_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "kind", "summary", "trigger", "effects"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "kind": {"enum": ["conditional", "npc_intent_driven"]},
        "summary": {"type": "string", "minLength": 1},
        "trigger": {"type": "object"},
        "effects": {"type": "object"},
        "rumors": {"type": "array"},
        "disabled": {"type": "boolean"},
    },
}

_ENDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["ending_type", "title", "description", "soft_conditions", "priority"],
    "properties": {
        "ending_type": {"enum": ["good", "normal", "bad", "hidden", "timeout"]},
        "title": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 20},
        "soft_conditions": {"type": "string", "minLength": 1},
        "priority": {"type": "integer"},
        "quality": {"type": "string"},
        "name": {"type": "string"},  # backward-compat mirror of title
    },
}

_SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "events_data", "endings_data"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "script_setting": {"type": "string"},
        "script_type": {"type": "string"},
        "events_data": {"type": "array", "items": _EVENT_SCHEMA, "minItems": 3},
        "endings_data": {"type": "array", "items": _ENDING_SCHEMA, "minItems": 2},
    },
}

_WORLD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "base_setting"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "base_setting": {"type": "string", "minLength": 1},
        "free_setting": {"type": "string"},
    },
}


class SchemaValidationError(ValueError):
    """Raised when payload fails the publish-boundary schema."""


def _format_jsonschema_error(err: jsonschema.ValidationError) -> str:
    path = ".".join(str(p) for p in err.absolute_path) or "$"
    return f"{path}: {err.message}"


def validate_script_payload(payload: dict[str, Any]) -> None:
    """Raises SchemaValidationError on violation; returns None on success."""
    errors: list[str] = []
    for err in jsonschema.Draft202012Validator(_SCRIPT_SCHEMA).iter_errors(payload):
        errors.append(_format_jsonschema_error(err))

    # Reject scripts containing any `disabled` event — disabled means the
    # generator produced something the runtime cannot execute.
    for idx, event in enumerate(payload.get("events_data") or []):
        if isinstance(event, dict) and event.get("disabled"):
            errors.append(
                f"events_data[{idx}].disabled is true: "
                f"{event.get('disabled_reason') or '(no reason)'}"
            )

    if errors:
        raise SchemaValidationError("; ".join(errors))


def validate_world_payload(payload: dict[str, Any]) -> None:
    errors: list[str] = []
    for err in jsonschema.Draft202012Validator(_WORLD_SCHEMA).iter_errors(payload):
        errors.append(_format_jsonschema_error(err))
    if errors:
        raise SchemaValidationError("; ".join(errors))
```

- [ ] **Step 4: Confirm `jsonschema` is in dependencies**

```bash
grep -E "^jsonschema" backend/pyproject.toml || echo "missing"
```

If missing, add to `[project.dependencies]` in `backend/pyproject.toml`:

```toml
"jsonschema>=4.21",
```

Then:

```bash
cd backend && pip install -e ".[dev]"
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_generation_schema.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Wire validator into `publish_service.py`**

Find the world/script publish entrypoints (line ~338 and ~441 per earlier grep). Just before the draft → published row promotion, call:

```python
from services.generation_schema import (
    SchemaValidationError,
    validate_script_payload,
    validate_world_payload,
)

# In publish_world:
try:
    validate_world_payload({
        "name": draft.name,
        "base_setting": draft.base_setting,
        "free_setting": draft.free_setting or "",
    })
except SchemaValidationError as exc:
    logger.warning("publish_world_schema_violation", draft_id=str(draft.id), error=str(exc))
    raise HTTPException(status_code=400, detail=f"world schema invalid: {exc}")

# In publish_script:
try:
    validate_script_payload({
        "name": draft.name,
        "script_setting": draft.script_setting,
        "script_type": draft.script_type,
        "events_data": draft.events_data or [],
        "endings_data": draft.endings_data or [],
    })
except SchemaValidationError as exc:
    logger.warning("publish_script_schema_violation", draft_id=str(draft.id), error=str(exc))
    raise HTTPException(status_code=400, detail=f"script schema invalid: {exc}")
```

(Match the existing logging style and HTTPException import already in `publish_service.py`.)

- [ ] **Step 7: Run full backend tests**

```bash
cd backend && python -m pytest tests/ -v 2>&1 | tail -40
```

Expected: PASS. If any test publishes a script with disabled events or skinny endings, it represents the old broken contract — update the test fixture to satisfy the new schema.

- [ ] **Step 8: Commit**

```bash
git add backend/services/generation_schema.py backend/services/publish_service.py \
        backend/tests/test_generation_schema.py backend/pyproject.toml
git commit -m "feat(publish): strict schema validation at world/script publish boundary"
```

---

## Phase 6 — Model capability matrix

### Task 6.1: Define and wire capability lookup

**Files:**
- Create: `backend/llm/model_capabilities.py`
- Test: `backend/tests/test_model_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_model_capabilities.py
from llm.model_capabilities import StructuredOutputMode, capability_for


def test_deepseek_v4_pro_uses_json_object():
    cap = capability_for("deepseek-v4-pro")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_claude_uses_forced_tool():
    cap = capability_for("claude-sonnet-4-6")
    assert cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL


def test_gpt_uses_forced_tool():
    cap = capability_for("gpt-4o")
    assert cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL


def test_unknown_model_default_to_tool_use_auto():
    cap = capability_for("totally-new-model-xyz")
    assert cap.structured_output_mode == StructuredOutputMode.TOOL_USE_AUTO


def test_grok_thinking_uses_json_object():
    cap = capability_for("grok-4.20-multi-agent-console")
    # Reasoning models with thinking output behave like deepseek-v4-pro.
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_qwen_thinking_uses_json_object():
    cap = capability_for("qwen3.7-max-preview-thinking")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT
```

- [ ] **Step 2: Implement `model_capabilities.py`**

```python
# backend/llm/model_capabilities.py
"""Per-model structured-output capability matrix.

Maps a model_id (as bound in the model slot management table) to the
structured-output mechanism that gives the most reliable JSON / tool_use
output for that model.

Heuristics:
- Reasoning / thinking models (DeepSeek V4 Pro, Qwen thinking variants,
  Grok multi-agent-console, etc.) often emit reasoning text before the
  tool call; tool_choice=auto is unreliable. Prefer JSON object mode.
- Claude and GPT mainline models handle tool_choice=forced cleanly and
  give the strictest schema adherence via forced tool_use.
- Anything else: tool_choice=auto with tool_use (legacy behavior).

Lookup is by lowercase prefix match against curated patterns. Unknown
models fall back to TOOL_USE_AUTO.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StructuredOutputMode(str, Enum):
    JSON_OBJECT = "json_object"     # response_format={"type":"json_object"}
    FORCED_TOOL = "forced_tool"     # tool_choice={"type":"function","function":{"name":...}}
    TOOL_USE_AUTO = "tool_use_auto"  # tool_choice="auto"


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    structured_output_mode: StructuredOutputMode


_REASONING_PREFIXES = (
    "deepseek-v4",
    "deepseek-r1",
    "deepseek-r2",
    "qwen3",
    "qwen-3",
    "grok-4.20-multi-agent",
    "o1",
    "o3",
)

_FORCED_TOOL_PREFIXES = (
    "claude-",
    "gpt-4",
    "gpt-5",
)


def capability_for(model_id: str) -> ModelCapability:
    """Look up capability for a model id. Always returns a value."""
    mid = (model_id or "").lower().strip()
    if any(mid.startswith(p) for p in _REASONING_PREFIXES):
        return ModelCapability(model_id, StructuredOutputMode.JSON_OBJECT)
    if any(mid.startswith(p) for p in _FORCED_TOOL_PREFIXES):
        return ModelCapability(model_id, StructuredOutputMode.FORCED_TOOL)
    return ModelCapability(model_id, StructuredOutputMode.TOOL_USE_AUTO)
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_model_capabilities.py -v
```

Expected: all 6 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/llm/model_capabilities.py backend/tests/test_model_capabilities.py
git commit -m "feat(llm): per-model structured output capability matrix"
```

---

## Phase 7 — DeepSeek provider extension

### Task 7.1: Add `tool_choice` parameter

**Files:**
- Modify: `backend/llm/deepseek.py`
- Modify: `backend/llm/openai_compatible.py` (mirror the change — other providers using the same OpenAI shape)
- Modify: `backend/llm/router.py` (forward the new param)
- Modify: `backend/llm/base.py` (update protocol signature)
- Test: `backend/tests/test_deepseek_tool_choice.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_deepseek_tool_choice.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from llm.deepseek import DeepSeekProvider


@pytest.mark.asyncio
async def test_tool_choice_forced_forwards_to_openai_call():
    captured_kwargs: dict = {}

    class FakeStream:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return FakeStream()

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    async for _ in provider.stream_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "foo", "input_schema": {"type": "object"}}],
        tool_choice={"type": "function", "function": {"name": "foo"}},
    ):
        pass

    assert captured_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "foo"},
    }


@pytest.mark.asyncio
async def test_tool_choice_default_is_auto():
    captured_kwargs: dict = {}

    class FakeStream:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise StopAsyncIteration

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return FakeStream()

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    async for _ in provider.stream_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "foo", "input_schema": {"type": "object"}}],
    ):
        pass

    assert captured_kwargs["tool_choice"] == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_deepseek_tool_choice.py -v
```

Expected: TypeError — `stream_with_tools` does not accept `tool_choice`.

- [ ] **Step 3: Modify `deepseek.py` `stream_with_tools`**

Replace the method signature and the tool-config block (lines 30-52):

```python
    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        response_format: dict | None = None,
        tool_choice: str | dict | None = None,
    ) -> AsyncIterator[dict]:
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [_convert_tool_to_openai(t) for t in tools]
            kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        if response_format:
            kwargs["response_format"] = response_format
        stream = await self.client.chat.completions.create(**kwargs)
```

- [ ] **Step 4: Mirror in `openai_compatible.py`**

Apply the same change at `backend/llm/openai_compatible.py:65-90`.

- [ ] **Step 5: Update `LLMProvider` protocol in `base.py`**

Add `tool_choice` to the `stream_with_tools` signature (with default None).

- [ ] **Step 6: Update `router.py` to forward `tool_choice`**

In `backend/llm/router.py` `stream_with_tools` (around line 124-235), add `tool_choice` parameter and forward to provider call (around line 234).

- [ ] **Step 7: Run tests**

```bash
cd backend && python -m pytest tests/test_deepseek_tool_choice.py tests/test_llm_router*.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/llm/deepseek.py backend/llm/openai_compatible.py \
        backend/llm/router.py backend/llm/base.py \
        backend/tests/test_deepseek_tool_choice.py
git commit -m "feat(llm): add tool_choice param to provider stream_with_tools"
```

---

### Task 7.2: Add `stream_json` method for native JSON mode

**Files:**
- Modify: `backend/llm/deepseek.py`
- Modify: `backend/llm/base.py`
- Modify: `backend/llm/router.py`
- Test: `backend/tests/test_deepseek_stream_json.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_deepseek_stream_json.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from llm.deepseek import DeepSeekProvider


class FakeChunk:
    def __init__(self, content=None, usage=None):
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice]
        self.usage = usage


@pytest.mark.asyncio
async def test_stream_json_emits_text_delta_and_usage():
    chunks = [
        FakeChunk(content="{"),
        FakeChunk(content='"a":1'),
        FakeChunk(content="}"),
        FakeChunk(usage=MagicMock(prompt_tokens=10, completion_tokens=5)),
    ]

    async def fake_iter():
        for c in chunks:
            yield c

    provider = DeepSeekProvider(model="deepseek-v4-pro")
    provider.client = MagicMock()

    async def fake_create(**_kwargs):
        return fake_iter()

    provider.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    events = []
    async for ev in provider.stream_json(
        messages=[{"role": "user", "content": "hi"}],
        system="produce JSON",
    ):
        events.append(ev)

    text_events = [e for e in events if e["type"] == "text_delta"]
    usage_events = [e for e in events if e["type"] == "usage"]
    assert "".join(e["text"] for e in text_events) == '{"a":1}'
    assert len(usage_events) == 1
    assert usage_events[0]["input_tokens"] == 10
```

- [ ] **Step 2: Implement `stream_json` in `deepseek.py`**

Append a new method to `DeepSeekProvider`:

```python
    async def stream_json(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> AsyncIterator[dict]:
        """Native JSON object mode — no tool plumbing. The model must produce a
        single JSON object as plain text; the caller parses it.
        """
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        stream = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=oai_messages,
            stream=True,
            stream_options={"include_usage": True},
            response_format={"type": "json_object"},
        )

        usage = None
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            for choice in getattr(chunk, "choices", []) or []:
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "text_delta", "text": content}

        yield {
            "type": "usage",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }
```

- [ ] **Step 3: Add to `LLMProvider` protocol and router**

In `base.py`, add the abstract method. In `router.py`, add a `stream_json` wrapper similar to `stream_with_tools` (capture model_id, forward through slot).

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_deepseek_stream_json.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/llm/deepseek.py backend/llm/base.py backend/llm/router.py \
        backend/tests/test_deepseek_stream_json.py
git commit -m "feat(llm): add stream_json native JSON mode to providers"
```

---

### Task 7.3: Expose current model id on router

**Files:**
- Modify: `backend/llm/router.py`

- [ ] **Step 1: Add `current_model_for_purpose()` method**

Add a method on `LLMRouter` that returns the model_id bound to a given purpose slot (e.g. `game_main`). Look at how slots resolve in `services/model_management.py` to mirror the same lookup.

```python
def current_model_for_purpose(self, purpose: str) -> str:
    """Return the model_id currently bound to `purpose` slot, or empty string."""
    # Reuse existing slot resolution logic; specifically the path that
    # picks which provider+model_id will serve the next call for purpose.
    # If the router caches this per-call, also expose it.
    ...
```

If the router currently resolves slot → provider per-call without caching the model_id, add a small helper that walks the same lookup (likely something like `model_slot_bindings` join). Reuse existing private helpers; do not duplicate slot logic.

- [ ] **Step 2: Add a smoke test against an in-memory slot binding**

This test wires up a minimal in-memory router config (or mocks the slot lookup) to assert `current_model_for_purpose("game_main")` returns the configured model.

- [ ] **Step 3: Commit**

```bash
git add backend/llm/router.py backend/tests/test_llm_router*.py
git commit -m "feat(llm): expose current model id per purpose slot"
```

---

## Phase 8 — Director uses capability matrix

### Task 8.1: Capability-based dispatch + prompt-mutation retry

**Files:**
- Modify: `backend/engine/director_agent.py`
- Modify: `backend/config.py` (remove `director_prefer_json_mode`)
- Test: `backend/tests/test_director_capability_routing.py`

- [ ] **Step 1: Read existing director_agent.py to anchor diffs**

```bash
sed -n '50,80p' backend/engine/director_agent.py
sed -n '250,320p' backend/engine/director_agent.py
```

Confirm constructor takes `prefer_json_mode` and `run()` dispatches by that flag.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_director_capability_routing.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from engine.director_agent import DirectorAgent, DirectorParseError
from engine.state_manager import GameState


def _state():
    return GameState(
        session_id="t",
        round_number=1,
        current_location="A",
        world_clock={"current_day": 1},
        player_action_history=[],
        case_board={},
        world_state={},
    )


@pytest.mark.asyncio
async def test_reasoning_model_uses_json_mode_path():
    """When game_main is bound to deepseek-v4-pro, Director should call stream_json,
    not stream_with_tools.
    """
    router = MagicMock()
    router.current_model_for_purpose = MagicMock(return_value="deepseek-v4-pro")
    json_calls = []

    async def stream_json(messages, system, max_tokens=2048):
        json_calls.append((messages, system))
        yield {"type": "text_delta", "text": '{"scene_direction":"...","involved_npcs":[]}'}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    router.stream_json = stream_json
    router.stream_with_tools = AsyncMock()

    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data={"base_setting": "x"},
        user_input="look around",
        game_mode="script",
    )
    assert result.scene_direction
    assert len(json_calls) == 1
    router.stream_with_tools.assert_not_called()


@pytest.mark.asyncio
async def test_strong_tool_model_uses_forced_tool():
    """When game_main is bound to claude-*, Director should call stream_with_tools
    with tool_choice forced to director_decide.
    """
    router = MagicMock()
    router.current_model_for_purpose = MagicMock(return_value="claude-sonnet-4-6")
    captured = {}

    async def stream_with_tools(messages, tools, system, tool_choice=None, **kw):
        captured["tool_choice"] = tool_choice
        yield {"type": "tool_use", "name": "director_decide",
               "input": {"scene_direction": "x", "involved_npcs": []}}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    router.stream_with_tools = stream_with_tools

    agent = DirectorAgent(router)
    await agent.run(
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data={"base_setting": "x"},
        user_input="hi",
        game_mode="script",
    )
    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "director_decide"},
    }


@pytest.mark.asyncio
async def test_prompt_mutation_on_retry():
    """Failed parse → next attempt appends explicit error feedback to system."""
    router = MagicMock()
    router.current_model_for_purpose = MagicMock(return_value="deepseek-v4-pro")
    systems_seen: list[str] = []

    call_count = {"n": 0}

    async def stream_json(messages, system, max_tokens=2048):
        systems_seen.append(system)
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield {"type": "text_delta", "text": "not json at all, just reasoning"}
        else:
            yield {"type": "text_delta", "text": '{"scene_direction":"x","involved_npcs":[]}'}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    router.stream_json = stream_json
    agent = DirectorAgent(router)
    result = await agent.run(
        game_state=_state(),
        recent_messages=[],
        context_summary=None,
        world_data={"base_setting": "x"},
        user_input="hi",
        game_mode="script",
    )
    assert result.scene_direction == "x"
    assert len(systems_seen) == 2
    # Second system message must carry feedback about the previous failure.
    assert "上一次" in systems_seen[1] or "previous" in systems_seen[1] or "JSON" in systems_seen[1]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_director_capability_routing.py -v
```

Expected: FAIL — no capability dispatch yet.

- [ ] **Step 4: Implement capability-based dispatch in `director_agent.py`**

Replace the `__init__` and `run` method:

```python
from llm.model_capabilities import StructuredOutputMode, capability_for


class DirectorAgent:
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router
        # prefer_json_mode is no longer a config flag — capability decides.

    async def run(
        self,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        user_input: str,
        game_mode: str,
        memory_context: str = "",
        authors_note: str | None = None,
        recall_fn: Callable[[str, int], list[dict]] | None = None,
        script_type: str = "",
    ) -> DirectorResult:
        base_system = build_director_system(
            base_setting=world_data.get("base_setting", ""),
            script_setting=world_data.get("script_setting", ""),
            npc_descriptions=world_data.get("npc_descriptions", ""),
            ending_conditions=world_data.get("ending_conditions", ""),
            game_mode=game_mode,
            memory_context=memory_context,
            script_type=script_type,
        )
        if authors_note:
            base_system = "\n\n".join([base_system, f"## Author's Note\n{authors_note}"])

        messages = build_messages(game_state, recent_messages, context_summary, user_input)
        director_tool = build_director_tool(script_type, game_mode)
        schema = director_tool["input_schema"]

        model_id = self.llm_router.current_model_for_purpose("game_main")
        cap = capability_for(model_id)

        last_feedback = ""
        for attempt in range(3):
            mutated_system = base_system
            if last_feedback:
                mutated_system = (
                    base_system
                    + "\n\n## 上一次输出的问题\n"
                    + last_feedback
                    + "\n请这次严格按 schema 输出，避免重复同样问题。"
                )

            try:
                if cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT:
                    result = await self._run_json_mode(
                        system=mutated_system,
                        messages=messages,
                        schema=schema,
                    )
                elif cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL:
                    result = await self._run_tool_use(
                        system=mutated_system,
                        messages=messages,
                        director_tool=director_tool,
                        recall_fn=recall_fn,
                        tool_choice={
                            "type": "function",
                            "function": {"name": director_tool["name"]},
                        },
                    )
                else:
                    result = await self._run_tool_use(
                        system=mutated_system,
                        messages=messages,
                        director_tool=director_tool,
                        recall_fn=recall_fn,
                        tool_choice="auto",
                    )
            except DirectorParseError as exc:
                last_feedback = (
                    f"- 上次输出无法解析：{exc}。"
                    "请直接输出一个合法 JSON 对象（或调用 director_decide 工具），不要任何前导文本或思考标签。"
                )
                logger.warning(
                    "director.parse_failure_retrying",
                    attempt=attempt,
                    reason=str(exc),
                )
                continue

            if result is None:
                last_feedback = (
                    "- 上次没有返回任何工具调用或 JSON 输出。"
                    "请直接产出 scene_direction / involved_npcs 字段的 JSON 对象。"
                )
                continue

            return result

        raise DirectorParseError("Director produced no usable output after 3 attempts")
```

Update `_run_tool_use` signature to accept `tool_choice` and forward it to `llm_router.stream_with_tools`. Update `_run_json_mode` to call `llm_router.stream_json` instead of `stream_with_tools(... response_format=...)` so the path is explicit.

Also extend `_run_json_mode` to strip `<think>...</think>` and `<reasoning>...</reasoning>` blocks before JSON extraction:

```python
import re
_THINK_RE = re.compile(r"<(think|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)

# In _run_json_mode, before json.loads:
raw = _THINK_RE.sub("", raw).strip()
```

- [ ] **Step 5: Remove `director_prefer_json_mode` from `config.py`**

Delete the field at `backend/config.py:61`.

- [ ] **Step 6: Update orchestrator.py wiring**

`backend/engine/orchestrator.py:149-152`:

```python
self.director_agent = director_agent or DirectorAgent(self.llm_router)
```

(Remove the `prefer_json_mode` kwarg.)

- [ ] **Step 7: Run tests**

```bash
cd backend && python -m pytest tests/test_director_capability_routing.py tests/test_director_json_mode.py tests/test_director_inform_npc.py tests/test_orchestrator.py -v
```

Expected: PASS. Existing director tests that constructed `DirectorAgent(router, prefer_json_mode=...)` need to drop that kwarg — update them to pass.

- [ ] **Step 8: Commit**

```bash
git add backend/engine/director_agent.py backend/engine/orchestrator.py \
        backend/config.py \
        backend/tests/test_director_capability_routing.py \
        backend/tests/test_director_json_mode.py \
        backend/tests/test_director_inform_npc.py \
        backend/tests/test_orchestrator.py
git commit -m "feat(director): per-model capability dispatch + prompt-mutation retry"
```

---

## Phase 9 — Observability counters

### Task 9.1: Extend `token_usage` with outcome columns

**Files:**
- Modify: `backend/models/token_usage.py`
- Create: `backend/migrations/versions/<timestamp>_add_token_usage_outcome.py`
- Modify: `backend/engine/director_agent.py` (record outcome)
- Test: `backend/tests/test_token_usage_outcome.py`

- [ ] **Step 1: Inspect current `token_usage` model**

```bash
cat backend/models/token_usage.py
```

- [ ] **Step 2: Add columns**

Add to the model:

```python
outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
# values: "success" | "parse_failure" | "retried_success" | "error"
retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd backend && alembic revision -m "add token_usage outcome and retry_count"
```

Edit the generated migration to:

```python
def upgrade():
    op.add_column("token_usage", sa.Column("outcome", sa.String(20), nullable=False,
                                            server_default="success"))
    op.add_column("token_usage", sa.Column("retry_count", sa.Integer(), nullable=False,
                                            server_default="0"))

def downgrade():
    op.drop_column("token_usage", "retry_count")
    op.drop_column("token_usage", "outcome")
```

- [ ] **Step 4: Wire outcome recording in Director**

In `director_agent.run`, after success/failure paths, ensure the `usage_context` wrapping the LLM call also records `outcome` and `retry_count`. Look at `services/token_usage_aop.py` or whatever AOP wraps usage to find the hook point.

If the AOP doesn't expose outcome, extend `record_usage(...)` to take an optional `outcome` and `retry_count`.

- [ ] **Step 5: Add a focused test**

```python
# backend/tests/test_token_usage_outcome.py
# Insert a token_usage row with outcome="parse_failure" and retry_count=2;
# read it back and assert the values persist.
```

- [ ] **Step 6: Run migration locally and tests**

```bash
cd backend && alembic upgrade head
cd backend && python -m pytest tests/test_token_usage_outcome.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/models/token_usage.py backend/migrations/versions/ \
        backend/engine/director_agent.py backend/tests/test_token_usage_outcome.py
git commit -m "feat(observability): record Director outcome + retry_count in token_usage"
```

---

## Phase 10 — Cleanup band-aids

### Task 10.1: Remove `_canonicalize_function_style_ops` from DSL parser

**Files:**
- Modify: `backend/engine/condition_dsl.py`
- Test: existing `backend/tests/test_condition_dsl.py`

- [ ] **Step 1: Confirm no production path still feeds function-style ops**

After Phase 2 lands, the events_data_builder always serializes from tree → canonical DSL string. Search for any other producer of `AND(...)` style strings:

```bash
grep -rn "AND(\|OR(\|NOT(" backend/services/ backend/engine/ --include="*.py" | grep -v test
```

Expected: only the parser's own canonicalization code references that pattern.

- [ ] **Step 2: Delete `_FUNCTION_STYLE_OP_RE`, `_split_top_level_commas`, `_canonicalize_function_style_ops`**

Remove the three definitions (lines ~373-473 in `condition_dsl.py`) and drop the call in `parse()` at line 484:

```python
def parse(source: str) -> _Expr:
    if not source or not source.strip():
        raise ConditionDSLParseError("Empty condition DSL string")

    tokens = _tokenize(source)
    parser = _Parser(tokens)
    expr = parser.parse_expr()

    if not parser._at_end():
        leftover_type, leftover_val = parser._peek()
        raise ConditionDSLParseError(
            f"Unexpected token {leftover_type!r} ({leftover_val!r}) after end of expression"
        )

    return expr
```

- [ ] **Step 3: Run condition_dsl tests**

```bash
cd backend && python -m pytest tests/test_condition_dsl.py -v
```

Expected: PASS. If a test asserts that `AND(x,y)` parses, delete it — that path is gone by design.

- [ ] **Step 4: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -x 2>&1 | tail -20
```

Expected: 0 failures. Investigate any regression before proceeding.

- [ ] **Step 5: Commit**

```bash
git add backend/engine/condition_dsl.py backend/tests/test_condition_dsl.py
git commit -m "refactor(dsl): remove function-style canonicalizer (tree is now the input)"
```

---

### Task 10.2: Remove VPS runner's content_repair.py

**Files (on VPS):**
- Delete: `experiments/2026-05-vps-eval/runner/content_repair.py`
- Modify: `experiments/2026-05-vps-eval/runner/smoke_generation.py`

- [ ] **Step 1: Check what imports `content_repair` on the VPS**

```bash
ssh tale "cd /inkwild && grep -rn 'content_repair\|audit_and_repair_world' experiments/ --include='*.py'"
```

- [ ] **Step 2: Remove the audit call from `smoke_generation.py`**

Replace the call to `audit_and_repair_world(...)` with an assertion that no audit issues exist:

```python
# Before:
# result = await audit_and_repair_world(db, world_id=world_id)
# After:
# (audit removed — backend now enforces schema at publish; if smoke generation
#  produced a publishable world, it is already valid by construction.)
```

If smoke flow previously logged audit issues to `smoke-generation-YYYY-MM-DD.md`, remove that section.

- [ ] **Step 3: Delete content_repair.py on VPS**

```bash
ssh tale "rm /inkwild/experiments/2026-05-vps-eval/runner/content_repair.py"
ssh tale "rm -rf /inkwild/experiments/2026-05-vps-eval/runner/__pycache__"
```

- [ ] **Step 4: Restart backend on VPS (to pick up new code if not auto-reloaded)**

```bash
ssh tale "cd /inkwild && docker compose restart backend"
```

- [ ] **Step 5: Commit (VPS-side experiment repo)**

```bash
ssh tale "cd /inkwild/experiments/2026-05-vps-eval && git add -A && git commit -m 'chore: drop content_repair band-aid'"
```

---

## Phase 11 — Smoke validation

### Task 11.1: Re-run generation smoke and assert clean output

- [ ] **Step 1: Deploy new backend to VPS**

```bash
ssh tale "cd /inkwild && git pull && docker compose build backend && docker compose up -d backend"
```

- [ ] **Step 2: Run alembic migration**

```bash
ssh tale "docker exec inkwild_backend_1 alembic upgrade head"
```

- [ ] **Step 3: Re-run smoke generation**

```bash
ssh tale "cd /inkwild && docker exec inkwild_backend_1 python -m experiments.2026-05-vps-eval.runner.smoke_generation"
```

Expected:
- All 5 worlds publish successfully.
- No `disabled=true` events anywhere in published scripts.
- No `needs_human_review` worlds.
- New `smoke-generation-YYYY-MM-DD.md` has no "audit issue" / "repair" lines.

If any world fails publish, the failure should be in the new schema validator — read the error, fix the generator prompt (Phase 2-4 prompts), do not add band-aids.

- [ ] **Step 4: Re-run smoke gameplay**

```bash
ssh tale "cd /inkwild && docker exec inkwild_backend_1 python -m experiments.2026-05-vps-eval.runner.session_runner --world-id <new-world-id> --mode script"
```

Run 5 sessions across the smoke worlds. Expected:
- 0 `llm_parse` SSE errors.
- Director success rate >= 95% across rounds.
- New `smoke-gameplay-YYYY-MM-DD.md` shows full multi-turn sessions, not just openings + `/结束测试`.

- [ ] **Step 5: Verify token_usage outcome distribution**

```bash
ssh tale "docker exec inkwild_db_1 psql -U postgres -d inkwild -c \"SELECT outcome, COUNT(*) FROM token_usage WHERE created_at > now() - interval '1 hour' AND purpose='game' GROUP BY outcome;\""
```

Expected: success dominant; parse_failure < 5% of rows.

- [ ] **Step 6: Write final smoke report**

Append to `experiments/2026-05-vps-eval/reports/smoke-generation-YYYY-MM-DD.md` and `smoke-gameplay-YYYY-MM-DD.md` with the new clean output. Note the absence of audit/repair lines as the success criterion.

- [ ] **Step 7: Commit smoke artifacts**

```bash
ssh tale "cd /inkwild/experiments/2026-05-vps-eval && git add reports/ && git commit -m 'chore: smoke report after hardening'"
```

---

## Self-Review Checklist (run after writing)

- [ ] **Spec coverage:** Issues 1/2/3/4 each have a phase. Issue 1 → Phase 4. Issue 2 → Phases 1-2 + 10. Issue 3 → Phase 3. Issue 4 → Phases 6-8.
- [ ] **No placeholders:** Every code step has full code. Every command has expected output. Every test has full body.
- [ ] **Type consistency:** `StructuredOutputMode` used identically in Phases 6 and 8. `ConditionTree` type alias used in Phases 1 and 2. `SchemaValidationError` raised in Phase 5 and not consumed downstream (HTTPException wraps it).
- [ ] **Test fixtures:** Each new test stands alone — no shared state between test files.
- [ ] **Migration safety:** Phase 9 migration has both `upgrade` and `downgrade`, with server_default so existing rows back-fill cleanly.
- [ ] **Rollback path:** Each phase is one or more focused commits; `git revert <sha>` restores the prior behavior. Phase 10 is gated on Phases 1-2 landing — do not skip ahead.

---

## Open follow-ups (not in scope)

These were considered and intentionally deferred:

- **Cross-model Director fallback** (originally C2.D): Skipped per user direction. Add a `director_fallback` slot in a future iteration if `parse_failure` rate stays elevated for a specific model.
- **Existing world DSL migration**: Pre-2026-05-23 worlds still hold raw DSL strings without `condition_tree` field. They keep working via the unchanged runtime parser. A one-off backfill script `tree_from_dsl(...)` could be written later to populate `condition_tree` for audit, but is not needed for runtime.
- **Admin "Model Health" dashboard** consuming the new `token_usage.outcome` column: out of scope; raw SQL queries suffice for now.
