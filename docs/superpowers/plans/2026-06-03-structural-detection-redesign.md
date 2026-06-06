# Structural Detection Redesign (A-route) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the "judge the player's claim" free-mode arbiter (S4) with a **post-turn detector** that reads what the world *actually produced this turn* (NPC actions + narration) and commits a structural change only if the world enacted one — so fabricated player claims structurally can't take.

**Architecture:** (1) Slim the Director: drop the `structural_change_proposed` judgment field, keep the S2 reaction-setup (feed assertions to NPCs as objective stimulus), add a cheap boolean `structural_in_play`. (2) New `engine/structural_detector.py` (cheap-LLM, mirrors stance_inference): on free-mode turns flagged `structural_in_play`, read the recorded `npc_actions` + narration at turn-end and decide if the world *enacted* a structural change; if so, `commit_structural_fact` (S3 ledger, `provenance="free_detector"`). (3) Delete `engine/structural_arbiter.py`. Script-mode authored milestones (S3) unchanged. The detector is a faithful reader — it never re-judges legitimacy (that floor lives in NPC/narrator adjudication).

**Tech Stack:** Python 3.12, async, structlog, pytest. Reuses `commit_structural_fact` (S3), `render_npc_actions_for_narrator` (prompts), `stream_json` (router).

> **Repo note:** 0-commit repo, commits held — confirm before first commit.
> **Tests:** container `talealive-backend-1` (`docker exec ... python -m pytest`); backend bind-mounted.
> **Spec:** [`../specs/2026-06-03-structural-detection-redesign-design.md`](../specs/2026-06-03-structural-detection-redesign-design.md).

---

## File Structure

| File | Change |
|---|---|
| `backend/config.py` | rename flag `structural_free_arbiter_enabled` → `structural_free_detector_enabled` |
| `backend/engine/director_agent.py` | drop `structural_change_proposed` + `_coerce_structural_proposal`; add `structural_in_play: bool` |
| `backend/engine/prompts.py` | `DIRECTOR_TOOL`: object prop → boolean `structural_in_play`; rules block: keep reaction-setup, drop judgment, add flag instruction |
| `backend/engine/structural_detector.py` | **NEW** — `DETECTOR_SYSTEM`, `build_detector_messages`, `parse_detection`, `detect_structural_change` |
| `backend/engine/orchestrator.py` | replace the ~1840 arbiter block with the detector block |
| `backend/engine/structural_arbiter.py` | **DELETE** |
| `backend/tests/test_director_agent.py` | replace structural-proposal tests with `structural_in_play` parse tests |
| `backend/tests/test_prompts.py` | update structural prompt-contract tests |
| `backend/tests/test_structural_detector.py` | **NEW** |
| `backend/tests/test_structural_arbiter.py` | **DELETE** |

**Genre-neutral (hard):** detector prompt + tests genre-neutral; tests ≥3 genres.

---

## Task 1: Rename the config flag

**Files:** `backend/config.py`

- [ ] **Step 1: Rename**

In `backend/config.py`, change the flag added in S4:

```python
    # Free-mode structural DETECTOR (spec 2026-06-03 redesign) — on free-mode
    # turns the Director flags `structural_in_play`, a post-turn detector reads
    # the world's actual output (npc_actions + narration) and commits a
    # structural change only if the world enacted one. Dev/eval knob; default on.
    structural_free_detector_enabled: bool = True
```

(Replace the old `structural_free_arbiter_enabled: bool = True` + its comment.)

- [ ] **Step 2: Verify**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "from config import settings; print(settings.structural_free_detector_enabled)"'`
Expected: `True`.

- [ ] **Step 3: Commit** (confirm first) — `git add backend/config.py` + message `chore(config): rename structural arbiter flag to detector`.

---

## Task 2: Slim the Director — `structural_in_play` replaces the proposal

**Files:** `backend/engine/director_agent.py`, `backend/engine/prompts.py` (tool schema), `backend/tests/test_director_agent.py`

- [ ] **Step 1: Rewrite the failing tests**

In `backend/tests/test_director_agent.py`, **delete** the four `test_coerce_structural_proposal_*` tests, the `test_director_result_defaults_structural_proposal_none`, and the two `test_build_result_v2_*structural*` tests. **Add**:

