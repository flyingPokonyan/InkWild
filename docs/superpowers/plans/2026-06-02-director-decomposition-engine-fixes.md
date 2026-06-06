# 导演单体生成解耦 / 可玩性引擎修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让导演被网关截断时"截断可见、可抢救、结局照常挣得到"，并修掉弱输入下导演只会抑制不会推进的惰性——把可玩性评测里的两个 P0 + 两个 P1 压下去。

**Architecture:** 评测根因是导演把「叙事 + 案件板 + 结局裁决」捆进一次 all-or-nothing 的结构化生成，任一处截断整份报废，且因 provider 的 usage 事件 schema 不统一（仅 deepseek 带 `finish_reason`）导致引擎对截断全瞎。本 plan 阶段一不改生成体积，而是先让系统「截断了也不致命」：①统一 provider usage 契约让截断可见 → ②导演终态复用 `try_partial_parse` 抢救前缀（救回 `scene_brief`/`ending_triggered`）→ ③结局 AI 层随之复活 → ④拆开弱输入护栏的「别抢玩家」与「别推世界」。阶段二（case_board two-pass 减体积、降低截断频率）单列文末，待阶段一落地验证后细化。

**Tech Stack:** Python 3.12 / FastAPI / pytest(+asyncio) / structlog；LLM provider 抽象层（`llm/base.py` + deepseek/claude/grok/openai_compatible）；导演 agent（`engine/director_agent.py`）。

**实施前提醒：** 记忆 `concurrency-bottleneck-2026-06-02` 记载——评测期跑在 `uvicorn --reload`，改 `backend/*.py` 会热重启掐断在飞 SSE。**执行本 plan 时确保不在评测窗口，或关掉 reload**，否则会重蹈「并发死 3/4」的伪结论。

---

## 文件结构（决策锁定）

| 文件 | 职责 | 本 plan 改动 |
|---|---|---|
| `llm/base.py` | LLMProvider 抽象契约 | 文档化 usage 事件必出字段（含 `finish_reason`）|
| `llm/openai_compatible.py` | OpenAI 兼容 provider（评测走它）| 流末捕获 `choice.finish_reason` → usage 事件 |
| `llm/grok.py` | Grok provider | 同上 |
| `llm/claude.py` | Anthropic provider | `final.stop_reason` 映射成 `finish_reason` |
| `llm/deepseek.py` | DeepSeek provider | **不动**（已正确实现）|
| `engine/director_agent.py` | 导演 agent + 两条 JSON 路径 | 终态 `try_partial_parse` 抢救（`_run_json_mode_raw` + `_run_json_mode`）|
| `engine/player_input_guard.py` | 弱输入评估 + clamp 提示 | 增「推进世界但不抢玩家」中间档 + 纯观察感官回报 |
| `engine/prompts.py` | 导演 prompt | 弱输入块同步增中间档 |
| `tests/test_*.py` | 回归测试 | 新增 provider finish_reason / 导演抢救 / 弱输入 / 结局复活 |

---

## Task 1: 统一 provider usage 事件契约，补 `finish_reason`（P0-a）

**Files:**
- Modify: `llm/base.py`（LLMProvider 抽象方法 docstring）
- Modify: `llm/openai_compatible.py:106-159`
- Modify: `llm/grok.py:83-138`
- Modify: `llm/claude.py:44-68`
- Test: `tests/test_openai_compatible_finish_reason.py`（新建）、`tests/test_grok_provider.py`（追加）、`tests/test_claude_finish_reason.py`（新建）

### Task 1a — openai_compatible

- [ ] **Step 1: 写失败测试** —— `tests/test_openai_compatible_finish_reason.py`

```python
from types import SimpleNamespace

import pytest

from llm.openai_compatible import OpenAICompatibleProvider


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCompletions:
    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **kwargs):
        return _FakeStream(self._chunks)


def _make_provider(monkeypatch, chunks):
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.model = "test-model"
    provider._reasoning_off_extra_body = None
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(chunks))
    )
    return provider


@pytest.mark.asyncio
async def test_usage_event_carries_finish_reason_length(monkeypatch):
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="部分文本", tool_calls=None),
                finish_reason=None,
            )],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=None),
                                     finish_reason="length")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        ),
    ]
    provider = _make_provider(monkeypatch, chunks)
    events = [e async for e in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=None, system="s")]
    usage = [e for e in events if e["type"] == "usage"][0]
    assert usage["finish_reason"] == "length"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_openai_compatible_finish_reason.py -v`
Expected: FAIL —— `KeyError: 'finish_reason'`（usage 事件当前无此字段）

- [ ] **Step 3: 实现** —— `llm/openai_compatible.py`

在 `:106` `usage = None` 后新增 finish_reason 累积变量：

```python
        tool_buffers: dict[int, dict] = {}
        usage = None
        finish_reason: str | None = None
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage

            for choice in getattr(chunk, "choices", []) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
```

把 usage 事件（`:155-159`）改为带上 finish_reason：

```python
        event = {
            "type": "usage",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "finish_reason": finish_reason,
        }
```

