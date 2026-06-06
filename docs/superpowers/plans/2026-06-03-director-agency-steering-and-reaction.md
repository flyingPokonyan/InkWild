# Director Agency: Steering + Structural Reaction (S1+S2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Director actively steer lost players (problem ①) and make the world *react* to — never silently absorb — structural assertions (problem ②), with **zero new persistent state**.

**Architecture:** Pure Director-behavior + orchestrator wiring. Add an optional `structural_change_proposed` field to `DirectorResult` (schema + parse). Augment the Director v2 system prompt: (S1) re-grant proactive *steering* (introduce world stimuli that re-surface the crux, without scripting player/NPC actions); (S2) detect player structural assertions and emit a graded `world_reaction`. The orchestrator feeds `world_reaction` to the narrator when a proposal is present and not (yet) supported. No commit path yet — that lands in Plan 2. This stage is the conservative half: the world never silently accepts a bare assertion; legit changes simply don't commit until Plan 2.

**Tech Stack:** Python 3.12, async, structlog, pytest. Files: `engine/director_agent.py`, `engine/prompts.py`, `engine/orchestrator.py`.

> **Repo note:** This repo currently has **0 commits** and a large uncommitted working tree. Commit steps below `git add` ONLY the files each task touches. **Confirm commit strategy with the user before the first commit** (the user has not been committing; do not sweep the whole tree).

> **Spec:** [`../specs/2026-06-03-structural-evolution-pipeline-design.md`](../specs/2026-06-03-structural-evolution-pipeline-design.md) §3.1, §5, §6 (破绽1/2), §8 (S1, S2).

> **Tests run inside the backend container** (`talealive-backend-1`) per memory `director-decomposition-landed-2026-06-02`; from host: `docker exec talealive-backend-1 python -m pytest <path> -v`. If running on host directly, `cd backend && python -m pytest <path> -v`. Steps below show the host-relative path; prefix with the container exec if needed.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/engine/director_agent.py` | `DirectorResult` dataclass + `_coerce_*` + `_build_result_v2` | Add `structural_change_proposed` field, `_coerce_structural_proposal` helper, wire into v2 parse |
| `backend/engine/prompts.py` | `DIRECTOR_TOOL` schema + `build_director_system_v2` | Add tool property; add S1 steering block + S2 structural-assertion block |
| `backend/engine/orchestrator.py` | v2 turn pipeline | Feed `world_reaction` into narrator inputs + structlog the proposal |
| `backend/tests/test_director_agent.py` | Director parse tests | Add coercion + parse tests |
| `backend/tests/test_prompts.py` | Prompt-contract tests | Add S1/S2 prompt-content assertions |

**Genre-neutrality rule (spec §1.2, hard):** all prompt language and tests must use **genre-neutral wording**; test cases must span ≥3 genres (palace-intrigue, mystery, sci-fi/relationship). No genre-specific branches in code.

---

## Task 1: Add `structural_change_proposed` field + coercion helper

**Files:**
- Modify: `backend/engine/director_agent.py` (DirectorResult dataclass ~line 218-253; add static method near other `_coerce_*` ~line 321)
- Test: `backend/tests/test_director_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_director_agent.py`:

```python
from engine.director_agent import DirectorAgent, DirectorResult


def test_coerce_structural_proposal_none_for_non_dict_or_empty():
    assert DirectorAgent._coerce_structural_proposal(None) is None
    assert DirectorAgent._coerce_structural_proposal("我是皇后") is None
    assert DirectorAgent._coerce_structural_proposal({"fact_text": "   "}) is None


def test_coerce_structural_proposal_unsupported_assertion_keeps_reaction():
    # Bare player assertion, no cause: supported defaults False, reaction kept.
    out = DirectorAgent._coerce_structural_proposal(
        {"fact_text": "玩家自称已是这艘船的船长", "world_reaction": "老水手嗤笑了一声"}
    )
    assert out["supported"] is False
    assert out["fact_text"] == "玩家自称已是这艘船的船长"
    assert out["world_reaction"] == "老水手嗤笑了一声"
    assert out["target_ref"] is None
    assert out["in_world_cause"] == ""


def test_coerce_structural_proposal_supported_carries_cause():
    out = DirectorAgent._coerce_structural_proposal(
        {
            "fact_text": "议会正式选举艾拉为新议长",
            "kind": "entity_role_changed",
            "target_ref": "艾拉",
            "supported": True,
            "in_world_cause": "三大阵营投票通过",
            "justification": "过去数轮玩家促成了三方结盟，投票水到渠成",
            "world_reaction": "",
        }
    )
    assert out["supported"] is True
    assert out["kind"] == "entity_role_changed"
    assert out["target_ref"] == "艾拉"
    assert out["in_world_cause"] == "三大阵营投票通过"