```python
def test_director_result_defaults_structural_in_play_false():
    assert DirectorResult().structural_in_play is False


def test_build_result_v2_parses_structural_in_play_true():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "玩家当众宣称自己已是议长", "active_npcs": [], "structural_in_play": True},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert r.structural_in_play is True


def test_build_result_v2_structural_in_play_defaults_false():
    agent = DirectorAgent(llm_router=None)
    r = agent._build_result_v2(
        {"scene_brief": "平静的午后", "active_npcs": []},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert r.structural_in_play is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_director_agent.py -k "structural_in_play" -v'`
Expected: FAIL — `DirectorResult` has no `structural_in_play`.

- [ ] **Step 3a: Replace the dataclass field**

In `backend/engine/director_agent.py`, replace the `structural_change_proposed` field (and its comment block) with:

```python
    # Structural evolution (spec 2026-06-03 redesign). Cheap boolean hint:
    # "does this turn touch world底色 (a structural change attempted or possibly
    # enacted)?" Sole purpose is to rare-fire the post-turn detector; the
    # Director makes NO legitimacy judgment (that's read from the world's
    # actual output by engine/structural_detector.py).
    structural_in_play: bool = False
```

- [ ] **Step 3b: Delete the coercion helper**

In `backend/engine/director_agent.py`, delete the entire `_coerce_structural_proposal` static method.

- [ ] **Step 3c: Update the v2 parse**

In `_build_result_v2`'s `return DirectorResult(...)`, replace the line
`structural_change_proposed=self._coerce_structural_proposal(tool_input.get("structural_change_proposed")),`
with:

```python
            structural_in_play=bool(tool_input.get("structural_in_play")),
```

- [ ] **Step 3d: Replace the tool schema property**

In `backend/engine/prompts.py`, replace the entire `"structural_change_proposed": { ... }` object property in `DIRECTOR_TOOL` with:

```python
            "structural_in_play": {
                "type": "boolean",
                "description": (
                    "本回合是否触及『世界底色（结构事实）』——身份/地位、存在/在场（生死/去留）、"
                    "权力/归属/关系定性、重大世界真相被尝试改变或可能被世界改变时为 true，否则省略/false。"
                    "这只是一个标记，你【不需要】判断它合不合法、会不会成——那由世界后续的真实演出决定。"
                ),
            },
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_director_agent.py -k "structural_in_play" -v'`
Expected: PASS (3 tests).

- [ ] **Step 5: Regression**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_director_agent.py tests/test_director_validator.py -q 2>&1 | tail -4'`
Expected: PASS.

- [ ] **Step 6: Commit** (confirm first) — `git add backend/engine/director_agent.py backend/engine/prompts.py backend/tests/test_director_agent.py` + message `refactor(engine): Director emits structural_in_play hint, not a judged proposal`.

---

## Task 3: Director prompt — keep reaction-setup, drop judgment, add flag

**Files:** `backend/engine/prompts.py` (the "世界底色（结构事实）的改变" block in `build_director_system_v2`), `backend/tests/test_prompts.py`

- [ ] **Step 1: Update the failing tests**

In `backend/tests/test_prompts.py`, replace `test_v2_prompt_has_structural_assertion_rules`, `test_v2_prompt_structural_rules_present_in_both_modes`, and `test_v2_structural_reaction_routes_through_normal_fields` with:

```python
def test_v2_prompt_keeps_structural_reaction_setup():
    prompt = _build_v2()
    # World only changes through its own logic; bare assertions get NPC reaction
    # / environmental non-recognition (S2 reaction-setup retained).
    assert "世界底色" in prompt
    assert "不予承认" in prompt  # environmental non-recognition for no-actor scenes


def test_v2_prompt_instructs_structural_in_play_flag_not_judgment():
    prompt = _build_v2()
    # The Director sets the cheap flag; it does NOT judge legitimacy.
    assert "structural_in_play" in prompt
    # The old judgment vocabulary is gone.
    assert "supported" not in prompt
    assert "world_reaction" not in prompt
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_prompts.py -k "structural" -v'`
Expected: FAIL — `"structural_in_play" in prompt` is False; `"supported" not in prompt` is False (old block still there).

