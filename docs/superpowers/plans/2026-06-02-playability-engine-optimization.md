# 可玩性评测优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉 2026-06-02 甄嬛传可玩性评测暴露的引擎短板——两个 P0（导演 climax JSON 截断导致软失败 + 结局信号丢失）、结局三层退化、导演弱输入惰性，以及若干 P2 健壮性/边界问题。

**Architecture:** 先打通可观测（finish_reason）让截断可见，再用「四招组合拳」根治 §1 截断：①usage 事件补 `finish_reason` → ②retry 在 truncated 时抬 max_tokens 自愈 → ③末次失败用 `try_partial_parse` 抢救部分 JSON → ④`ending_triggered` schema 前移让它在膨胀字段前就闭合。结局 AI 层（§3）靠这套自动复活，加端到端验证锁定。其余 §4/§5 为 prompt 软约束 + 健壮性收尾，独立并行。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest（异步），structlog；LLM 经 `LLMRouter` + provider 抽象（deepseek / openai_compatible / grok）。

**关键约束（执行者必读）：**
- **评测期绝不能改 `backend/*.py`**：栈跑在 `uvicorn --reload`，改 .py 会热重启掐断在飞 SSE → 误报。**本计划所有验证用 pytest 单测 + in-process，不在评测中边改边测。** 最终全量评测另起独立实例 / 关 reload。
- 统一响应包裹 `{"code":0,"data":...,"message":"ok"}`；日志用 `structlog` 不用 `print`；类型标注必写，`str | None` 不用 `Optional`。
- LLM 调用走 `LLMRouter`，不硬编码 provider/model。
- 测试落点：`backend/tests/`，命名 `test_*.py`，异步用 `pytest.mark.asyncio`（看现有 `test_director_json_robustness.py` 风格）。
- 每个 task 跑测只跑该 task 涉及的文件（全量 pytest 有 ~56 个 pre-existing 失败，与本改动无关，见记忆 `backend-test-suite-preexisting-failures`）。
- 提交前确认在个人 git 身份下（inkwild 已 git init，remote=github-personal）。

**任务依赖图：**
```
Task 0 (harness)  ─── 独立，先做（下轮评测才准）
Task 1 (finish_reason) ──┬─> Task 2 (truncated 自愈)
                         └─> Task 6 (结局层验证) 依赖 1+3+4
Task 3 (ending 前移) ─────┘
Task 4 (抢救 partial) ────┘
Task 5 (case_board tail) ── 条件触发：仅当 Task1 观测显示 finish_reason=length/输出过大
Task 7/8/9/10 ── 独立并行收尾
```

---

## Task 0: 修评测 harness 的结局判定字段（§6）

**为什么先做：** 当前 harness 用 `ending_triggered` 字段判结局，但 forced 结局不写该字段 → 误报「故事收不了尾」。不先修，下一轮验证还是测不准。

**Files:**
- Modify: `backend/eval/examples/playability_judge.py`（`_progression` 函数 + `capture_session` 附带 status）

- [ ] **Step 1: 定位现状**

Run: `grep -n "_progression\|ending_triggered\|def capture_session\|status" backend/eval/examples/playability_judge.py`
Expected: 看到 `_progression` 内用 `ending_triggered` 判 ended，`capture_session` 未附 `status`。

- [ ] **Step 2: 写失败测试**

Create/Modify: `backend/tests/test_playability_judge_progression.py`

```python
from eval.examples.playability_judge import _progression


def test_progression_reads_session_status_not_ending_triggered():
    # forced 结局：status=ended 但 ending_triggered 缺失 → 必须判为已收束
    captured = {"status": "ended", "rounds": 12, "ending_triggered": None}
    assert _progression(captured)["ended"] is True


def test_progression_playing_when_status_not_ended():
    captured = {"status": "playing", "rounds": 9, "ending_triggered": None}
    assert _progression(captured)["ended"] is False
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_playability_judge_progression.py -v`
Expected: FAIL（`_progression` 仍读 `ending_triggered`，或 KeyError `status`）。

- [ ] **Step 4: 改 `_progression` 读 `status`，`capture_session` 附带 `status`**