def test_director_result_defaults_structural_proposal_none():
    assert DirectorResult().structural_change_proposed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_director_agent.py -k structural -v`
Expected: FAIL — `AttributeError: type object 'DirectorAgent' has no attribute '_coerce_structural_proposal'` (and `DirectorResult` has no `structural_change_proposed`).

- [ ] **Step 3a: Add the dataclass field**

In `backend/engine/director_agent.py`, in the `DirectorResult` dataclass, after `event_fire_intent` (line ~253):

```python
    event_fire_intent: list[str] = field(default_factory=list)

    # Structural evolution (spec §3.1). Optional: present only when the Director
    # detects a structural change is being attempted/claimed. In this stage
    # (Plan 1) there is NO commit path — `supported=False` proposals surface a
    # graded `world_reaction`; `supported=True` proposals are logged but not yet
    # applied (Plan 2 adds the arbiter + ledger). Keys: fact_key, fact_text,
    # kind, target_ref, supported, in_world_cause, justification, world_reaction.
    structural_change_proposed: dict | None = None
```

- [ ] **Step 3b: Add the coercion helper**

In `backend/engine/director_agent.py`, next to the other `_coerce_*` static methods (after `_coerce_optional_dict`, ~line 323):

```python
    @staticmethod
    def _coerce_structural_proposal(value: object) -> dict | None:
        """Normalize the optional structural_change_proposed payload (spec §3.1).

        Conservative: returns None unless a non-empty `fact_text` is present.
        `supported` defaults False (a structural change is never assumed
        legitimate from the Director's say-so alone — the arbiter verifies in
        Plan 2). All scalar fields coerced to str; target_ref normalized to
        None when blank. Genre-neutral: no assumptions about fact category.
        """
        if not isinstance(value, dict):
            return None
        fact_text = str(value.get("fact_text") or "").strip()
        if not fact_text:
            return None
        return {
            "fact_key": str(value.get("fact_key") or "").strip(),
            "fact_text": fact_text,
            "kind": str(value.get("kind") or "").strip(),
            "target_ref": (str(value.get("target_ref") or "").strip() or None),
            "supported": bool(value.get("supported")),
            "in_world_cause": str(value.get("in_world_cause") or "").strip(),
            "justification": str(value.get("justification") or "").strip(),
            "world_reaction": str(value.get("world_reaction") or "").strip(),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_director_agent.py -k structural -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** (confirm with user first — see repo note)

```bash
git add backend/engine/director_agent.py backend/tests/test_director_agent.py
git commit -m "feat(engine): add structural_change_proposed to DirectorResult + coercion

Optional Director output describing a structural change being attempted/
claimed. supported defaults False (arbiter verifies later). No commit path
yet — Plan 1 surfaces world_reaction only.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Wire the field into `_build_result_v2` + add tool schema property

**Files:**
- Modify: `backend/engine/director_agent.py` (`_build_result_v2` return, ~line 505-534)
- Modify: `backend/engine/prompts.py` (`DIRECTOR_TOOL` schema, after `event_fire_intent` ~line 282)
- Test: `backend/tests/test_director_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_director_agent.py`:

```python
def test_build_result_v2_parses_structural_proposal():
    agent = DirectorAgent(llm_router=None)
    tool_input = {
        "scene_brief": "玩家在议事厅宣称自己已是议长",
        "active_npcs": [],
        "structural_change_proposed": {
            "fact_text": "玩家自称已是议长",
            "world_reaction": "书记官皱眉，没有起身行礼",
        },
    }
    result = agent._build_result_v2(
        tool_input, None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set()
    )
    assert result.structural_change_proposed is not None
    assert result.structural_change_proposed["supported"] is False
    assert result.structural_change_proposed["world_reaction"].startswith("书记官")


def test_build_result_v2_structural_proposal_absent_is_none():
    agent = DirectorAgent(llm_router=None)
    result = agent._build_result_v2(
        {"scene_brief": "平静的午后", "active_npcs": []},
        None, known_npcs=set(), known_event_ids=set(), fired_event_ids=set(),
    )
    assert result.structural_change_proposed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_director_agent.py -k "build_result_v2_parses_structural or build_result_v2_structural" -v`
Expected: FAIL — `result.structural_change_proposed` is `None` even when supplied (field not parsed).

- [ ] **Step 3a: Wire the parse**

In `backend/engine/director_agent.py`, in `_build_result_v2`'s `return DirectorResult(...)` (~line 533), after `event_fire_intent=event_intent,`:

```python
            event_fire_intent=event_intent,
            structural_change_proposed=self._coerce_structural_proposal(
                tool_input.get("structural_change_proposed")
            ),
```

- [ ] **Step 3b: Add the tool schema property**

In `backend/engine/prompts.py`, in the `DIRECTOR_TOOL` properties, after the `event_fire_intent` property (closes ~line 282):

```python
            "structural_change_proposed": {
                "type": "object",
                "description": (
                    "仅当本回合出现『世界底色（结构事实）层面的改变』被尝试/声称时才填，"
                    "否则省略。结构事实=身份/地位、存在/在场（生死/去留）、权力/归属/关系定性、"
                    "重大世界真相——即那些被设定为固定、平时不会变的东西。"
                    "普通的情绪/线索/位置变化【不要】填这里。"
                ),
                "properties": {
                    "fact_text": {"type": "string", "description": "用人话描述这条结构改变"},
                    "fact_key": {"type": "string", "description": "稳定键，如 character.role / entity.alive"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "entity_removed",
                            "entity_role_changed",
                            "relation_redefined",
                            "world_fact_changed",
                        ],
                        "description": "机械后果类型（题材无关）",
                    },
                    "target_ref": {"type": "string", "description": "涉及的实体名（world_fact 可空）"},
                    "supported": {
                        "type": "boolean",
                        "description": (
                            "以这个世界的既定逻辑（涉及角色的性格/动机 + 设定规则 + 已发生的因果），"
                            "此刻这个改变是否有足够且自洽的『世界内因』。"
                            "【仅凭玩家一句声称】=false；有真实的人物/事件促成=true。"
                        ),
                    },
                    "in_world_cause": {"type": "string", "description": "supported=true 时必填：哪个角色/事件促成"},
                    "justification": {"type": "string", "description": "依据：为什么世界逻辑支持/不支持"},
                    "world_reaction": {
                        "type": "string",
                        "description": (
                            "supported=false 时填：世界对这个未被支撑的声称的【分级】反应。"
                            "有该在意的角色→该角色按其性格反对/惊疑/上报；"
                            "无对抗角色（独处/日常场景）→环境/叙事层面的不予承认。"
                        ),
                    },
                },
            },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_director_agent.py -k structural -v`
Expected: PASS (all structural tests).

- [ ] **Step 5: Run the existing director suite for regressions**

Run: `cd backend && python -m pytest tests/test_director_agent.py tests/test_director_validator.py -v`
Expected: PASS (no regressions; pre-existing failures unrelated to this change per memory `backend-test-suite-preexisting-failures` — confirm none mention structural/this change).

- [ ] **Step 6: Commit** (confirm with user first)

```bash
git add backend/engine/director_agent.py backend/engine/prompts.py backend/tests/test_director_agent.py
git commit -m "feat(engine): parse structural_change_proposed from Director tool output