（下方 cache_hit/miss 注入逻辑保持不变。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_openai_compatible_finish_reason.py -v`
Expected: PASS

### Task 1b — grok

- [ ] **Step 5: 写失败测试** —— `tests/test_grok_provider.py` 末尾追加

```python
@pytest.mark.asyncio
async def test_stream_with_tools_usage_carries_finish_reason():
    provider = GrokProvider(api_key="test-key", model="grok-test")

    class _Stream:
        def __aiter__(self):
            self._it = iter([
                SimpleNamespace(
                    choices=[SimpleNamespace(
                        delta=SimpleNamespace(content="片段", tool_calls=None),
                        finish_reason=None)],
                    usage=None),
                SimpleNamespace(
                    choices=[SimpleNamespace(
                        delta=SimpleNamespace(content=None, tool_calls=None),
                        finish_reason="length")],
                    usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3)),
            ])
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class _Completions:
        async def create(self, **kwargs):
            return _Stream()

    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    events = [e async for e in provider.stream_with_tools(
        messages=[{"role": "user", "content": "x"}], tools=None, system="s")]
    usage = [e for e in events if e["type"] == "usage"][0]
    assert usage["finish_reason"] == "length"
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_grok_provider.py::test_stream_with_tools_usage_carries_finish_reason -v`
Expected: FAIL —— `KeyError: 'finish_reason'`

- [ ] **Step 7: 实现** —— `llm/grok.py`

在 `:83` `usage = None` 后加 `finish_reason: str | None = None`，并在 `:85` `async for chunk in stream:` 内的 `for choice in ...` 循环开头（`:89`）捕获：

```python
        tool_buffers: dict[int, dict] = {}
        usage = None
        finish_reason: str | None = None

        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage

            for choice in getattr(chunk, "choices", []) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
```

把 usage 事件（`:134-138`）改为：

```python
        yield {
            "type": "usage",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "finish_reason": finish_reason,
        }
```

- [ ] **Step 8: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_grok_provider.py -v`
Expected: PASS（含原有 2 个 web_search 测试）

### Task 1c — claude（stop_reason 映射，抽纯函数便于测试）

- [ ] **Step 9: 写失败测试** —— `tests/test_claude_finish_reason.py`（新建）

```python
from llm.claude import _finish_reason_from_stop


def test_max_tokens_maps_to_length():
    assert _finish_reason_from_stop("max_tokens") == "length"


def test_end_turn_maps_to_stop():
    assert _finish_reason_from_stop("end_turn") == "stop"


def test_tool_use_passthrough():
    assert _finish_reason_from_stop("tool_use") == "tool_use"


def test_none_stays_none():
    assert _finish_reason_from_stop(None) is None
```

- [ ] **Step 10: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_claude_finish_reason.py -v`
Expected: FAIL —— `ImportError: cannot import name '_finish_reason_from_stop'`

- [ ] **Step 11: 实现** —— `llm/claude.py`

模块级新增映射函数（放在文件 import 之后、类定义之前）：

```python
def _finish_reason_from_stop(stop_reason: str | None) -> str | None:
    """Normalize Anthropic ``stop_reason`` to the OpenAI-style ``finish_reason``
    the director's truncation detector consumes. ``max_tokens`` is the only one
    that must become ``length``; ``end_turn``/``stop_sequence`` collapse to
    ``stop``; ``tool_use`` passes through; ``None`` stays ``None``."""
    if stop_reason is None:
        return None
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason in {"end_turn", "stop_sequence"}:
        return "stop"
    return stop_reason
```

把 usage 事件（`:64-68`）改为：

```python
            yield {
                "type": "usage",
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
                "finish_reason": _finish_reason_from_stop(
                    getattr(final, "stop_reason", None)
                ),
            }
```

- [ ] **Step 12: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_claude_finish_reason.py -v`
Expected: PASS

### Task 1d — base.py 契约文档化

- [ ] **Step 13: 在 `llm/base.py` 的 `stream_with_tools` 与 `stream_json` 抽象方法 docstring 末尾，各追加 usage 事件契约说明**

追加文本（两个方法都加同样一段）：

```
        Usage-event contract: the final event yielded MUST be
        ``{"type": "usage", "input_tokens": int, "output_tokens": int,
        "finish_reason": str | None}``. ``finish_reason`` follows OpenAI
        semantics ("stop" | "length" | "tool_calls" | provider-native | None);
        downstream truncation detection (director_agent) depends on "length"
        being surfaced here. ``cache_hit_tokens``/``cache_miss_tokens`` are
        optional.
```

- [ ] **Step 14: 跑全 provider 相关测试，确认无回归**

Run: `cd backend && python -m pytest tests/test_deepseek_provider.py tests/test_grok_provider.py tests/test_openai_compatible_finish_reason.py tests/test_claude_finish_reason.py tests/test_llm_router.py -v`
Expected: 全部 PASS（deepseek 原测试不受影响——它的 usage 事件本就带 finish_reason，且未断言"无额外字段"）