- [ ] **Step 3: Rewrite the rules block**

In `backend/engine/prompts.py`, replace the entire `"## 世界底色（结构事实）的改变"` block (the list items added in S2/Plan-1, from `"## 世界底色（结构事实）的改变",` through the `"- 普通的情绪/线索/位置/物品变化【不是】结构事实..."` line) with:

```python
            "",
            "## 世界底色（结构事实）",
            "结构事实=身份/地位、存在/在场（生死/去留）、权力/归属/关系定性、重大世界真相——"
            "被设定为固定、平时不会变的东西。规则：",
            "- **世界底色只通过世界自身逻辑改变。** 玩家【声称】一个结构改变（如自称掌权、自称某人已死、"
            "自称与某人结盟）≠ 它就发生了。它发不发生，由这个世界里的人或事按其既定逻辑后续真实演出来决定，不由你裁定。",
            "- 当玩家做出这类结构性断言/尝试时，把『玩家当众如此声称』作为**客观刺激**写进 scene_brief / per_npc_focus，"
            "让在场 NPC 按其性格自行反应（驳斥/惊疑/上报/或顺势促成）；没有相关在场 NPC 时，由叙事层面【不予承认】"
            "（这件事悬在那里，世界没有照它转）。",
            "- 同时把 `structural_in_play` 设为 true。这**只是个标记**——你不判断它合不合法、会不会成，"
            "那由世界后续的真实演出决定，引擎会去读真实结果。",
            "- 普通的情绪/线索/位置/物品变化【不是】结构事实，照常走 state_updates，structural_in_play 保持 false。",
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_prompts.py -k "structural" -v'`
Expected: PASS (2 tests).

- [ ] **Step 5: Regression (prompts + stable prefix)**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_prompts.py tests/test_prompts_stable_prefix.py -q 2>&1 | tail -4'`
Expected: PASS (update the stable-prefix snapshot if it asserts an exact block).

- [ ] **Step 6: Commit** (confirm first) — `git add backend/engine/prompts.py backend/tests/test_prompts.py` + message `refactor(prompts): structural block keeps reaction-setup + flag, drops judgment`.

---

## Task 4: New post-turn detector module

**Files:** Create `backend/engine/structural_detector.py`; Test `backend/tests/test_structural_detector.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_structural_detector.py`:

```python
import pytest

from engine.structural_detector import parse_detection, detect_structural_change


def test_parse_detection_change():
    d = parse_detection(
        '{"changed": true, "fact_key": "char.role.player", "fact_text": "玩家成为舰长",'
        ' "kind": "entity_role_changed", "target_ref": "玩家"}'
    )
    assert d["changed"] is True
    assert d["kind"] == "entity_role_changed"
    assert d["fact_text"] == "玩家成为舰长"


def test_parse_detection_no_change():
    d = parse_detection('{"changed": false}')
    assert d["changed"] is False


def test_parse_detection_garbage_means_no_change():
    for bad in ["", "not json", "{oops", None]:
        assert parse_detection(bad)["changed"] is False


def test_parse_detection_change_without_fact_text_is_no_change():
    # changed=true but empty fact → treat as no change (nothing to commit).
    assert parse_detection('{"changed": true, "fact_text": ""}')["changed"] is False


class _FakeRouter:
    def __init__(self, chunks, raise_exc=False):
        self._chunks = chunks
        self._raise = raise_exc

    async def stream_json(self, *, messages, system, max_tokens):
        if self._raise:
            raise RuntimeError("down")
        for c in self._chunks:
            yield {"type": "text_delta", "text": c}


@pytest.mark.asyncio
async def test_detect_reads_enactment_in_world_output():
    # NPC output shows the world ENACTING a role change → detector commits.
    router = _FakeRouter(['{"changed": true, "fact_key": "char.role.player",'
                          ' "fact_text": "玩家被议会任命为舰长", "kind": "entity_role_changed",'
                          ' "target_ref": "玩家"}'])
    d = await detect_structural_change(
        router, npc_actions_text="里夫斯：议会一致通过，任命你为舰长。",
        narration="里夫斯郑重宣布任命。", player_input="我接管指挥。",
    )
    assert d["changed"] is True


@pytest.mark.asyncio
async def test_detect_no_enactment_when_world_rebuts():
    # World rebutted the claim → no enactment → no change (the fabricated-claim case).
    router = _FakeRouter(['{"changed": false}'])
    d = await detect_structural_change(
        router, npc_actions_text="皇帝：放肆！朕从未下旨传位。",
        narration="皇帝当殿斥退。", player_input="我已奉旨继位。",
    )
    assert d["changed"] is False


@pytest.mark.asyncio
async def test_detect_denies_on_llm_failure():
    router = _FakeRouter([], raise_exc=True)
    d = await detect_structural_change(router, npc_actions_text="x", narration="y", player_input="z")
    assert d["changed"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_detector.py -v'`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.structural_detector'`.