Add DIRECTOR_TOOL schema property + wire _build_result_v2.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: S1 — Director prompt re-grants proactive steering

**Files:**
- Modify: `backend/engine/prompts.py` (`build_director_system_v2`: the `narrative_pressure` section ~line 894-898 and the `player_input_weak` block ~line 948-963)
- Test: `backend/tests/test_prompts.py`

**Why:** The current `player_input_weak` block (prompts.py:948) over-restricts ("严禁让 NPC 替玩家完成动作" + intensity ≤ medium + ≤1 NPC). It already says "世界不能停摆" but doesn't tell the Director to *actively steer toward the crux*. S1 adds steering while keeping the no-script-player-action guardrail (spec §5). Genre-neutral wording — no "case"/"凶手" specific.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_prompts.py`:

```python
from engine.prompts import build_director_system_v2


def _build(**kw):
    base = dict(
        base_setting="一个测试世界", script_setting="", npc_descriptions="（无）",
        ending_conditions="", game_mode="free",
    )
    base.update(kw)
    return build_director_system_v2(**base)


def test_v2_prompt_grants_steering_on_weak_input():
    prompt = _build(player_input_weak=True)
    # Steering directive present: actively introduce a crux-relevant stimulus.
    assert "主动" in prompt and "刺激" in prompt
    # Guardrail retained: must not script the player's actions.
    assert "替玩家" in prompt


def test_v2_prompt_steering_is_genre_neutral():
    prompt = _build(player_input_weak=True)
    # No genre-specific vocabulary baked into the steering directive.
    for word in ("凶手", "案件", "嫔妃", "皇后"):
        assert word not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prompts.py -k "steering" -v`