`_progression` 判定改为 `captured.get("status") == "ended"`；`capture_session` 在返回 dict 里加入 `"status": session.status`（从 `game_sessions` 行读）。保留 `ending_triggered` 字段供「path=ai 比例」统计，但不再用于 ended 判定。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_playability_judge_progression.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 6: 提交**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/eval/examples/playability_judge.py backend/tests/test_playability_judge_progression.py
git commit -m "fix(eval): judge progression by session.status not ending_triggered"
```

---

## Task 1: usage 事件补 `finish_reason`（§2，打通可观测）

**为什么：** 现在只有 `deepseek.py` 通过 `_build_usage_event` 填 `finish_reason`；线上 provider 走 `openai_compatible.py`（usage @155）和 `grok.py`（usage @134）都没填 → `director_agent.py:1019` 永远读到 None → `:1031` 的 truncated 判断是死代码，引擎对自己的截断全瞎。

**做法（DRY）：** 把 `deepseek.py:_build_usage_event` 提成公用函数，三个 provider 共用；在 openai_compatible / grok 的 chunk 循环里捕获 `choice.finish_reason`。

**Files:**
- Create: `backend/llm/_usage.py`（公用 `build_usage_event`）
- Modify: `backend/llm/deepseek.py:16-49`（删本地 `_build_usage_event`，改 import 公用的）
- Modify: `backend/llm/openai_compatible.py:107-177`（捕获 finish_reason + 用公用函数）
- Modify: `backend/llm/grok.py`（chunk 循环捕获 finish_reason + 用公用函数）
- Test: `backend/tests/test_openai_compatible_finish_reason.py`、`backend/tests/test_grok_provider.py`

- [ ] **Step 1: 抽公用函数**

Create `backend/llm/_usage.py`，把 `deepseek.py:16-49` 的 `_build_usage_event` 整体搬过来，重命名为 `build_usage_event`（去掉前导下划线，因为跨模块）：

```python
"""Shared usage-event builder for streaming LLM providers.

Surfaces prefix-cache fields and ``finish_reason`` ("stop"|"length"|…) so the
director can detect truncation (the only signal when JSON-mode output is cut at
max_tokens) and so cost/cache accounting stays uniform across providers.
"""
from __future__ import annotations


def build_usage_event(usage, finish_reason: str | None = None) -> dict:
    event: dict = {
        "type": "usage",
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }
    if finish_reason is not None:
        event["finish_reason"] = finish_reason
    if usage is not None:
        hit = getattr(usage, "prompt_cache_hit_tokens", None)
        miss = getattr(usage, "prompt_cache_miss_tokens", None)
        if hit is None:
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                cached = getattr(details, "cached_tokens", None)
                if cached is not None:
                    hit = int(cached)
                    miss = max(int(event["input_tokens"]) - hit, 0)
        if hit is not None:
            event["cache_hit_tokens"] = int(hit)
        if miss is not None:
            event["cache_miss_tokens"] = int(miss)
    return event
```

- [ ] **Step 2: 写失败测试（openai_compatible 透传 finish_reason）**

Create `backend/tests/test_openai_compatible_finish_reason.py`：

```python
"""openai_compatible / grok 的 usage 事件必须透传 finish_reason，
否则 director 的截断检测（director_agent.py:1031）是死代码。"""
from __future__ import annotations

import pytest

from llm._usage import build_usage_event


class _FakeUsage:
    prompt_tokens = 100
    completion_tokens = 50


def test_build_usage_event_surfaces_finish_reason_length():
    ev = build_usage_event(_FakeUsage(), finish_reason="length")
    assert ev["type"] == "usage"
    assert ev["finish_reason"] == "length"
    assert ev["input_tokens"] == 100
    assert ev["output_tokens"] == 50


def test_build_usage_event_omits_finish_reason_when_none():
    ev = build_usage_event(_FakeUsage(), finish_reason=None)
    assert "finish_reason" not in ev
```

加一个端到端流测试，断言 provider 把 chunk 的 finish_reason 透到 usage 事件。用 fake stream（仿 `test_director_json_robustness.py` 的脚本化 stream 风格）：

```python
class _FakeChoice:
    def __init__(self, content=None, finish_reason=None):
        self.delta = type("D", (), {"content": content, "tool_calls": None})()
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(self, choices, usage=None):
        self.choices = choices
        self.usage = usage


async def _fake_stream(chunks):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_openai_compatible_stream_emits_finish_reason(monkeypatch):
    from llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="x", base_url="http://x", model="m")
    chunks = [
        _FakeChunk([_FakeChoice(content='{"a":1}')]),
        _FakeChunk([_FakeChoice(finish_reason="length")], usage=_FakeUsage()),
    ]

    async def _fake_create(**kwargs):
        return _fake_stream(chunks)

    monkeypatch.setattr(provider.client.chat.completions, "create", _fake_create)

    events = [ev async for ev in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=[]
    )]
    usage = [e for e in events if e["type"] == "usage"][-1]
    assert usage["finish_reason"] == "length"
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_openai_compatible_finish_reason.py -v`
Expected: `build_usage_event` 用例 PASS（公用函数已建），但 `test_openai_compatible_stream_emits_finish_reason` FAIL（provider 尚未捕获 finish_reason）。

- [ ] **Step 4: 改 openai_compatible 捕获 finish_reason**

在 `openai_compatible.py` 的 `stream_with_tools` chunk 循环（107 起）顶部加 `finish_reason: str | None = None`，在 `for choice in ...` 内捕获（仿 deepseek.py:206-208）：

```python
for choice in getattr(chunk, "choices", []) or []:
    if getattr(choice, "finish_reason", None):
        finish_reason = choice.finish_reason
    delta = getattr(choice, "delta", None)
    ...