- [ ] **Step 15: Commit**（若仓库已 init）

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/llm/base.py backend/llm/openai_compatible.py backend/llm/grok.py backend/llm/claude.py backend/tests/test_openai_compatible_finish_reason.py backend/tests/test_grok_provider.py backend/tests/test_claude_finish_reason.py
git commit -m "fix(llm): 统一 provider usage 事件补 finish_reason，让导演截断可见"
```

---

## Task 2: 导演终态复用 `try_partial_parse` 抢救被截断的 JSON（P0-b.1/.2）

**根因**：`_run_json_mode_raw`（`director_agent.py:1024-1044`）终态用 `_extract_json_from_text(raw)`（要求**完整** JSON），截断即 `return None` → 3 次重试耗尽 → 整回合 abort。但 `:1006` 的流式增量早就有 `try_partial_parse`，终态没复用。抢救前缀即可救回 `scene_brief`/`ending_triggered`，把「整回合软失败」降级为「记账丢失」，并让结局 AI 层复活。

**质量门槛**：只在抢救出的 dict 含 `scene_brief` 或 `ending_triggered` 时才采用（避免拿半个空壳冒充成功）；否则维持 `return None` 走重试。

**Files:**
- Modify: `engine/director_agent.py:1024-1045`（`_run_json_mode_raw` 终态）、`:1148-1157`（`_run_json_mode` 终态，防御一致性）
- Test: `tests/test_director_json_robustness.py`（追加）

- [ ] **Step 1: 写失败测试** —— `tests/test_director_json_robustness.py` 末尾追加

```python
@pytest.mark.asyncio
async def test_truncated_json_salvages_ending_triggered():
    """climax 时导演 JSON 在尾部被网关截断 → 终态抢救出已生成的
    scene_brief + ending_triggered，而不是整回合 abort。"""
    truncated = (
        '{"scene_brief": "皇后摊牌，甄嬛递上滴血的证物。",'
        ' "active_npcs": ["皇后"], "ending_triggered": {"should_end": true,'
        ' "ending_type": "good", "reason": "真相大白"}, "case_board_ops": ['
    )  # 在 case_board_ops 处被切断，整体不可 json.loads

    class _OneShotRouter:
        def __init__(self):
            self.calls = 0

        def current_model_id(self):
            return "deepseek-v4-pro"

        async def stream_json(self, messages, system=None, max_tokens=2048,
                              provider_offset=0):
            self.calls += 1
            yield {"type": "text_delta", "text": truncated}
            yield {"type": "usage", "input_tokens": 0, "output_tokens": 0,
                   "finish_reason": "length"}

        async def stream_with_tools(self, **kwargs):  # pragma: no cover
            if False:
                yield {}

    router = _OneShotRouter()
    agent = DirectorAgent(router)
    result = await agent._run_json_mode_raw(
        system="s", messages=[{"role": "user", "content": "摊牌"}],
        schema={"type": "object", "properties": {}},
    )
    assert result is not None
    usage_data, tool_input = result
    assert tool_input["scene_brief"].startswith("皇后摊牌")
    assert tool_input["ending_triggered"]["should_end"] is True
    assert router.calls == 1  # 抢救成功，未触发重试
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_director_json_robustness.py::test_truncated_json_salvages_ending_triggered -v`
Expected: FAIL —— `result is None`（终态当前不抢救，截断即返回 None）

- [ ] **Step 3: 实现** —— `engine/director_agent.py` `_run_json_mode_raw` 终态（`:1024-1044`）

把：

```python
        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
```

改为先抢救：

```python
        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
            # Truncation salvage: the streaming path already partial-parses the
            # buffer (see on_partial above); reuse it at the terminal state so a
            # mid-stream cut (network gateway clipping the climax payload) still
            # yields the front of the JSON. Only accept the salvage if it carries
            # a load-bearing field — otherwise fall through to the retry below so
            # we don't pass an empty shell off as success.
            salvaged = try_partial_parse(raw)
            if salvaged and (salvaged.get("scene_brief") or salvaged.get("ending_triggered")):
                logger.warning(
                    "director_v2.json_mode_salvaged",
                    finish_reason=finish_reason,
                    output_chars=len(raw),
                    salvaged_keys=sorted(salvaged.keys()),
                )
                return usage_data, salvaged
```

注意：`raw` 可能带 ```` ```json ```` fence —— `try_partial_parse` 接受裸 JSON 起始，若 raw 以 fence 开头，复用上面 `:1002-1005` 的剥离逻辑。在抢救前加：

```python
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            salvaged = try_partial_parse(salvage_src)
```

（即把上面 `try_partial_parse(raw)` 替换为对 `salvage_src` 调用。）原有的 `finish_reason == "length"` 分类 + `return None` 逻辑保留在抢救失败之后，作为兜底。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_director_json_robustness.py -v`
Expected: 全部 PASS（含原有 5 个测试 + 新增 1 个）

- [ ] **Step 5: 对 `_run_json_mode`（v1，`:1148-1155`）做同样的抢救**（防御一致性，避免 v1 路径残留旧行为）

把：

```python
        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
            logger.warning(
                "director.json_mode_parse_failed",
                preview=raw[:200] if raw else "<empty>",
            )
            return None
```

改为：

```python
        raw = "".join(text_parts)
        tool_input = _extract_json_from_text(raw)
        if tool_input is None:
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            salvaged = try_partial_parse(salvage_src)
            if salvaged and (salvaged.get("scene_brief") or salvaged.get("ending_triggered")):
                logger.warning("director.json_mode_salvaged",
                               salvaged_keys=sorted(salvaged.keys()))
                return self._build_result(salvaged, usage_data)
            logger.warning(
                "director.json_mode_parse_failed",
                preview=raw[:200] if raw else "<empty>",
            )
            return None
```

- [ ] **Step 6: 跑导演相关测试套，确认无回归**

Run: `cd backend && python -m pytest tests/test_director_agent.py tests/test_director_json_mode.py tests/test_director_json_robustness.py -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/engine/director_agent.py backend/tests/test_director_json_robustness.py
git commit -m "fix(director): 截断 JSON 终态复用 try_partial_parse 抢救前缀，救回 scene_brief/ending_triggered"
```

---

## Task 3: 结局 AI 层复活回归测试（P1 §3）

**说明**：结局 AI 层退化的根因是 `ending_triggered` 被截断切没（Task 1+2 已修），不是 `merge_ai_ending_judgment` 本身坏。本 task 加一条回归测试钉住「只要 director 给出匹配的 `ending_triggered`，结局解析就走 AI 层而非 forced 地板」，防止未来再退化。

**Files:**
- Test: `tests/test_ending_system.py`（追加）

- [ ] **Step 1: 写测试** —— `tests/test_ending_system.py` 末尾追加

```python
from engine.ending_system import merge_ai_ending_judgment, check_forced_ending


