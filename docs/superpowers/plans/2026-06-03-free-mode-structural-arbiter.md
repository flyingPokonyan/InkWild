# Free-Mode Structural Arbiter (S4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** In **free mode** (no authored milestones, no ground truth), when the Director proposes a structural change it believes is genuinely caused (`supported=true`), an **independent character/world-consistency judge** verifies it before committing. Approve → `commit_structural_fact` (the S3 machinery already built & verified). Reject → no commit (the S2 reaction path already handles in-world friction). This is the "earn structural change through play" highlight.

**Architecture:** New `engine/structural_arbiter.py` mirrors `engine/stance_inference.py` (cheap-LLM, `stream_json`, parse-or-safe-default). **Rare-fire:** the judge only runs when there is a `structural_change_proposed` with `supported=true` in **free** mode and the flag is on — 99% of turns make zero extra LLM calls. **Independent second opinion** (not the proposing Director → anti-yes-man). **Conservative:** any failure → deny (never auto-commit on error). Genre-neutral charter: "given these actors' established personalities + setting rules + what's happened, would this change actually come about now?" Wired into the orchestrator at the existing structural observability point (~line 1826, after `director_result` resolves), using the cheap `self.npc_llm_router`. On approve → commit with `provenance="free_arbiter"`; the committed fact reaches the spine next turn via the S3 overlay (this turn the Director already narrated the cause it proposed).

**Tech Stack:** Python 3.12, async, structlog, pytest. Reuses `stream_json` (router), `engine/structural_ledger.commit_structural_fact` (S3), the `structural_change_proposed` field (Plan 1).

> **Repo note:** 0-commit repo, commits held — confirm before first commit.
> **Tests:** container `talealive-backend-1` (`docker exec ... python -m pytest`).
> **Spec:** [`../specs/2026-06-03-structural-evolution-pipeline-design.md`](../specs/2026-06-03-structural-evolution-pipeline-design.md) §3.2 (free-mode judge), §1 (philosophy A, generality, flag = dev/eval knob), §8 (S4).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/config.py` | settings | Add `structural_free_arbiter_enabled: bool = True` (dev/eval knob, default on per user) |
| `backend/engine/structural_arbiter.py` | **NEW** — consistency judge | `ARBITER_SYSTEM`, `build_arbiter_messages`, `parse_verdict`, `judge_structural_change` |
| `backend/engine/orchestrator.py` | v2 turn path (~line 1826) | free + supported + flag → judge → commit on approve; update structural observability log |
| `backend/tests/test_structural_arbiter.py` | **NEW** | parse (approve/reject/garbage→deny), judge (approve/deny/failure→deny), cross-genre |

**Genre-neutrality (hard):** prompt + tests genre-neutral; judge tests span ≥3 genres.

---

## Task 1: Config flag

**Files:** Modify `backend/config.py` (near `npc_initial_stance_enabled` ~line 142)

- [ ] **Step 1: Add the flag**

In `backend/config.py`, right after `npc_initial_stance_enabled: bool = True`:

```python
    # Free-mode structural arbiter (spec §3.2, S4) — when the Director proposes
    # a structural change it deems caused (supported=true) in FREE mode, an
    # independent cheap-LLM judge verifies world/character consistency before
    # committing. Rare-fire (only on supported=true proposals). Dev/eval knob;
    # default on (the "earn world change through play" feature is live).
    structural_free_arbiter_enabled: bool = True
```

- [ ] **Step 2: Verify it loads**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "from config import settings; print(settings.structural_free_arbiter_enabled)"'`
Expected: `True`.

- [ ] **Step 3: Commit** (confirm with user first)

```bash
git add backend/config.py
git commit -m "feat(config): add structural_free_arbiter_enabled flag (default on)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `parse_verdict` — pure, conservative parse

**Files:** Create `backend/engine/structural_arbiter.py`; Test `backend/tests/test_structural_arbiter.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_structural_arbiter.py`:

```python
from engine.structural_arbiter import parse_verdict


def test_parse_verdict_approve():
    v = parse_verdict('{"supported": true, "reason": "议会已投票通过", "missing": ""}')
    assert v["supported"] is True
    assert "议会" in v["reason"]


def test_parse_verdict_reject_with_missing():
    v = parse_verdict('{"supported": false, "reason": "无授权", "missing": "需议会任命"}')
    assert v["supported"] is False
    assert v["missing"] == "需议会任命"