Expected: FAIL — `assert "主动" in prompt and "刺激" in prompt` fails (steering directive not yet present).

- [ ] **Step 3: Add the steering directive**

In `backend/engine/prompts.py`, replace the `player_input_weak` block (currently ~line 948-963) with an augmented version that adds steering:

```python
    if player_input_weak:
        parts.extend(
            [
                "",
                "## ⚠️ 本回合玩家输入很弱（player_input_weak）",
                "玩家本轮只输入了简短/纯观察的内容。**严禁替玩家完成未声明的动作**。",
                "- dramatic_intensity 必须 ≤ medium",
                "- active_npcs 最多 1 人",
                "- per_npc_focus 不要暗示 NPC 主动行动",
                "- 让叙事以环境 + 玩家 POV 感官为主",
                "",
                "### 但你要【主动推世界】，别只描述",
                "玩家卡住/跑偏时，你的职责是把他温和拽回当前的核心张力，"
                "做法是【投放一个客观的世界刺激】，而不是替他行动、也不是命令 NPC：",
                "- 让一个相关 NPC 带着自身理由靠近、出现、或抛出一句话；",
                "- 推进一条环境线索 / 后台事件 / 时间流逝，让局势自己往前挪一格；",
                "- 把当前最该被注意的张力点，以客观感官的方式重新摆到玩家面前。",
                "这是『推世界』≠『推玩家』：你提供刺激，玩家仍然自己决定怎么回应。",
                "- 若玩家在观察，至少回报一条具体的感官新发现（看到/听到/闻到），"
                "可写进 state_updates.new_clues",
            ]
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_prompts.py -k "steering" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the prompt suite for regressions**

Run: `cd backend && python -m pytest tests/test_prompts.py tests/test_prompts_stable_prefix.py -v`
Expected: PASS (the weak block is in the dynamic suffix, not the cached prefix — stable-prefix tests unaffected).

- [ ] **Step 6: Commit** (confirm with user first)

```bash
git add backend/engine/prompts.py backend/tests/test_prompts.py
git commit -m "feat(prompts): S1 — Director proactively steers lost players via world stimuli

Augment player_input_weak block: push the world (NPC approach / env clue /
time) to re-surface the crux, without scripting the player or commanding NPCs.
Genre-neutral.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: S2 — Director prompt detects structural assertions + graded reaction

**Files:**
- Modify: `backend/engine/prompts.py` (`build_director_system_v2`: add a static rules block in the stable-prefix region, after the "行为规则" block ~line 893)
- Test: `backend/tests/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_prompts.py`:

```python
def test_v2_prompt_has_structural_assertion_rules():
    prompt = _build()
    # Instructs the Director on structural assertions + graded reaction.
    assert "结构" in prompt and "structural_change_proposed" in prompt
    assert "不予承认" in prompt  # environmental non-recognition for no-actor scenes


def test_v2_prompt_structural_rules_present_in_both_modes():
    assert "structural_change_proposed" in _build(game_mode="free")
    assert "structural_change_proposed" in _build(game_mode="script", script_setting="秘密")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prompts.py -k "structural_assertion or structural_rules" -v`
Expected: FAIL — `"structural_change_proposed" in prompt` is False.

- [ ] **Step 3: Add the structural-assertion rules block**

In `backend/engine/prompts.py`, in `build_director_system_v2`, inside the big static `parts.extend([...])` that ends with the `narrative_pressure` section, insert this block right after the "## 行为规则" list and before "## 节奏控制（narrative_pressure）" (~line 893). Add these list items:

```python
            "",
            "## 世界底色（结构事实）的改变",
            "结构事实=身份/地位、存在/在场（生死/去留）、权力/归属/关系定性、重大世界真相——"
            "被设定为固定、平时不会变的东西。规则：",
            "- **世界底色只通过世界自身逻辑改变。** 玩家【声称】一个结构改变（如自称掌权、自称某人已死、"
            "自称与某人结盟）≠ 它就发生了。要发生，必须有这个世界里的人或事、按其既定逻辑真的促成它。",
            "- 当本回合出现结构改变被尝试/声称时，填 `structural_change_proposed`（见工具字段）：",
            "  · 以世界既定逻辑（涉及角色的性格/动机 + 设定规则 + 已发生的因果）判断 `supported`；",
            "  · 仅凭玩家一句声称、没有真实世界内因 → `supported=false`，并给出【分级】`world_reaction`："
            "有该在意的角色就让该角色按其性格反对/惊疑/上报；没有对抗角色的场景（独处/日常）"
            "就让环境/叙事层面【不予承认】（这件事悬在那里，世界没有照它转）。",
            "  · 确有人物/事件促成 → `supported=true`，写清 `in_world_cause` 与 `justification`。",
            "- 普通的情绪/线索/位置/物品变化【不是】结构事实，照常走 state_updates，不要填这里。",
```

> Note: this block is **genre-neutral** and lives in the stable prefix (same content every turn) so prefix-cache still hits.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_prompts.py -k "structural_assertion or structural_rules" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run prompt + stable-prefix suite**

Run: `cd backend && python -m pytest tests/test_prompts.py tests/test_prompts_stable_prefix.py -v`
Expected: PASS. If `test_prompts_stable_prefix` asserts an exact prefix snapshot, update its expected snapshot to include the new static block (the block is intentionally in the stable prefix).

- [ ] **Step 6: Commit** (confirm with user first)

```bash
git add backend/engine/prompts.py backend/tests/test_prompts.py
git commit -m "feat(prompts): S2 — Director detects structural assertions, emits graded reaction

World底色 changes only through in-world causes (philosophy A). Bare player
assertions get supported=false + a graded world_reaction (actor pushback, or
environmental non-recognition when no actor cares). Genre-neutral, stable-prefix.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Orchestrator — surface `world_reaction` to the narrator + log proposals

**Files:**
- Modify: `backend/engine/orchestrator.py` (v2 turn path, where `director_result` is available and `narrator_inputs` is assembled — confirmed symbols: `narrator_inputs` dict gets `narrative_pressure` at ~line 1696/1754)
- Modify: `backend/engine/prompts.py` (narrator prompt builder — locate via grep in Step 0)
- Test: `backend/tests/test_orchestrator.py` (or `tests/test_orchestrator_v2_loading.py` style in-process test)

- [ ] **Step 0: Locate the narrator wiring points**

Run:
```bash
cd backend && grep -n "narrator_inputs\[" engine/orchestrator.py
grep -n "def build_narrator\|scene_direction\|narrative_pressure" engine/prompts.py | head
```
Expected: shows where `narrator_inputs["scene_direction"]` / `["narrative_pressure"]` are set (orchestrator) and the narrator prompt builder that consumes them (prompts.py). Use these exact locations in Steps 3a/3b.

- [ ] **Step 1: Write the failing test**

Add an in-process test (no real LLM) to `backend/tests/test_orchestrator.py`. Mirror the existing in-process orchestrator test setup in that file (fake director returning a `DirectorResult`, assert on narrator inputs). Skeleton:

```python
def test_world_reaction_passed_to_narrator_when_unsupported(monkeypatch):
    """An unsupported structural proposal's world_reaction reaches the narrator."""
    from engine.prompts import build_narrator_user  # adjust to the real builder name from Step 0
    reaction = "守卫纹丝不动，仿佛没听见这句话"
    rendered = build_narrator_user(  # call the narrator builder with world_reaction set
        scene_direction="玩家在城门口高声宣称自己是新任城主",
        narrative_pressure="advance",
        world_reaction=reaction,
        # ...other required args with minimal valid values per the real signature
    )
    assert reaction in rendered
```

> If the narrator builder signature differs, adapt the call to its real parameters (from Step 0); the assertion (reaction text appears in the rendered narrator prompt) is the contract.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -k world_reaction -v`
Expected: FAIL — `build_narrator_*` has no `world_reaction` parameter / reaction not rendered.

- [ ] **Step 3a: Render `world_reaction` in the narrator prompt**

In `backend/engine/prompts.py`, in the narrator builder identified in Step 0, add an optional `world_reaction: str = ""` parameter and, when non-empty, append a block instructing the narrator to weave the world's pushback into the prose, e.g.:

```python
    if world_reaction:
        parts.extend([
            "",
            "## 世界的反应（必须自然写进本段叙事）",
            "玩家本回合试图断言一个世界底色层面的改变，但世界并不认可。"
            "把下面这条反应自然融入叙事——不要让那个改变显得已经发生：",
            world_reaction,
        ])
```