def _endings():
    return [
        {"ending_type": "good", "priority": 10, "soft_conditions": {"any": []},
         "title": "真相大白"},
        {"ending_type": "timeout", "priority": 1, "soft_conditions": {"any": []},
         "title": "不了了之"},
    ]


def test_ai_judgment_selects_earned_ending_over_floor():
    """director 给出有效 ending_triggered 时，AI 层应选中对应的 good 结局
    （而不是退化到 stall floor 偏好的 timeout）。"""
    ai = {"should_end": True, "ending_type": "good", "reason": "玩家揭穿真凶"}
    picked = merge_ai_ending_judgment(_endings(), ai)
    assert picked is not None
    assert picked["ending_type"] == "good"


def test_ai_judgment_should_not_end_returns_none():
    ai = {"should_end": False}
    assert merge_ai_ending_judgment(_endings(), ai) is None
```

- [ ] **Step 2: 跑测试确认通过**（这是回归保护，逻辑已存在，应直接 PASS）

Run: `cd backend && python -m pytest tests/test_ending_system.py -v`
Expected: 全部 PASS。若新测试意外 FAIL，说明 `soft_conditions` 匹配逻辑有额外约束——回到 `engine/ending_system.py:184-193` 核对 `merge_ai_ending_judgment` 的匹配条件再调整测试夹具。

- [ ] **Step 3: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/tests/test_ending_system.py
git commit -m "test(ending): 钉住 AI 结局层优先于 stall floor 的回归"
```

---

## Task 4: 弱输入推进地板——拆开「别抢玩家」与「别推世界」（P1 §4）

**根因**：弱/纯观察输入时三层全是抑制（`player_input_guard.to_hint` + `prompts.py` 弱输入块 + orchestrator safety net），没有「推进世界但不替玩家行动」的中间档；纯观察输入连一条感官线索都不回报。改法是**内容层**：给 clamp 增中间档 + 纯观察感官回报要求。不新增逻辑地板（YAGNI，先靠 prompt）。

**Files:**
- Modify: `engine/player_input_guard.py:89-98`（`to_hint`）
- Modify: `engine/prompts.py:842-853`（弱输入块）
- Test: `tests/test_player_input_guard.py`（追加）

- [ ] **Step 1: 写失败测试** —— `tests/test_player_input_guard.py` 末尾追加

```python
from engine.player_input_guard import assess_input_strength


def test_weak_hint_keeps_world_progression_clause():
    """弱输入 clamp 不能只会抑制——必须保留「推进世界但不替玩家行动」中间档。"""
    hint = assess_input_strength("环顾").to_hint()
    assert "推进世界" in hint or "环境线索" in hint
    # 抑制条款仍在
    assert "替玩家" in hint


def test_pure_observation_demands_sensory_payoff():
    """纯观察输入必须回报至少一条感官层面的新观察。"""
    assessment = assess_input_strength("仔细观察四周")
    assert assessment.is_pure_observation is True
    hint = assessment.to_hint()
    assert "感官" in hint or "看到" in hint
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_player_input_guard.py::test_weak_hint_keeps_world_progression_clause tests/test_player_input_guard.py::test_pure_observation_demands_sensory_payoff -v`
Expected: FAIL —— 当前 `to_hint` 只有抑制条款，无「推进世界」/「感官回报」措辞

- [ ] **Step 3: 实现** —— `engine/player_input_guard.py` `to_hint`（`:89-98`）

把 `lines` 列表改为（保留原抑制条款 + 新增中间档 + 纯观察感官回报）：

```python
        lines = [
            "## 玩家本轮输入信号弱（player_input_weak=true）",
            f"- 字数 {self.char_count}，"
            f"{'仅含观察类动词' if self.is_pure_observation else '无明确目标'}",
            "- dramatic_intensity 不要给 high/climax；active_npcs 不要超过 1 人",
            "- per_npc_focus 禁止暗示「NPC 主动行动」；让叙事以环境/玩家 POV 感官为主",
            "- narrator 段落应短（≤250 字），可以反问玩家「想看什么 / 想问谁」",
            "- 严禁让 NPC 替玩家完成未声明的动作（移动、取物、揭露线索等）",
            # 中间档：抑制「替玩家行动」≠ 冻结世界。世界仍要往前走一点。
            "- **但世界不能停摆**：可以推进一条环境线索 / 后台正在发生的事 / 时间流逝的细节，"
            "只要不替玩家完成他没声明的动作即可。",
        ]
        if self.is_pure_observation:
            lines.append(
                "- 玩家在观察 → **至少回报一条感官层面的新观察**（看到/听到/闻到的具体细节），"
                "看了就该有所得；可写进 state_updates.new_clues 或场景描述。"
            )
        return "\n".join(lines)
```

注意：原 `:98` 的 `return "\n".join(lines)` 被上面的 `if` 块替代，确保只保留一处 return。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_player_input_guard.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 同步 `engine/prompts.py` 弱输入块（`:842-853`）**

在 `player_input_weak` 块的列表里，于 `"- 让叙事以环境 + 玩家 POV 感官为主"` 之后追加两条，保持与 `to_hint` 一致：