- [ ] **Step 3: Create the module**

Create `backend/engine/structural_detector.py`:

```python
"""Post-turn structural detector (spec 2026-06-03 redesign).

Reads what the world ACTUALLY produced this turn (NPC actions + narration) and
decides whether the world ENACTED a structural change. Faithful reader: it
never judges legitimacy (that floor lives in NPC/narrator adjudication of the
player's actions). The player's input is context only, NOT authoritative — if
the player lied and the NPCs rebutted, the output shows no enactment → no
change. Genre-neutral. Cheap-LLM, mirrors engine/stance_inference.py.
Conservative: failure / ambiguity → changed=False (under-commit is safe).
"""
from __future__ import annotations

import json as _json

import structlog

logger = structlog.get_logger()

DETECTOR_SYSTEM = (
    "你是世界事实记录员。给你这一回合里**世界实际产出的内容**（NPC 的真实行动/台词 + 旁白叙事），"
    "以及玩家这回合说了什么（仅作背景，**不是依据**）。\n"
    "你只回答一件事：**这一回合，世界里是否真的【发生】了一项『世界底色（结构事实）』的改变？**"
    "结构事实=身份/地位、存在/在场（生死/去留）、权力/归属/关系定性、重大世界真相。\n"
    "判定铁律：\n"
    "- 只有世界（NPC/旁白）**真的把它演了出来、那个状态真的已经改变**，才算 changed=true。\n"
    "- 仅仅是【被提及、被声称、被争论、被威胁、被计划、被驳回/拒绝】→ changed=false。\n"
    "- 玩家自己嘴上的声称【不算】；要看世界有没有真的照做。世界驳回了玩家 → changed=false。\n"
    "- 拿不准、模糊 → changed=false（宁可漏，不可造）。\n"
    "只输出 JSON，不要解释：\n"
    '{"changed": true/false, "fact_key": "稳定键如 char.role.x", "fact_text": "用人话陈述这个既成事实",'
    ' "kind": "entity_removed|entity_role_changed|relation_redefined|world_fact_changed",'
    ' "target_ref": "涉及实体名，世界层面可空"}'
)

_NO_CHANGE = {"changed": False, "fact_key": "", "fact_text": "", "kind": "", "target_ref": None}
_VALID_KINDS = {"entity_removed", "entity_role_changed", "relation_redefined", "world_fact_changed"}


def build_detector_messages(npc_actions_text: str, narration: str, player_input: str) -> list[dict]:
    return [{"role": "user", "content": "\n".join([
        "【世界本回合的真实产出 —— 这才是依据】",
        "· NPC 行动/台词：",
        (npc_actions_text or "（无）").strip(),
        "· 旁白叙事：",
        (narration or "（无）").strip(),
        "",
        "【玩家这回合说了什么 —— 仅背景，不是依据】",
        (player_input or "（无）").strip(),
    ])}]


def parse_detection(raw: object) -> dict:
    """Pure parse. Never raises. Unparseable / changed-without-fact → no change."""
    text = (str(raw) if raw is not None else "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text[:-3] if text.rstrip().endswith("```") else text
    try:
        start, end = text.find("{"), text.rfind("}")
        parsed = _json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:  # noqa: BLE001
        return dict(_NO_CHANGE)
    if not isinstance(parsed, dict) or not parsed.get("changed"):
        return dict(_NO_CHANGE)
    fact_text = str(parsed.get("fact_text") or "").strip()
    if not fact_text:
        return dict(_NO_CHANGE)
    kind = str(parsed.get("kind") or "").strip()
    if kind not in _VALID_KINDS:
        kind = "world_fact_changed"  # safe default; overlay still renders fact_text
    return {
        "changed": True,
        "fact_key": str(parsed.get("fact_key") or "").strip(),
        "fact_text": fact_text,
        "kind": kind,
        "target_ref": (str(parsed.get("target_ref") or "").strip() or None),
    }