- [ ] **Step 3b: Pass `world_reaction` from the orchestrator**

In `backend/engine/orchestrator.py`, where `narrator_inputs` is assembled (Step 0 location, near the `narrative_pressure` assignment), add:

```python
        proposal = director_result.structural_change_proposed
        if proposal and not proposal.get("supported") and proposal.get("world_reaction"):
            narrator_inputs["world_reaction"] = proposal["world_reaction"]
```

And ensure the narrator builder call passes `world_reaction=narrator_inputs.get("world_reaction", "")`.

- [ ] **Step 3c: Log every proposal (observability)**

In `backend/engine/orchestrator.py`, right after `director_result` is produced in the v2 path, add:

```python
        if director_result.structural_change_proposed:
            _p = director_result.structural_change_proposed
            logger.info(
                "structural.proposal",
                supported=_p.get("supported"),
                kind=_p.get("kind"),
                fact_key=_p.get("fact_key"),
                has_reaction=bool(_p.get("world_reaction")),
                committed=False,  # Plan 1 has no commit path
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -k world_reaction -v`
Expected: PASS.

- [ ] **Step 5: Run orchestrator suite for regressions**

Run: `cd backend && python -m pytest tests/test_orchestrator.py tests/test_orchestrator_v2_loading.py tests/test_orchestrator_early_stream.py -v`
Expected: PASS (pre-existing unrelated failures per memory may persist — confirm none are caused by this change; the `FakeDirectorAgent` fixtures lacking `run_v2` are a known stale-fixture issue, not introduced here).

- [ ] **Step 6: Commit** (confirm with user first)

```bash
git add backend/engine/orchestrator.py backend/engine/prompts.py backend/tests/test_orchestrator.py
git commit -m "feat(engine): surface unsupported structural reaction to narrator + log proposals

Orchestrator feeds world_reaction into narrator inputs when a structural
proposal is unsupported; structlog every proposal (committed=False this stage).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Genre-neutrality cross-check (no new code — verification gate)

**Files:** none (review + one consolidated test file already covers ≥3 genres via Tasks 1, 3, 5).

- [ ] **Step 1: Confirm cross-genre coverage**

Run: `cd backend && python -m pytest tests/test_director_agent.py tests/test_prompts.py tests/test_orchestrator.py -k "structural or steering or world_reaction" -v`
Expected: PASS. Confirm the test bodies reference ≥3 genres (palace-intrigue 皇后, mystery 船长/城主, sci-fi/relationship 议长/结盟) and that **no production code added in this plan contains a genre-specific branch** (grep below).

- [ ] **Step 2: Grep for accidental genre coupling**

Run:
```bash
cd backend && grep -n "凶手\|嫔妃\|案件\|后宫" engine/director_agent.py engine/orchestrator.py | grep -i "structural\|world_reaction" || echo "OK: no genre coupling in new structural code"
```
Expected: `OK: no genre coupling in new structural code`.

- [ ] **Step 3: Final full-suite smoke (changed modules)**

Run: `cd backend && python -m pytest tests/test_director_agent.py tests/test_prompts.py tests/test_prompts_stable_prefix.py tests/test_orchestrator.py -v`
Expected: PASS / only pre-existing unrelated failures.

---

## Self-Review (done at plan-write time)

**Spec coverage:** S1 steering → Task 3 ✓; S2 reject+reaction → Tasks 2,4,5 ✓; §3.1 proposal field → Tasks 1,2 ✓; §6 破绽1 (genre-neutral judge wording) → Task 4 prompt + Task 6 ✓; §6 破绽2 (graded reaction incl. environmental non-recognition) → Task 4 (`不予承认`) + Task 5 ✓. Out of scope for Plan 1 (deferred to Plan 2): account/overlay/cascade/condition_tree/free-mode judge — correctly absent.

**Placeholder scan:** No TBD/TODO. Task 5 uses a Step-0 grep to pin the narrator builder name/signature (a real "how", not a placeholder) because that symbol wasn't read at plan time.

**Type consistency:** `structural_change_proposed` dict keys (`fact_key, fact_text, kind, target_ref, supported, in_world_cause, justification, world_reaction`) are identical across Tasks 1 (helper), 2 (parse/schema), 5 (orchestrator read). `supported` is bool everywhere; `world_reaction` is the field read in Task 5.

**Genre-neutrality:** enforced by Task 4 wording + Task 6 grep gate + ≥3-genre test cases.