```python
    if player_input_weak:
        parts.extend(
            [
                "",
                "## ⚠️ 本回合玩家输入很弱（player_input_weak）",
                "玩家本轮只输入了简短/纯观察的内容。**严禁**让 NPC 替玩家完成动作。",
                "- dramatic_intensity 必须 ≤ medium",
                "- active_npcs 最多 1 人",
                "- per_npc_focus 不要暗示 NPC 主动行动",
                "- 让叙事以环境 + 玩家 POV 感官为主",
                "- 但世界不能停摆：仍可推进一条环境线索 / 后台事件 / 时间流逝，"
                "只要不替玩家完成未声明的动作",
                "- 若玩家在观察，至少回报一条具体的感官新发现（看到/听到/闻到），"
                "可写进 state_updates.new_clues",
            ]
        )
```

- [ ] **Step 6: 跑 prompts 相关测试确认无回归**

Run: `cd backend && python -m pytest tests/test_prompts.py tests/test_prompts_stable_prefix.py tests/test_player_input_guard.py -v`
Expected: 全部 PASS（新增条款是 `player_input_weak` 条件段，不影响 stable-prefix 缓存测试——弱输入块本就是条件性动态段）

- [ ] **Step 7: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/engine/player_input_guard.py backend/engine/prompts.py backend/tests/test_player_input_guard.py
git commit -m "fix(director): 弱输入增「推进世界但不抢玩家」中间档 + 纯观察感官回报"
```

---

## 阶段一收尾验证

- [ ] **跑改动涉及的测试模块全集**

Run: `cd backend && python -m pytest tests/test_openai_compatible_finish_reason.py tests/test_grok_provider.py tests/test_claude_finish_reason.py tests/test_director_agent.py tests/test_director_json_mode.py tests/test_director_json_robustness.py tests/test_ending_system.py tests/test_player_input_guard.py tests/test_prompts.py -v`
Expected: 全 PASS。（记忆 `backend-test-suite-preexisting-failures`：全量 pytest 有 ~56 个 pre-existing 失败，验证只看上面这些被改模块。）

- [ ] **真跑一局甄嬛传 script 局**（非评测窗口 / 关 reload），结构化确认：
  - `director_v2.json_mode_salvaged` 在截断时出现（而非 `parse_failed` 后 abort）
  - 截断时 usage 日志的 `finish_reason` 不再恒为 `None`
  - 进 climax 且玩家挣到结局时 `ending.resolved path=ai`（而非全 `forced`）

---

# ========================= 阶段二：case_board two-pass 减体积 =========================

**目标**：阶段一让导演「截断了也不致命」，阶段二降低截断**频率**——把 JSON 里体积最大的 `case_board_ops` 从导演主生成里移出，走第二次独立轻量 LLM 调用（done 之后、玩家已解锁）。截断 case_board 只影响案件板（非致命），不连累叙事/结局。

**spike 结论（已核验，无悬空）**：
- 现有 `case_board_deferred`/`director_v2_tail`（`orchestrator.py:2262`）是**同一次 LLM 调用的延迟 apply**（`full_result = await director_task`），降感知延迟但**不降截断风险**——故必须独立第二次调用。
- `build_director_json_instruction`（`prompts.py:392`）序列化整个 schema + 一个**硬编码且不含 case_board_ops** 的 example → 去掉 schema 注入后 prompt 自洽，**无需改它**。
- `case_board_ops` items schema 在 `prompts.py:516-543`(v1) 和 `:580-605`(v2) 重复两份 → 抽共享常量。
- two-pass 用 **flag `director_case_board_two_pass`（默认 off）** 灰度：off 时行为与阶段一完全一致，可回滚；on 后用阶段一的 `finish_reason=length` 频率量化截断率降幅。
- 独立调用复用 `self.llm_router`（game_main slot）——case_board 的 clue 引用约束需要较强 instruction following；如后续成本敏感再切便宜 slot。

---

## Task 5: settings flag + 抽 case_board_ops items 共享常量

**Files:**
- Modify: `config.py:203`（settings）
- Modify: `engine/prompts.py:509-543, 573-605`
- Test: `tests/test_director_tool_clue_constraint.py`（追加）

- [ ] **Step 1: config.py 加 flag** —— 在 `:203` `case_board_research: bool = False` 旁追加：

```python
    case_board_research: bool = False
    case_board_research_dir: str = "research"
    # two-pass case board: 把 case_board_ops 从导演主 JSON 移出，done 后独立生成。
    # 默认 off → 行为与单 pass 一致；灰度开启后用 director_v2 finish_reason=length
    # 频率量化截断率降幅。见 docs/superpowers/plans/2026-06-02-director-decomposition.
    director_case_board_two_pass: bool = False
```

- [ ] **Step 2: prompts.py 抽共享常量** —— 在 `build_director_tool`（`:495`）之前新增模块级常量：

```python
_CASE_BOARD_OPS_ITEMS: dict = {
    "type": "object",
    "properties": {
        "op_type": {
            "type": "string",
            "enum": ["set_field", "upsert_list_item", "remove_list_item"],
        },
        "path": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "目标路径，如 ['current_objective']、['suspects']、['evidence_graph']、['npc_dynamic', '张三']、['scene_state']。",
        },
        "match": {
            "type": "object",
            "description": "列表项匹配条件，仅用于 upsert_list_item/remove_list_item。",
        },
        "value": {
            "type": ["object", "array", "string", "number", "boolean", "null"],
            "description": "set_field 的新值，或 upsert_list_item 的列表项内容。",
        },
        "reason": {
            "type": "string",
            "description": "简短说明为什么要更新案件面板。",
        },
    },
    "required": ["op_type", "path"],
}
```

把 `build_director_tool`（`:516-543`）和 `build_director_tool_v2`（`:580-605`）里的 `"items": { ... }` 两处都替换为：

```python
            "items": _CASE_BOARD_OPS_ITEMS,