```

把 155-177 行手搓的 usage event dict 整段替换为：

```python
yield build_usage_event(usage, finish_reason)
```

并在文件顶部 `from llm._usage import build_usage_event`。

- [ ] **Step 5: 改 grok 捕获 finish_reason**

`grok.py` 同样：chunk 循环顶部 `finish_reason: str | None = None`，`for choice` 内捕获，把 134-138 的手搓 usage dict 换成 `yield build_usage_event(usage, finish_reason)`，顶部 import。

- [ ] **Step 6: deepseek 改用公用函数**

`deepseek.py`：删除本地 `_build_usage_event`（16-49），改 `from llm._usage import build_usage_event`，把 `:216` 的 `yield _build_usage_event(usage, finish_reason)` 改成 `yield build_usage_event(usage, finish_reason)`。

- [ ] **Step 7: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_openai_compatible_finish_reason.py tests/test_grok_provider.py tests/test_llm_router.py -v`
Expected: 全 PASS（含 grok 既有用例不回归）。

- [ ] **Step 8: 回归验证——usage 多一个 key 不破坏消费方**

usage 事件被 token_usage 记账消费。确认消费方按 key 取值、不假设 key 集合固定。

Run: `grep -rn "event\[.type.\] == .usage.\|cache_hit_tokens\|output_tokens" backend/engine backend/services | grep -i usage`
检查无「断言 usage event keys 完全相等」的脆弱代码。`finish_reason` 是可选 key，新增不影响既有取值。

Run: `cd backend && python -m pytest tests/test_orchestrator_timing.py -v`
Expected: PASS（计时/记账路径不回归）。

- [ ] **Step 9: 提交**

```bash
git add backend/llm/_usage.py backend/llm/deepseek.py backend/llm/openai_compatible.py backend/llm/grok.py backend/tests/test_openai_compatible_finish_reason.py
git commit -m "fix(llm): surface finish_reason on openai_compatible/grok usage events"
```

---

## Task 2: retry 在 truncated 时抬 max_tokens 自愈（§1 第二招）

**为什么：** Task 1 让 truncated 可见后，retry 循环（director_agent.py:680-692）仍只加文本反馈、**不抬 max_tokens**——若病因是 length，重试还是会被同样截断。要让 `_run_json_mode` 把失败原因（truncated/malformed/empty）回传 retry 循环，truncated 时下次用更高 max_tokens。

**Files:**
- Modify: `backend/engine/director_agent.py`（`_run_json_mode` 返回失败原因；retry 循环据此抬 max_tokens）
- Test: `backend/tests/test_director_json_mode.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_director_json_mode.py` 加用例：脚本化 router，第一次返回被 length 截断的 JSON（usage 带 `finish_reason="length"`），断言第二次调用收到的 `max_tokens` 高于第一次。

```python
@pytest.mark.asyncio
async def test_truncated_director_retries_with_higher_max_tokens():
    seen_max_tokens = []

    class _Router:
        def current_model_id(self): return "deepseek-v4-pro"
        async def stream_json(self, messages, system=None, max_tokens=2048, provider_offset=0):
            seen_max_tokens.append(max_tokens)
            if len(seen_max_tokens) == 1:
                yield {"type": "text_delta", "text": '{"scene_brief":"x"'}  # 截断
                yield {"type": "usage", "input_tokens": 10, "output_tokens": 8192,
                       "finish_reason": "length"}
            else:
                yield {"type": "text_delta", "text":
                       '{"scene_brief":"x","active_npcs":[],"per_npc_focus":{},'
                       '"scene_role":{},"dramatic_intensity":"low",'
                       '"scene_direction":"d","state_updates":{},'
                       '"quick_actions":[],"player_action":{"action_type":"wait","summary":"s"}}'}
                yield {"type": "usage", "input_tokens": 10, "output_tokens": 50,
                       "finish_reason": "stop"}

    agent = DirectorAgent(_Router())
    result = await agent._run_director_json_with_retry(...)  # 用现有入口名，见 Step 2
    assert len(seen_max_tokens) == 2
    assert seen_max_tokens[1] > seen_max_tokens[0]
```