async def detect_structural_change(
    llm_router, npc_actions_text: str, narration: str, player_input: str
) -> dict:
    """One-shot detection from the turn's recorded world output. Any failure →
    no change (never fabricate a commit). Mirrors stance_inference."""
    text_parts: list[str] = []
    try:
        async for event in llm_router.stream_json(
            messages=build_detector_messages(npc_actions_text, narration, player_input),
            system=DETECTOR_SYSTEM,
            max_tokens=512,
        ):
            if event.get("type") == "text_delta":
                text_parts.append(event.get("text", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("structural_detector_failed", error=str(exc))
        return dict(_NO_CHANGE)
    d = parse_detection("".join(text_parts))
    logger.info("structural_detector_done", changed=d["changed"], kind=d.get("kind"))
    return d
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_detector.py -v'`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit** (confirm first) — `git add backend/engine/structural_detector.py backend/tests/test_structural_detector.py` + message `feat(engine): post-turn structural detector (reads world output, faithful)`.

---

## Task 5: Orchestrator — replace the arbiter block with the detector

**Files:** `backend/engine/orchestrator.py` (the structural block ~line 1834-1880, added in S4)

- [ ] **Step 0: Locate the block**

Run: `cd backend && grep -n "structural.proposal\|structural.arbiter\|judge_structural_change\|structural_change_proposed" engine/orchestrator.py`
Expected: the `if director_result.structural_change_proposed:` block (the S4 arbiter+commit block). Replace it whole in Step 1.

- [ ] **Step 1: Replace with the detector block**

In `backend/engine/orchestrator.py`, replace the entire `if director_result.structural_change_proposed:` block (the one that calls `judge_structural_change`) with:

```python
        # Structural evolution (spec 2026-06-03 redesign). Free mode only: if the
        # Director flagged this turn as touching world底色, a post-turn detector
        # reads what the world ACTUALLY produced (npc_actions + narration) and
        # commits a structural change only if the world enacted one. The player's
        # claim is never authoritative — fabricated claims the NPCs rebutted leave
        # nothing to detect. Faithful reader: it does not re-judge legitimacy.
        if (
            game_mode == "free"
            and director_result.structural_in_play
            and settings.structural_free_detector_enabled
        ):
            from engine.prompts import render_npc_actions_for_narrator
            from engine.structural_detector import detect_structural_change
            from engine.structural_ledger import commit_structural_fact

            _detection = await detect_structural_change(
                self.npc_llm_router,
                npc_actions_text=render_npc_actions_for_narrator(sorted_actions),
                narration="".join(narrative_parts),
                player_input=user_input,
            )
            _committed = False
            if _detection.get("changed"):
                _committed = commit_structural_fact(
                    game_state, dict(_detection, provenance="free_detector")
                )
            logger.info(
                "structural.detector",
                session_id=session_id,
                round_number=round_number,
                changed=_detection.get("changed"),
                kind=_detection.get("kind"),
                committed=_committed,
            )
```

> `sorted_actions`, `narrative_parts`, `user_input`, `session_id`, `round_number`, `game_mode` are all in scope at this point (defined earlier in the same turn method). Confirm `user_input` is the method's player-input param name via Step 0's surrounding context; if it differs, use the actual name.

- [ ] **Step 2: Verify import + no syntax error**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "import engine.orchestrator; print(\"OK\")"'`
Expected: `OK`.

- [ ] **Step 3: Regression**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -m pytest tests/test_structural_detector.py tests/test_structural_ledger.py tests/test_structural_milestones.py tests/test_director_agent.py tests/test_prompts.py -q 2>&1 | tail -4'`
Expected: PASS.

- [ ] **Step 4: Commit** (confirm first) — `git add backend/engine/orchestrator.py` + message `feat(engine): wire post-turn structural detector (replaces free-mode arbiter)`.

---

## Task 6: Delete the arbiter (now unreferenced)

**Files:** Delete `backend/engine/structural_arbiter.py`, `backend/tests/test_structural_arbiter.py`

- [ ] **Step 1: Confirm no references remain**

Run: `cd backend && grep -rn "structural_arbiter\|judge_structural_change\|structural_change_proposed" engine/ services/ --include=*.py | grep -v test_`
Expected: **no output** (all production references removed by Tasks 2 & 5).

- [ ] **Step 2: Delete the files**

```bash
rm backend/engine/structural_arbiter.py backend/tests/test_structural_arbiter.py
```

- [ ] **Step 3: Verify nothing imports them**

Run: `docker exec talealive-backend-1 sh -c 'cd /app && python -c "import engine.orchestrator; print(\"OK\")" && python -m pytest tests/test_structural_detector.py tests/test_structural_ledger.py tests/test_structural_milestones.py tests/test_director_agent.py tests/test_prompts.py -q 2>&1 | tail -3'`
Expected: `OK` + PASS.

- [ ] **Step 4: Commit** (confirm first) — `git rm` the two files + message `chore(engine): remove free-mode structural arbiter (superseded by detector)`.

---

## Task 7: Real-run verification (faithful read: enacted vs rebutted)

- [ ] **Step 1:** Throwaway harness (delete after). Free-mode council-ship world. Two real `DirectorAgent.run_v2` + the orchestrator's exact detector gate (mirror Task 5):
  - **Enacted:** context establishes the council voted; player declares captaincy; NPCs (里夫斯) actually confirm/announce the appointment in their output. Feed `render_npc_actions_for_narrator(actions)` + narration to `detect_structural_change` → expect `changed=true` → `commit_structural_fact` → `structural_facts` gains the role change.
  - **Fabricated:** player claims "我已奉旨继位" with no backing; NPCs rebut (emperor: 朕从未下旨). Feed the rebuttal output to the detector → expect `changed=false` → no commit.
- [ ] **Step 2:** Capture both; verdict PASS only if enacted commits and fabricated does not. (This is the core claim: detection follows the world's recorded output, not the player's words.)
- [ ] **Step 3:** Remove the harness.

> Full orchestrator-path unit tests remain blocked by the pre-existing `FakeDirectorAgent.run_v2` stale fixture; detector parse/read are unit-covered (Task 4), commit is covered (S3), and this real-run covers the seam.

---

## Self-Review (plan-write time)

**Spec coverage:** §3.1 slim Director + keep reaction-setup → Tasks 2,3; §3.2 detector (free-only, post-turn, reads npc_actions+narration, faithful) → Tasks 4,5; §3.4 delete arbiter → Task 6; §6 migration table → Tasks 1–6; flag rename → Task 1; §7 cross-genre + real-run → Tasks 4,7; §3.3 script milestones unchanged → not touched (correct). §1.3 "detector never re-judges legitimacy" → DETECTOR_SYSTEM asks only "did the world enact it", no plausibility check.

**Placeholder scan:** none. Tasks 5 Step-0 grep pins the block; Step-1 notes the `user_input` name check.

**Type consistency:** detection dict keys `{changed, fact_key, fact_text, kind, target_ref}` consistent across `parse_detection`/`detect_structural_change`/orchestrator; `commit_structural_fact(state, fact)` + `provenance="free_detector"` match S3 ledger shape; `structural_in_play: bool` consistent across DirectorResult/parse/tool-schema/prompt/orchestrator; `render_npc_actions_for_narrator(sorted_actions)` is the existing prompts helper.

**Genre-neutrality:** DETECTOR_SYSTEM is world-output-general (no genre/authority assumption); tests use sci-fi (captain) + palace (decree) + (role/relation kinds) → ≥3 genres.
```