```

- [ ] **Step 3: 写回归测试**（确保抽常量不改变 schema 形状）—— `tests/test_director_tool_clue_constraint.py` 末尾追加：

```python
from engine.prompts import build_director_tool_v2, _CASE_BOARD_OPS_ITEMS


def test_case_board_ops_items_shared_constant_intact():
    tool = build_director_tool_v2("mystery", "script", discovered_clue_ids=["c1"])
    items = tool["input_schema"]["properties"]["case_board_ops"]["items"]
    assert items == _CASE_BOARD_OPS_ITEMS
    assert items["required"] == ["op_type", "path"]
    assert set(items["properties"]) == {"op_type", "path", "match", "value", "reason"}
```

- [ ] **Step 4: 跑测试** —— `cd backend && python -m pytest tests/test_director_tool_clue_constraint.py -v`  → Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/config.py backend/engine/prompts.py backend/tests/test_director_tool_clue_constraint.py
git commit -m "refactor(director): 抽 case_board_ops items 共享常量 + 加 two-pass flag"
```

---

## Task 6: flag on 时导演主 schema 不再注入 case_board_ops

**Files:**
- Modify: `engine/prompts.py:559-606`（`build_director_tool_v2`）
- Test: `tests/test_director_tool_clue_constraint.py`（追加）

- [ ] **Step 1: 写失败测试** —— 追加：

```python
def test_two_pass_flag_strips_case_board_ops_from_v2_schema(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "director_case_board_two_pass", True)
    tool = build_director_tool_v2("mystery", "script", discovered_clue_ids=["c1"])
    assert "case_board_ops" not in tool["input_schema"]["properties"]


def test_single_pass_keeps_case_board_ops(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "director_case_board_two_pass", False)
    tool = build_director_tool_v2("mystery", "script", discovered_clue_ids=["c1"])
    assert "case_board_ops" in tool["input_schema"]["properties"]
```

- [ ] **Step 2: 跑测试确认失败** —— `cd backend && python -m pytest tests/test_director_tool_clue_constraint.py::test_two_pass_flag_strips_case_board_ops_from_v2_schema -v` → FAIL（当前无条件注入）

- [ ] **Step 3: 实现** —— `build_director_tool_v2`（`:559-562`）在 `if game_mode == "script" and script_type:` 之后、注入逻辑之前加 flag 短路：

```python
    tool = copy.deepcopy(DIRECTOR_TOOL_V2)
    _maybe_inject_research_note(tool)
    if game_mode == "script" and script_type:
        from config import settings
        if settings.director_case_board_two_pass:
            # two-pass: case_board_ops 由 DirectorAgent.generate_case_board_ops
            # 独立生成，不进导演主 schema（瘦身 → 降低截断概率）。
            return tool
        if discovered_clue_ids:
```

（其余原注入逻辑不变。）

- [ ] **Step 4: 跑测试确认通过** —— `cd backend && python -m pytest tests/test_director_tool_clue_constraint.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/engine/prompts.py backend/tests/test_director_tool_clue_constraint.py
git commit -m "feat(director): two-pass flag on 时主 schema 不注入 case_board_ops"
```

---

## Task 7: `DirectorAgent.generate_case_board_ops` 独立生成 + prompt builder

**Files:**
- Modify: `engine/prompts.py`（新增两个 builder）
- Modify: `engine/director_agent.py`（新增方法）
- Test: `tests/test_case_board_two_pass.py`（新建）

- [ ] **Step 1: prompts.py 新增 schema + prompt builder**（放在 `_CASE_BOARD_OPS_ITEMS` 常量之后）：

```python
def build_case_board_ops_schema() -> dict:
    """Standalone schema for the two-pass case board call."""
    return {
        "type": "object",
        "properties": {
            "case_board_ops": {"type": "array", "items": _CASE_BOARD_OPS_ITEMS},
        },
        "required": ["case_board_ops"],
    }


def build_case_board_generation_prompt(
    script_type: str, discovered_clue_ids: list[str]
) -> str:
    """System prompt for the standalone case-board pass. Carries the same
    field rules + clue constraint as the inline path, plus a DeepSeek-JSON-mode
    compliant sample (the word 'json' + a filled example)."""
    import json as _json

    from engine.case_board_prompts import build_case_board_prompt_rules

    rules = build_case_board_prompt_rules(script_type)
    if discovered_clue_ids:
        clue_constraint = (
            f"\n\n**value/match 里的 clue_id 只能取自这 {len(discovered_clue_ids)} 个："
            f"{discovered_clue_ids}**，不要发明新的 clue_id。"
        )
    else:
        clue_constraint = "\n\n当前 discovered_clues 为空，case_board_ops 不要引用任何 clue_id。"

    example = _json.dumps(
        {
            "case_board_ops": [
                {
                    "op_type": "upsert_list_item",
                    "path": ["suspects"],
                    "match": {"name": "华妃"},
                    "value": {"name": "华妃", "status": "嫌疑上升"},
                    "reason": "新证物指向华妃",
                }
            ]
        },
        ensure_ascii=False,
    )
    return (
        "你是案件面板维护器。读下面这一回合发生的事，输出案件面板的**增量更新操作**。\n"
        + rules
        + clue_constraint
        + "\n\n## 输出格式（严格遵守）\n"
        "只输出**一个** json 对象 `{\"case_board_ops\": [...]}`，没有要更新的就给空数组；"
        "不要输出任何其它文字、解释或代码块标记。\n"
        "示例（仅示意结构）：\n" + example
    )