> 注：实际入口是 `run_v2` 内的 retry for-loop（director_agent.py:631）。若直接测私有 retry 不便，改为通过 `run_v2` 驱动并用上面的 `_Router`。执行者按现有可调用入口对齐测试钩子。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_director_json_mode.py::test_truncated_director_retries_with_higher_max_tokens -v`
Expected: FAIL（两次 max_tokens 相同）。

- [ ] **Step 3: `_run_json_mode` 回传失败原因**

把 `_run_json_mode` 失败分支（director_agent.py:1026-1044）的 `return None` 改为 `return ("__fail__", reason)` 之类的判别返回，或更干净——让它 raise 一个带 `reason` 属性的内部异常。推荐后者：

```python
class _DirectorJsonFailure(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
```

`_run_json_mode` 在 `tool_input is None` 时 `raise _DirectorJsonFailure(reason)`（reason 取自现有 truncated/empty/malformed 判定）。成功仍 `return usage_data, tool_input`。

- [ ] **Step 4: retry 循环据 reason 抬 max_tokens**

在 `run_v2` 的 retry for-loop（631）加一个 `current_max_tokens = settings.director_json_max_tokens` 初值，把它传进 `_run_json_mode(..., max_tokens=current_max_tokens)`（给 `_run_json_mode` 加 `max_tokens` 参数，替掉内部写死的 `settings.director_json_max_tokens`）。catch `_DirectorJsonFailure`：

```python
except _DirectorJsonFailure as exc:
    if exc.reason == "truncated":
        current_max_tokens = min(current_max_tokens * 2, 16384)
        last_feedback = "- 上次输出被截断（length）。请更精炼，确保 JSON 完整闭合。"
    else:
        last_feedback = f"- 上次输出无法解析（{exc.reason}）。请直接产出合法 JSON 对象……"
    logger.warning("director.parse_failure_retrying", attempt=attempt + 1,
                   reason=exc.reason, next_max_tokens=current_max_tokens)
    continue
```

保留原 `DirectorParseError` catch 兼容 tool_use 路径。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_director_json_mode.py tests/test_director_json_robustness.py -v`
Expected: PASS（含既有健壮性用例不回归）。

- [ ] **Step 6: 提交**

```bash
git add backend/engine/director_agent.py backend/tests/test_director_json_mode.py
git commit -m "fix(director): raise max_tokens on truncated JSON-mode retry"
```

---

## Task 3: `ending_triggered` schema 前移（§1 第三招，确定性最强）

**为什么：** `ending_triggered` 在 DIRECTOR_TOOL_V2 properties 里排在 317 行（state_updates / quick_actions 之后、player_action 之前）。climax 时前置字段（per_npc_focus 按 NPC 膨胀 + state_updates）撑爆 ~2242 字符，截断发生在 ending_triggered 之前 → 信号丢失。LLM JSON 倾向按 properties 顺序输出，把 ending_triggered 移到 `scene_brief` 之后，能在膨胀字段前就闭合，配合 Task 4 的 partial 抢救可救回。

**Files:**
- Modify: `backend/engine/prompts.py:200-368`（DIRECTOR_TOOL_V2 properties 顺序 + required）
- Test: `backend/tests/test_prompts.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_prompts.py` 加：

```python
def test_v2_ending_triggered_precedes_bulky_fields():
    from engine.prompts import DIRECTOR_TOOL_V2
    keys = list(DIRECTOR_TOOL_V2["input_schema"]["properties"].keys())
    # ending_triggered 必须排在膨胀字段（per_npc_focus / state_updates）之前，
    # 这样 climax 截断时它已闭合、可被 partial 抢救。
    assert keys.index("ending_triggered") < keys.index("per_npc_focus")
    assert keys.index("ending_triggered") < keys.index("state_updates")
    # 但要排在 scene_brief 之后（模型先描述场景再判结局）
    assert keys.index("scene_brief") < keys.index("ending_triggered")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_prompts.py::test_v2_ending_triggered_precedes_bulky_fields -v`
Expected: FAIL。

- [ ] **Step 3: 把 `ending_triggered` 块移到 `scene_brief` 之后**

在 `prompts.py` 把 `ending_triggered` 整块（317-325）剪切，粘贴到 `scene_brief`（200-206）之后、`active_npcs`（207）之前。其 description 补一句：「**这是高优先字段，请尽早输出，不要等到 JSON 末尾。**」properties 其余顺序不变。

- [ ] **Step 4: 运行确认通过 + schema 合法性不回归**

Run: `cd backend && python -m pytest tests/test_prompts.py tests/test_prompts_stable_prefix.py tests/test_director_validator.py -v`
Expected: PASS。`test_prompts_stable_prefix` 确认稳定前缀缓存不被破坏（注意：ending_triggered 在 system 注入的 stable 前缀里若被影响则需复核；schema 本身不进 stable prefix，应无碍）。

- [ ] **Step 5: 提交**

```bash
git add backend/engine/prompts.py backend/tests/test_prompts.py
git commit -m "fix(director): move ending_triggered ahead of bulky schema fields"
```

---

## Task 4: 末次失败抢救部分 JSON（§1 第四招，兜底）

**为什么：** 即便前三招仍可能截断。`_run_json_mode` 末次 `tool_input is None` 时，直接丢弃整个回合。但流里往往已包含可解析的前缀（scene_brief / scene_direction / ending_triggered）。用现有 `try_partial_parse(raw)` 抢救前缀，至少让旁白能发、结局信号能保。

**Files:**
- Modify: `backend/engine/director_agent.py`（`_run_json_mode` 失败前抢救 + `_extract_json_from_text` 失败兜底）
- Test: `backend/tests/test_director_json_robustness.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_director_json_robustness.py` 加：截断 stream（ending_triggered 在前、player_action 缺失），断言抢救出 `scene_brief` 与 `ending_triggered`。

```python
@pytest.mark.asyncio
async def test_salvage_partial_recovers_ending_triggered():
    truncated = (
        '{"scene_brief":"皇后摔杯","ending_triggered":'
        '{"should_end":true,"ending_type":"good","reason":"真相大白"},'
        '"active_npcs":["皇后"],"per_npc_focus":{"皇后":"被当众揭穿'  # 中途截断
    )
    class _Router:
        def current_model_id(self): return "deepseek-v4-pro"
        async def stream_json(self, messages, system=None, max_tokens=2048, provider_offset=0):
            yield {"type": "text_delta", "text": truncated}
            yield {"type": "usage", "input_tokens": 10, "output_tokens": 8192,
                   "finish_reason": "length"}
    agent = DirectorAgent(_Router())
    salvaged = agent._salvage_partial(truncated)  # 见 Step 3
    assert salvaged is not None
    assert salvaged["scene_brief"] == "皇后摔杯"
    assert salvaged["ending_triggered"]["should_end"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_director_json_robustness.py::test_salvage_partial_recovers_ending_triggered -v`
Expected: FAIL（`_salvage_partial` 未定义）。

- [ ] **Step 3: 加 `_salvage_partial` + 在末次失败处调用**

`_salvage_partial` 复用 `try_partial_parse`，但剔除可能半截的最后一个 key（`try_partial_parse` 已按最后一个顶层逗号截断，本就丢弃半截尾项）：

```python
def _salvage_partial(self, raw: str) -> dict | None:
    """末次解析失败时，从截断流里抢救已完结的顶层字段子集。
    至少救回 scene_brief / scene_direction / ending_triggered，让旁白能发、
    结局信号不丢。case_board_ops 即便半截也会被 try_partial_parse 丢弃。"""
    cleaned = raw.lstrip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
    salvaged = try_partial_parse(cleaned)
    if not salvaged:
        return None
    # 至少要有 scene_brief 或 scene_direction 才算救回（否则旁白无依据）
    if not (salvaged.get("scene_brief") or salvaged.get("scene_direction")):
        return None
    return salvaged
```

在 `_run_json_mode` 的失败分支（Task 2 改成 raise `_DirectorJsonFailure` 处）之前先尝试抢救：若 `_salvage_partial(raw)` 成功，记 `logger.warning("director_v2.json_mode_salvaged", recovered_keys=...)` 并 `return usage_data, salvaged`（当作成功返回，让回合继续）。仅当抢救也失败才 raise。

> 边界：抢救出的 dict 缺 required 字段（如 player_action）。`_build_result_v2` 已对缺字段做防御（active_npcs 默认空、player_action 可 None）。确认 `_build_result_v2` 对 None/缺字段不抛异常——若抛，加默认值。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_director_json_robustness.py tests/test_director_agent.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/engine/director_agent.py backend/tests/test_director_json_robustness.py
git commit -m "feat(director): salvage partial JSON on terminal parse failure"
```

---

## Task 5:（条件触发）case_board_ops 移出主调用走 tail 生成（§1 削 payload）

**触发条件：** 仅当 Task 1 上线后评测/日志显示 director 截断主要是 `finish_reason=length`（即输出确实过大），才做此 task。若根因是网关 silent drop（无 finish_reason），削 payload 收益有限，**跳过本 task**，标记为已评估不做。

**为什么：** `case_board_ops` 是 director JSON 最大的动态字段，且已在 `orchestrator.py:1798` 被 defer 到 `director_v2_tail` 应用。但它仍在主调用里被**生成**，继续撑大主 JSON。把它彻底移出主 schema、改由 tail 阶段一次轻量调用生成，能对所有回合缩小主 JSON。

**Files:**
- Modify: `backend/engine/prompts.py:548-600`（`build_director_tool_v2` 不再注入 case_board_ops）
- Modify: `backend/engine/orchestrator.py:2240-2280`（tail 阶段调一次轻量 director 生成 case_board）
- Modify: `backend/engine/director_agent.py`（新增轻量 `generate_case_board_ops` 方法）
- Test: `backend/tests/test_director_tool_clue_constraint.py`、`backend/tests/test_orchestrator_early_stream.py`

- [ ] **Step 1: 写失败测试（主 schema 不含 case_board_ops）**

```python
def test_v2_schema_excludes_case_board_ops():
    from engine.prompts import build_director_tool_v2
    tool = build_director_tool_v2(script_type="detective", game_mode="script",
                                  discovered_clue_ids=["clue_001"])
    assert "case_board_ops" not in tool["input_schema"]["properties"]
```

- [ ] **Step 2: 运行确认失败 → 改 `build_director_tool_v2`**

去掉 `build_director_tool_v2` 里注入 case_board_ops 的整段（559-600+）。`build_director_tool`（v1）保持不变（v1 仍单调用）。

- [ ] **Step 3: tail 阶段新增轻量 case_board 生成**

`director_agent.py` 加 `generate_case_board_ops(self, *, scene_brief, discovered_clue_ids, current_case_board) -> list[dict]`：用一个精简 prompt（只含本回合 scene_brief + 现有案件板快照 + clue 约束）走 `stream_json`，schema 只有 `case_board_ops` 一个字段。失败返回 `[]`（案件板本就是增量，丢一回合可容忍）。

`orchestrator.py` 的 `if case_board_deferred:` 分支（2262）改为：调用 `generate_case_board_ops(...)` 拿 ops，再 `apply_case_board_ops`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_director_tool_clue_constraint.py tests/test_orchestrator_early_stream.py tests/test_orchestrator_v2_loading.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/engine/prompts.py backend/engine/orchestrator.py backend/engine/director_agent.py backend/tests/
git commit -m "perf(director): generate case_board_ops in tail call, shrink main JSON"
```

---

## Task 6: 结局 AI 层复活的端到端验证（§3）

**为什么：** §3 不需要补 hard_conditions——`merge_ai_ending_judgment`（ending_system.py:184-193）匹配的是 `ending_type + soft_conditions`，工坊产的 soft 结局本就能被 AI 层匹配。Task 1+3+4 让 `ending_triggered` 活过来后，AI 层自动复活。这个 task 用一个 in-process 端到端测试**锁定**「director 给出 ending_triggered → `_resolve_ending` 走 path=ai 而非 forced」。

**Files:**
- Test: `backend/tests/test_ending_system.py`（或新 `test_resolve_ending_path.py`）

- [ ] **Step 1: 写测试——AI 层优先于 forced 地板**

```python
def test_resolve_ending_prefers_ai_over_forced(monkeypatch):
    from engine.ending_system import merge_ai_ending_judgment
    endings = [
        {"ending_type": "good", "soft_conditions": {"x": 1}, "priority": 10},
        {"ending_type": "timeout", "soft_conditions": {"y": 1}, "priority": 1},
    ]
    ai = {"should_end": True, "ending_type": "good", "reason": "真相揭露"}
    matched = merge_ai_ending_judgment(endings, ai)
    assert matched is not None
    assert matched["ending_type"] == "good"  # 拿到挣来的好结局，不是安慰奖


def test_resolve_ending_ai_judgment_ignored_when_should_end_false():
    from engine.ending_system import merge_ai_ending_judgment
    endings = [{"ending_type": "good", "soft_conditions": {"x": 1}}]
    assert merge_ai_ending_judgment(endings, {"should_end": False}) is None
```

- [ ] **Step 2: 运行确认通过（行为已被 Task1-4 解锁，这里是回归锁定）**

Run: `cd backend && python -m pytest tests/test_ending_system.py -v`
Expected: PASS。

- [ ] **Step 3: 加 `_resolve_ending` 集成测试（path=ai）**

构造 fake `director_result.ending_triggered={"should_end":True,"ending_type":"good"}` + world_data.endings 含 good(soft)，断言 `_resolve_ending` 返回 good 结局、日志 path=ai。用现有 orchestrator 测试夹具（看 `test_orchestrator.py` 的 GameState/world_data 构造）。

- [ ] **Step 4: 提交**

```bash
git add backend/tests/test_ending_system.py
git commit -m "test(ending): lock AI ending layer revival (path=ai over forced floor)"
```

---

## Task 7: 导演弱输入「推进地板」（§4）

**为什么：** 弱输入 clamp（prompts.py:843-852）只会「做更少」，没有「推世界但不替玩家完成声明动作」的中间档；节奏只有「3 轮无发现才 advance」（:789），没有「每回合至少留一点新东西」的地板。纯观察输入也 0 线索回报。

**测试性质说明：** 这是 prompt 软约束，LLM 输出非确定。本 task 的「测试」= prompt 内容存在性断言（确定性）+ 人工评测验收（非确定，标注）。

**Files:**
- Modify: `backend/engine/prompts.py:786-792`（节奏段加推进地板）、`843-852`（弱输入 clamp 加中间档）
- Test: `backend/tests/test_prompts.py`

- [ ] **Step 1: 写存在性测试**

```python
def test_weak_input_clamp_allows_world_progress():
    from engine.prompts import build_director_system_v2  # 或弱输入段构造函数
    sys = build_director_system_v2(..., player_input_weak=True)  # 按实际签名
    # 弱输入下仍允许推进世界（环境线索/后台事件），只是不替玩家完成声明动作
    assert "环境线索" in sys or "后台" in sys
    assert "纯观察" in sys  # 纯观察至少回一条感官线索
```

> 执行者按 `build_director_system_v2` 实际签名对齐（grep 确认函数名/参数）。

- [ ] **Step 2: 运行确认失败 → 改弱输入段文案**

把弱输入段（843-852）改为：

```python
"## ⚠️ 本回合玩家输入很弱（player_input_weak）",
"玩家本轮只输入了简短/纯观察的内容。",
"**严禁**让 NPC 替玩家完成动作、替玩家做决定。",
"- dramatic_intensity 必须 ≤ medium",
"- active_npcs 最多 1 人，且不暗示 NPC 主动进逼玩家",
"**但世界不能停**——以下仍要做（这是推进地板）：",
"- 至少在 scene_brief 或 state_updates.new_clues 里给出 1 条**新的环境/感官信息**",
"  （玩家纯观察 → 回报他观察到的一条具体细节，看了就该有所得）",
"- 可推进 1 条后台/环境线索（NPC 远处的动静、时间流逝带来的变化），",
"  但不替玩家执行其声明的动作。",
```

- [ ] **Step 3: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_prompts.py -v`
Expected: PASS。

- [ ] **Step 4: （非确定性，人工）评测验收**

独立实例跑 1-2 局弱输入/纯观察场景，确认「仔细观察」能回报感官线索、漫游局不再 7 回合 0 推进。**此步不进 CI，标注为人工验收。**

- [ ] **Step 5: 提交**

```bash
git add backend/engine/prompts.py backend/tests/test_prompts.py
git commit -m "feat(director): add progress-floor to weak-input clamp"
```

---

## Task 8: free 模式 POV 边界 + 线索语义门槛（§5.1 + §5.2）

**为什么：**
- §5.1：free 模式玩家是皇后却命令了华妃的宫女颂芝——缺「玩家只能驱动自己 POV 角色」约束。
- §5.2：把玩家自己下的命令记成 discovered_clue → 进展度量灌水。

**测试性质：** §5.1 是 prompt 软约束（存在性断言 + 人工）；§5.2 可加确定性的写入门槛单测。

**Files:**
- Modify: `backend/engine/prompts.py`（free 模式段加 POV 边界）
- Modify: `backend/engine/orchestrator.py` 或 `state_manager.py`（new_clues 写入门槛：过滤「玩家意图日志」）
- Test: `backend/tests/test_prompts.py`、`backend/tests/test_orchestrator.py`

- [ ] **Step 1: §5.1 写存在性测试 + 改 free 模式 prompt**

测试断言 free 模式 system 含 POV 边界文案；prompt 加：「玩家只能驱动自己扮演的角色（{player_persona}）。玩家不能直接命令其他阵营的 NPC 做事——其他 NPC 是否服从由其自身 persona / 关系决定，不照单全收跨角色指令。」

- [ ] **Step 2: §5.2 写线索门槛失败测试**

```python
def test_new_clue_rejects_player_intent_log():
    from engine.state_manager import filter_new_clues  # 见 Step 3
    raw = ["管事桌上的登记簿撕掉了腊月十八那页",  # 世界新事实 ✅
           "我命令颂芝去查华妃"]                      # 玩家意图日志 ❌
    kept = filter_new_clues(raw, player_action_summary="命令颂芝去查华妃")
    assert "管事桌上的登记簿撕掉了腊月十八那页" in kept
    assert "我命令颂芝去查华妃" not in kept
```

- [ ] **Step 3: 实现 `filter_new_clues` 写入门槛**

加一个轻量过滤：剔除以「我/玩家」第一人称指令开头、或与本回合 player_action.summary 高度重合的条目。保守策略（只挡明显的玩家意图日志，不误杀世界事实）。在 orchestrator 应用 new_clues 处接入。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_prompts.py tests/test_orchestrator.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/engine/prompts.py backend/engine/state_manager.py backend/engine/orchestrator.py backend/tests/
git commit -m "fix(engine): free-mode POV boundary + clue write-gate against intent logs"
```

---

## Task 9: 结构化输出解析脆弱治理（§5.4）

**为什么：** 评测期 warning 频发：`npc_reflection.empty_output`（NPC 反思常空转）、`case_board_invalid_ops`（案件板 op schema 校验失败被丢）、`ending_summary_json_parse_failed`。多为后台非致命，但说明结构化解析普遍脆弱。

**Files:**
- Modify: `backend/engine/case_board.py`（invalid_ops 记录被丢的具体原因 + 救可解析的 op）
- Modify: `backend/engine/npc_agent.py`（reflection empty 时降级而非空转）
- Modify: `backend/engine/ending_system.py:77` 附近（ending_summary parse 失败兜底）
- Test: `backend/tests/test_case_board.py`（若无则建）、`backend/tests/test_ending_system.py`

- [ ] **Step 1: case_board invalid_ops——逐 op 校验，救合法的**

现状整批 ops 校验失败就全丢。改为逐 op 校验，合法的照常 apply，非法的记 `logger.warning("case_board_invalid_op", op=..., reason=...)` 跳过。写测试：混合合法/非法 ops，断言合法的被 apply。

- [ ] **Step 2: npc_reflection 空输出降级**

reflection 空时，不写空 memory、记 `logger.info`（降噪到 info），用上一轮 stance 兜底，不影响 act 步。写测试断言空 reflection 不抛、不污染 memory。

- [ ] **Step 3: ending_summary parse 失败兜底**

parse 失败时用模板化 fallback summary（结局类型 + 既有 reason），不让结局展示空白。写测试。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_case_board.py tests/test_ending_system.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/engine/case_board.py backend/engine/npc_agent.py backend/engine/ending_system.py backend/tests/
git commit -m "fix(engine): harden case_board/reflection/ending-summary parse failures"
```

---

## Task 10: narrator boundary 风格约束（§5.5）

**为什么：** boundary 局旁白被挑衅输入带偏到近恐怖氛围，对宫斗题材略 OOC。narrator 对敌意输入过度渲染阴森。

**测试性质：** prompt 软约束，存在性断言 + 人工验收。

**Files:**
- Modify: `backend/engine/prompts.py`（narrator 风格段）
- Test: `backend/tests/test_prompts.py`

- [ ] **Step 1: 写存在性测试 + 改 narrator 风格段**

加约束：「面对玩家的挑衅/敌意输入，保持题材基调（如宫斗的端庄机锋），不要滑向恐怖/惊悚渲染；张力来自人物关系与权谋，不是环境惊吓。」

- [ ] **Step 2: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_prompts.py -v`
Expected: PASS。

- [ ] **Step 3: 提交**

```bash
git add backend/engine/prompts.py backend/tests/test_prompts.py
git commit -m "fix(narrator): keep genre tone under hostile input, avoid horror drift"
```

---

## 最终验证（全部 task 完成后）

- [ ] **跑改动涉及的测试文件全集**

Run:
```bash
cd backend && python -m pytest \
  tests/test_director_json_mode.py tests/test_director_json_robustness.py \
  tests/test_director_agent.py tests/test_prompts.py tests/test_ending_system.py \
  tests/test_openai_compatible_finish_reason.py tests/test_grok_provider.py \
  tests/test_orchestrator.py tests/test_orchestrator_early_stream.py \
  tests/test_case_board.py tests/test_playability_judge_progression.py -v
```
Expected: 全 PASS。（不跑全量 pytest——有 ~56 个 pre-existing 失败与本改动无关。）

- [ ] **独立实例全量可玩性评测（关 reload）**

用 Task 0 修好的 harness，**起独立后端实例 / 关闭 `--reload`**，重跑甄嬛传 6 局评测。验收指标：
- `ending.resolved path=ai` 出现率 > 0（修复前为 0）。
- 导演软失败率（无旁白回合）显著下降（修复前 S3/S4 仅成功 13/30）。
- 弱输入/纯观察回合有线索回报。
- 硬检仍全 0（不引入越狱回退）。

- [ ] **更新记忆**

把本轮结果回写记忆 `playability-eval-findings-2026-06-02`（或新建优化结论记忆），记录 path=ai 复活、软失败率变化、§1 真实根因（length vs silent drop，由 Task 1 的 finish_reason 揭晓）。

---

## Self-Review（写计划时已执行）

**Spec 覆盖：** §1（Task 1-5）、§2（Task 1）、§3（Task 6）、§4（Task 7）、§5.1/5.2（Task 8）、§5.3 延迟（随 Task 5 削 payload 顺带，未单列）、§5.4（Task 9）、§5.5（Task 10）、§6 harness（Task 0）。全覆盖。

**已知取舍：**
- Task 5（削 payload）设为条件触发——一步到位 ≠ 盲目做高风险改动；若 §1 根因是 silent drop，削 payload 收益有限，由 Task 1 观测定夺。
- §5.3 延迟未单列 task：climax 延迟主因是 payload 重，Task 5 已覆盖；其余延迟优化属另一条线（见记忆 `play-perf-optimization-2026-05`），不在本可玩性修复范围。
- Prompt 软约束类（Task 7/8.1/10）诚实标注「无确定性单测，存在性断言 + 人工验收」，不假装 TDD。

**类型一致性：** `_DirectorJsonFailure`(Task 2) / `_salvage_partial`(Task 4) / `build_usage_event`(Task 1) / `generate_case_board_ops`(Task 5) / `filter_new_clues`(Task 8) 命名跨 task 一致。