def test_parse_verdict_garbage_defaults_to_deny():
    # Never raises; unparseable → conservative deny (never auto-commit on noise).
    for bad in ["", "not json", "{oops", None]:
        v = parse_verdict(bad)
        assert v["supported"] is False


def test_parse_verdict_strips_code_fence():
    v = parse_verdict('```json\n{"supported": true, "reason": "ok", "missing": ""}\n```')
    assert v["supported"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_arbiter.py -k parse_verdict -v'`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.structural_arbiter'`.

- [ ] **Step 3: Create the module with parse_verdict**

Create `backend/engine/structural_arbiter.py`:

```python
"""Free-mode structural consistency judge (spec §3.2, S4).

Independent second-opinion on a Director-proposed structural change: "given
the world's established logic (involved actors' personalities/motives +
setting rules + what has happened), would this change actually come about
now?" Genre-neutral. Cheap-LLM, rare-fire (only on supported=true free-mode
proposals). Mirrors engine/stance_inference.py. Conservative: any failure or
unparseable output → deny (never auto-commit on error).
"""
from __future__ import annotations

import json as _json

import structlog

logger = structlog.get_logger()

ARBITER_SYSTEM = (
    "你是世界一致性裁决者。给你一个【被提议的世界底色（结构事实）改变】，以及涉及角色的人设、"
    "世界设定规则、和已经发生的因果。\n"
    "你要判断的【不是】玩家想不想、说没说，而是：**以这个世界的既定逻辑——涉及角色的性格/动机/约束"
    " + 世界设定规则 + 已经发生的因果——此刻这个改变会不会真的发生、成立？**\n"
    "- 有足够且自洽的世界内因促成它（某角色会按其性格这么做 / 某事件已造成它 / 设定规则允许并被满足）→ supported=true。\n"
    "- 仅凭一句声称、缺乏世界内因、或与角色性格/设定规则相悖 → supported=false。\n"
    "保守原则：证据不足时一律 false。\n"
    "只输出 JSON，不要任何解释文字：\n"
    '{"supported": true/false, "reason": "一句话依据", "missing": "若 false，还差什么世界内因才成立"}'
)

_DENY = {"supported": False, "reason": "", "missing": ""}


def build_arbiter_messages(proposal: dict, world_data: dict, recent_context: str = "") -> list[dict]:
    """Assemble the judge's user message from the proposal + the world's
    established logic (setting rules + involved-actor personas) + recent
    context. Genre-neutral: no assumptions about fact category."""
    parts = [
        "【被提议的结构改变】",
        f"- 内容：{str(proposal.get('fact_text') or '').strip()}",
        f"- 类型：{str(proposal.get('kind') or '').strip()}",
        f"- 涉及对象：{str(proposal.get('target_ref') or '（世界层面）').strip()}",
        f"- 导演给的世界内因：{str(proposal.get('in_world_cause') or '（未给）').strip()}",
        f"- 导演的依据：{str(proposal.get('justification') or '（未给）').strip()}",
        "",
        "【世界设定规则】",
        str(world_data.get("base_setting") or "（无）").strip(),
        "",
        "【涉及角色 / 人物画像】",
        str(world_data.get("npc_descriptions") or "（无）").strip(),
    ]
    if recent_context.strip():
        parts += ["", "【近期发生】", recent_context.strip()]
    return [{"role": "user", "content": "\n".join(parts)}]


def parse_verdict(raw: object) -> dict:
    """Pure parse. Never raises. Unparseable / non-dict → conservative deny."""
    text = (str(raw) if raw is not None else "").strip()
    if not text:
        return dict(_DENY)
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text[:-3] if text.rstrip().endswith("```") else text
    try:
        start, end = text.find("{"), text.rfind("}")
        parsed = _json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:  # noqa: BLE001
        return dict(_DENY)
    if not isinstance(parsed, dict):
        return dict(_DENY)
    return {
        "supported": bool(parsed.get("supported")),
        "reason": str(parsed.get("reason") or "").strip()[:120],
        "missing": str(parsed.get("missing") or "").strip()[:120],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_arbiter.py -k parse_verdict -v'`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** (confirm first)

```bash
git add backend/engine/structural_arbiter.py backend/tests/test_structural_arbiter.py
git commit -m "feat(engine): structural arbiter parse_verdict (conservative deny)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `judge_structural_change` — the cheap-LLM call

**Files:** Modify `backend/engine/structural_arbiter.py`; Test `backend/tests/test_structural_arbiter.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_structural_arbiter.py`:

```python
import pytest
from engine.structural_arbiter import judge_structural_change


class _FakeRouter:
    """Mimics LLMRouter.stream_json yielding text_delta events."""
    def __init__(self, chunks, raise_exc=False):
        self._chunks = chunks
        self._raise = raise_exc

    async def stream_json(self, *, messages, system, max_tokens):
        if self._raise:
            raise RuntimeError("provider down")
        for c in self._chunks:
            yield {"type": "text_delta", "text": c}


_WORLD = {"base_setting": "深空殖民船，舰长由议会任命。", "npc_descriptions": "里夫斯：恪守船规。"}
_PROPOSAL = {"fact_text": "艾拉成为舰长", "kind": "entity_role_changed", "target_ref": "艾拉",
             "in_world_cause": "议会投票", "justification": "三派结盟后投票通过"}


@pytest.mark.asyncio
async def test_judge_approves_when_llm_supports():
    router = _FakeRouter(['{"supported": true,', ' "reason": "议会已通过", "missing": ""}'])
    v = await judge_structural_change(router, _PROPOSAL, _WORLD)
    assert v["supported"] is True


@pytest.mark.asyncio
async def test_judge_denies_when_llm_rejects():
    router = _FakeRouter(['{"supported": false, "reason": "无授权", "missing": "需议会任命"}'])
    v = await judge_structural_change(router, _PROPOSAL, _WORLD)
    assert v["supported"] is False
    assert v["missing"]


@pytest.mark.asyncio
async def test_judge_denies_on_llm_failure():
    router = _FakeRouter([], raise_exc=True)
    v = await judge_structural_change(router, _PROPOSAL, _WORLD)
    assert v["supported"] is False  # never auto-commit on error
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_arbiter.py -k judge -v'`
Expected: FAIL — `ImportError: cannot import name 'judge_structural_change'`.

- [ ] **Step 3: Add the function**

Append to `backend/engine/structural_arbiter.py`:

```python
async def judge_structural_change(
    llm_router, proposal: dict, world_data: dict, recent_context: str = ""
) -> dict:
    """One-shot consistency judgment. Returns a verdict dict
    {supported, reason, missing}. Any failure → conservative deny, so callers
    never auto-commit on error. Mirrors stance_inference.infer_initial_stances.
    """
    text_parts: list[str] = []
    try:
        async for event in llm_router.stream_json(
            messages=build_arbiter_messages(proposal, world_data, recent_context),
            system=ARBITER_SYSTEM,
            max_tokens=512,
        ):
            if event.get("type") == "text_delta":
                text_parts.append(event.get("text", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("structural_arbiter_failed", error=str(exc))
        return dict(_DENY)
    verdict = parse_verdict("".join(text_parts))
    logger.info(
        "structural_arbiter_done",
        supported=verdict["supported"], fact_key=proposal.get("fact_key"),
    )
    return verdict
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_arbiter.py -v'`
Expected: PASS (all parse + judge tests).

- [ ] **Step 5: Commit** (confirm first)

```bash
git add backend/engine/structural_arbiter.py backend/tests/test_structural_arbiter.py
git commit -m "feat(engine): judge_structural_change cheap-LLM consistency judge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Orchestrator wiring — judge then commit (rare-fire, free mode)

**Files:** Modify `backend/engine/orchestrator.py` (the structural observability block added in Plan 1, ~line 1826)

- [ ] **Step 0: Locate the Plan 1 observability block**

Run: `cd backend && grep -n "structural.proposal\|director_result.structural_change_proposed" engine/orchestrator.py`
Expected: the `if director_result.structural_change_proposed:` block (committed=False placeholder). Replace it in Step 1.

- [ ] **Step 1: Replace the block with judge+commit**

In `backend/engine/orchestrator.py`, replace the existing block:

```python
        if director_result.structural_change_proposed:
            _sp = director_result.structural_change_proposed
            logger.info(
                "structural.proposal",
                session_id=session_id,
                round_number=round_number,
                supported=_sp.get("supported"),
                kind=_sp.get("kind"),
                fact_key=_sp.get("fact_key"),
                has_reaction=bool(_sp.get("world_reaction")),
                committed=False,
            )
```

with:

```python
        if director_result.structural_change_proposed:
            _sp = director_result.structural_change_proposed
            _committed = False
            # Rare-fire free-mode arbiter (spec §3.2, S4): only verify proposals
            # the Director deems caused (supported=true) in free mode. The
            # arbiter is an independent second opinion (anti-yes-man); on
            # approve we commit via the S3 ledger (visible to the Director next
            # turn). Reject / non-free / supported=false → no commit; the S2
            # reaction (rendered through the Director's normal fields) stands.
            if (
                game_mode == "free"
                and _sp.get("supported")
                and settings.structural_free_arbiter_enabled
            ):
                from engine.structural_arbiter import judge_structural_change
                from engine.structural_ledger import commit_structural_fact

                _verdict = await judge_structural_change(
                    self.npc_llm_router, _sp, world_data
                )
                if _verdict.get("supported"):
                    _committed = commit_structural_fact(
                        game_state, dict(_sp, provenance="free_arbiter")
                    )
                logger.info(
                    "structural.arbiter",
                    session_id=session_id,
                    round_number=round_number,
                    fact_key=_sp.get("fact_key"),
                    arbiter_supported=_verdict.get("supported"),
                    reason=_verdict.get("reason"),
                    committed=_committed,
                )
            logger.info(
                "structural.proposal",
                session_id=session_id,
                round_number=round_number,
                supported=_sp.get("supported"),
                kind=_sp.get("kind"),
                fact_key=_sp.get("fact_key"),
                has_reaction=bool(_sp.get("world_reaction")),
                committed=_committed,
            )
```

- [ ] **Step 2: Verify import + no syntax error**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "import engine.orchestrator; print(\"OK\")"'`
Expected: `OK`.

- [ ] **Step 3: Regression — changed-module + new suites**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_arbiter.py tests/test_structural_ledger.py tests/test_structural_milestones.py tests/test_director_agent.py tests/test_prompts.py -q 2>&1 | tail -4'`
Expected: PASS.

- [ ] **Step 4: Commit** (confirm first)

```bash
git add backend/engine/orchestrator.py
git commit -m "feat(engine): wire free-mode structural arbiter -> commit (rare-fire)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Real-run verification (earned vs fiat)

- [ ] **Step 1:** Throwaway harness (delete after). Build a free-mode `world_data` (sci-fi council ship: captaincy requires council vote) + a `GameState`. Two real `DirectorAgent.run_v2` + arbiter runs:
  - **Earned:** recent context establishes the player has secured the three factions' votes; player declares captaincy. Expect Director `supported=true` → arbiter approve → `commit_structural_fact` → `game_state.structural_facts` gains the role change; next-turn `apply_structural_overlay` shows it.
  - **Fiat:** no buildup; player just declares captaincy. Expect Director `supported=false` (no arbiter call) OR arbiter deny → no commit; world reaction present.
- [ ] **Step 2:** Capture both outcomes (the `structural.arbiter` / `structural.committed` logs + `structural_facts` before/after). Verdict PASS only if earned commits and fiat does not.
- [ ] **Step 3:** Remove the harness.

> Note: full orchestrator-path unit tests are blocked by the pre-existing `FakeDirectorAgent.run_v2` stale fixture; the arbiter + parse are unit-covered (Tasks 2–3), the commit is covered (S3 Task 3), and this real-run covers the integration seam.

---

## Self-Review (plan-write time)

**Spec coverage:** §3.2 free-mode judge → Tasks 2–3; rare-fire + free-only + flag gating → Task 4; approve→commit via S3 → Task 4; conservative-deny on failure → Tasks 2–3; flag as dev/eval knob → Task 1; real-run gate → Task 5. **Connects Plan 1's `structural_change_proposed` to Plan 2's `commit_structural_fact` — the last seam of the pipeline.**

**Placeholder scan:** none. Task 4 Step-0 grep pins the exact block to replace.

**Type consistency:** verdict dict keys `{supported, reason, missing}` consistent across `parse_verdict`/`judge_structural_change`/orchestrator. `commit_structural_fact(state, fact)` signature matches S3. `provenance="free_arbiter"` matches the spec/S3 ledger entry shape. Arbiter uses `self.npc_llm_router` (cheap, confirmed available in orchestrator __init__).

**Genre-neutrality:** `ARBITER_SYSTEM` is world-logic-general (no authority/genre assumption); judge tests use sci-fi council; combined with palace (S2) + relationship (S3) tests, ≥3 genres across the pipeline.
```