```

- [ ] **Step 2: 写失败测试** —— `tests/test_case_board_two_pass.py`（新建）：

```python
import pytest

from engine.director_agent import DirectorAgent


class _CaseBoardRouter:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks
        self.calls = 0

    def current_model_id(self):
        return "deepseek-v4-pro"

    async def stream_json(self, messages, system=None, max_tokens=2048):
        self.calls += 1
        for c in self._chunks:
            yield {"type": "text_delta", "text": c}
        yield {"type": "usage", "input_tokens": 0, "output_tokens": 0,
               "finish_reason": "stop"}

    async def stream_with_tools(self, **kwargs):  # pragma: no cover
        if False:
            yield {}


@pytest.mark.asyncio
async def test_generate_case_board_ops_parses_ops():
    router = _CaseBoardRouter([
        '{"case_board_ops": [{"op_type": "set_field",',
        ' "path": ["current_objective"], "value": "找出真凶", "reason": "新线索"}]}',
    ])
    agent = DirectorAgent(router)
    ops = await agent.generate_case_board_ops(
        scene_brief="甄嬛发现账册", new_clues=["账册"],
        current_board={}, script_type="mystery", discovered_clue_ids=["账册"],
    )
    assert ops == [{
        "op_type": "set_field", "path": ["current_objective"],
        "value": "找出真凶", "reason": "新线索",
    }]


@pytest.mark.asyncio
async def test_generate_case_board_ops_empty_on_garbage():
    router = _CaseBoardRouter(["完全不是 json {{{"])
    agent = DirectorAgent(router)
    ops = await agent.generate_case_board_ops(
        scene_brief="x", new_clues=[], current_board={},
        script_type="mystery", discovered_clue_ids=[],
    )
    assert ops == []
```

- [ ] **Step 3: 跑测试确认失败** —— `cd backend && python -m pytest tests/test_case_board_two_pass.py -v` → FAIL（`AttributeError: generate_case_board_ops`）

- [ ] **Step 4: 实现** —— `engine/director_agent.py` 在 `DirectorAgent` 类内新增方法（放在 `_run_json_mode` 之后）：

```python
    async def generate_case_board_ops(
        self,
        *,
        scene_brief: str,
        new_clues: list,
        current_board: dict,
        script_type: str,
        discovered_clue_ids: list[str],
    ) -> list[dict]:
        """Two-pass case board — a lean standalone JSON call producing
        case_board_ops off the player's critical path. Runs after `done`, so a
        truncation here only affects the case board (non-fatal), never the
        narrative or ending. Returns [] on any failure."""
        import json as _json

        from engine.prompts import (
            build_case_board_generation_prompt,
            build_case_board_ops_schema,
        )

        schema = build_case_board_ops_schema()
        system = (
            build_case_board_generation_prompt(script_type, discovered_clue_ids)
            + "\n\n### JSON Schema\n```\n"
            + _json.dumps(schema, ensure_ascii=False)
            + "\n```"
        )
        user = _json.dumps(
            {
                "scene_brief": scene_brief,
                "new_clues": new_clues,
                "current_case_board": current_board,
            },
            ensure_ascii=False,
        )
        text_parts: list[str] = []
        try:
            async for event in self.llm_router.stream_json(
                messages=[{"role": "user", "content": user}],
                system=system,
                max_tokens=2048,
            ):
                if event["type"] == "text_delta":
                    text_parts.append(event.get("text", ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning("case_board_two_pass.provider_failed", error=str(exc))
            return []

        raw = "".join(text_parts)
        parsed = _extract_json_from_text(raw)
        if parsed is None:
            salvage_src = raw.lstrip()
            if salvage_src.startswith("```"):
                salvage_src = salvage_src.split("\n", 1)[1] if "\n" in salvage_src else ""
            parsed = try_partial_parse(salvage_src) or {}
        ops = parsed.get("case_board_ops")
        return ops if isinstance(ops, list) else []
```

- [ ] **Step 5: 跑测试确认通过** —— `cd backend && python -m pytest tests/test_case_board_two_pass.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/engine/prompts.py backend/engine/director_agent.py backend/tests/test_case_board_two_pass.py
git commit -m "feat(director): generate_case_board_ops 独立轻量调用 + prompt builder"
```

---

## Task 8: orchestrator 接线 two-pass（Phase-3 强制 deferred + Phase-4 分叉）

**Files:**
- Modify: `engine/orchestrator.py:1798`（Phase-3 设 `case_board_deferred`）、`:2262`（Phase-4 分叉）
- Test: 集成靠真跑；flag off 回归靠现有 orchestrator 测试套

- [ ] **Step 1: Phase-3 —— flag on + script 时强制 case_board 走独立生成**

在 `:1798`（`case_board_deferred = game_mode == "script"` 所在的 if/elif 块）之后、`:1820` `director_elapsed_ms = ...` 之前插入：

```python
        # two-pass: 即使 director 完全 resolved（慢路径），也把 case_board 推迟到
        # Phase-4 独立生成 —— 主 schema 已不含 ops（Task 6），director_result.
        # case_board_ops 恒空，:2050 的 inline apply 自然跳过。
        if settings.director_case_board_two_pass and game_mode == "script":
            case_board_deferred = True
```

- [ ] **Step 2: Phase-4 —— 在 `if case_board_deferred:`（`:2262`）内部最前面加 two-pass 分支**，原逻辑落入 `else`：

```python
        if case_board_deferred:
            if settings.director_case_board_two_pass and game_mode == "script":
                ops = await self.director_agent.generate_case_board_ops(
                    scene_brief=director_result.scene_brief,
                    new_clues=(director_result.state_updates or {}).get("new_clues") or [],
                    current_board=game_state.case_board or {},
                    script_type=world_data.get("script_type", ""),
                    discovered_clue_ids=[
                        c.get("id")
                        for c in (getattr(new_state, "discovered_clues", None) or [])
                        if isinstance(c, dict) and c.get("id")
                    ],
                )
                cb_history: list[dict] = []
                if ops:
                    try:
                        new_case_board, cb_history = apply_case_board_ops(
                            new_state.to_dict(), game_state.case_board or {}, ops,
                        )
                        new_state.case_board = new_case_board
                    except CaseBoardError as exc:
                        logger.warning("case_board_invalid_ops", error=str(exc))
                _emit_stage_timing(
                    "case_board_two_pass",
                    director_started,
                    session_id=session_id,
                    round_number=round_number,
                    op_count=len(ops),
                )
                yield {
                    "type": "case_board_update",
                    "new_state": new_state,
                    "game_state": new_state.to_dict(),
                    "case_board_history_entries": cb_history,
                    "mem_extract_input": {
                        "player_action": (director_result.player_action or {}).get("summary", ""),
                        "scene_brief": director_result.scene_brief,
                        "per_npc_focus": director_result.per_npc_focus,
                        "new_clues": (director_result.state_updates or {}).get("new_clues") or [],
                        "case_board_ops": ops,
                        "active_npcs": list(director_result.active_npcs),
                    },
                }
            else:
                try:
                    full_result = await director_task
                except DirectorParseError:
                    full_result = None
                except Exception:  # noqa: BLE001
                    logger.warning("director_v2.tail_await_failed", exc_info=True)
                    full_result = None
                # ... 原有 full_result 处理逻辑保持不变 ...
```

注意：`else` 块里放**原封不动**的现有 `:2263-2304` 逻辑（`full_result = await director_task` 那整段）。只是缩进进 `else`。

- [ ] **Step 3: flag off 回归 —— 跑 orchestrator 测试套确认现状不变**

Run: `cd backend && python -m pytest tests/test_orchestrator.py tests/test_orchestrator_early_stream.py tests/test_orchestrator_v2_loading.py tests/test_orchestrator_timing.py -v`
Expected: 全 PASS（flag 默认 off → `case_board_deferred` 逻辑与改前一致，`else` 分支即原路径）

- [ ] **Step 4: Commit**

```bash
cd /Users/jie/Desktop/code/pokonyan/inkwild
git add backend/engine/orchestrator.py
git commit -m "feat(orchestrator): two-pass 接线——case_board 走独立生成（flag 灰度）"
```

---

## Task 9: 阶段二验证

- [ ] **flag off 全回归**（证明阶段二零破坏）

Run: `cd backend && python -m pytest tests/test_director_tool_clue_constraint.py tests/test_case_board_two_pass.py tests/test_director_agent.py tests/test_director_json_robustness.py tests/test_orchestrator.py tests/test_orchestrator_early_stream.py tests/test_case_board.py -v`
Expected: 全 PASS

- [ ] **flag on 真跑甄嬛传 script 局**（非评测窗口 / 关 reload），设 `DIRECTOR_CASE_BOARD_TWO_PASS=1`，结构化确认：
  - 导演主 JSON 不再含 `case_board_ops`（导演 decode tokens 下降）
  - `case_board_two_pass` stage timing 出现，案件板照常更新（`case_board_update` 事件）
  - 对比阶段一基线：`director_v2` 的 `finish_reason=length` 频率下降（截断率↓）
  - climax 回合 TTFT / director 时延改善（§5.3）
  - 玩家挣到结局时仍 `ending.resolved path=ai`（two-pass 不影响结局——结局信号在主 JSON，已随 case_board 移出而更不易截断）

---

## Self-Review

---

## Self-Review

- **Spec 覆盖**：P0-a→Task1；P0-b.1/.2（截断抢救）→Task2；P1 §3（结局复活）→Task3；P1 §4（弱输入）→Task4；P0-b.3（case_board two-pass）→Task5-8；阶段二验证→Task9。§2「自愈逻辑」校准（真因是网关体积截断、非 max_tokens 不够）体现为「不提 max_tokens、改抢救 + 减体积」。§5.3（climax 延迟）随 Task5-8 减体积顺带改善。§5.1/5.2/5.4/5.5 不在 P0/P1 范围，本 plan 不含。
- **类型一致**：`finish_reason` 全链路 `str | None`，usage 事件 key 统一 `"finish_reason"`；`generate_case_board_ops` 参数名（scene_brief / new_clues / current_board / script_type / discovered_clue_ids）在 Task7 定义、Task8 调用处一字不差；`_CASE_BOARD_OPS_ITEMS`（Task5）→ `build_case_board_ops_schema`（Task7）引用一致；`settings.director_case_board_two_pass`（Task5）在 Task6/8 引用一致。
- **占位扫描**：Task1-9 均含完整代码 + 命令 + 预期。唯一「引用现有代码」处是 Task8 Step2 的 `else` 分支——刻意不重复 40 行现有 `:2263-2304` 逻辑（重复反而易引入抄写错误），指令是「把现有代码原样缩进进 else」，对执行者无歧义。
- **风险隔离**：阶段二全程 flag（默认 off）守护——off 时行为与阶段一逐字节一致，可秒回滚；Task8 Step3 的 flag-off 回归测试钉住这一点。
