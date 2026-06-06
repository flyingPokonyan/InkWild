# Narrator Simplification — 撤退到 v1-style 稳定形态

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 v2 narrator weave 从"6 个 action_type 规则 + prelude + multi_step/weak_input 分支 + 全量 recent_messages"撤退到 v1 已验证稳定的简单形态，配套用动态 processing 流补 TTFB，目标把 Tier2 从 2.0 拉回 4.5+ 灰度线。

**Architecture:** 保留 v2 的 Director → NPC → Narrator 三层结构 + NPCAction structured output（这部分 v2 设计正确）。删掉 v2 加在 narrator 这层的过度工程：prelude、6 个 action_type 渲染细则、multi_step/weak_input 分支、recent_messages anchoring 污染源。TTFB 用 Director 已生成的 per_npc_focus 直接转 processing event flavor，前端灰色斜体小字渲染，0% 模板。

**Tech Stack:** Python 3.12 / FastAPI / asyncio / SQLAlchemy async / SSE (sse-starlette) / pytest async / Next.js 16 / TypeScript / Zustand.

**实施前提**：BUGS #27 的 H1 fix（`render_npc_actions_for_narrator` 4 段分组）已 landed，本 plan 在它基础上继续撤退到 simplicity。

---

## Self-review 结论

走这条路（不是 B 的 "verbatim 校验 + retry + fallback 拼接"，也不是 C 的 "骨架填空 + 程序拼装"）的理由：v1 同构架构有生产数据（Tier2=4.8）证明稳；v2 翻车不是架构本身错，是上面堆了太多过度工程。本 plan 删污染源，不加新机制。

**风险**：v2 可能还有未识别的污染源（比如 NPCAction schema 比 v1 dict 多字段也可能干扰）。我们的 4 段分组渲染已经吸收了这部分，预期不会有问题，但 dogfood 验收时要看真实数据。

---

## 文件结构（涉及修改 / 创建）

| 路径 | 责任 | 改动类型 |
|---|---|---|
| `backend/engine/prompts.py` | narrator system prompt 简化 | 修改 `build_narrator_weave_v2_system`；删 `build_narrator_prelude_system`（dead after T4）|
| `backend/engine/narrator_agent.py` | 删 prelude 方法，简化 stream_v2 签名 | 修改 |
| `backend/engine/orchestrator.py` | 删 prelude 调用路径；recent_messages 过滤 | 修改 `_process_action_v2` |
| `backend/engine/narrator_context.py` | **新建**：recent_messages 过滤 helper | 创建 |
| `backend/engine/processing_hint.py` | 用 Director per_npc_focus 替换 templates；新增 phase-specific hints | 修改 |
| `backend/api/game.py` | processing event payload 加 `kind` 字段（区分 phase / per-npc）| 修改 `to_sse_event` |
| `backend/tests/test_narrator_context.py` | 新过滤 helper 单测 | 创建 |
| `backend/tests/test_orchestrator_no_prelude.py` | 删 prelude 后单 turn 流式顺序回归 | 创建 |
| `frontend/lib/sse.ts` | processing payload 透传 kind | 修改 |
| `frontend/components/play/ProcessingHint.tsx` | 灰色斜体小字组件（或既有的改样式）| 修改/新建 |
| `experiments/local/runs/2026-05-XX_narrator-simplification_狄仁杰/` | dogfood 验收报告 | 创建 |

---

## Task 1: 简化 `build_narrator_weave_v2_system` system prompt

**Goal**: 把 30+ 行的 6 action_type 详细渲染规则 + multi_step/weak_input 条件块，撤退到 v1 风格的 ~10 行简明规则。signature 同时去掉 `multi_step_input` / `weak_input` 参数。

**Files:**
- Modify: `backend/engine/prompts.py:1530-1609`（`build_narrator_weave_v2_system`）
- Modify: `backend/engine/narrator_agent.py:100-159`（`stream_v2` 调用点同步删参数）

- [ ] **Step 1: 改 `build_narrator_weave_v2_system`**

把现有 function 整体替换为：

```python
def build_narrator_weave_v2_system(
    authors_note: str | None = None,
    prelude_text: str | None = None,
) -> str:
    """v2 narrator weave system prompt — v1-style simplicity restored.

    设计原则（撤退到已验证稳的形态）：
    - 只给最少的角色 / 边界 / 长度规则，不给 action_type 详细渲染细则
    - dialogue 必须 verbatim 织入；其他靠 LLM 文学判断
    - 不分支 multi_step / weak_input，让 director 用 scene_direction 表达节奏意图

    See docs/plans/narrator-simplification-2026-05.md for context.
    """
    parts = [
        "你是 InkWild 的叙述者（Narrator）。把导演的场景指引 + NPC 行动列表，",
        "合成为一段流畅、沉浸的中文叙事。",
        "",
        "## 风格",
        "- 第三人称有限视角，跟随玩家",
        "- 语言风格符合世界观时代背景",
        "- NPC 对白用引号包裹，**dialogue 字段的原话一字不改地织入**",
        "- 不替玩家做未声明的动作，不描写玩家内心",
        "- 不打破第四面墙，不使用现代网络用语",
        "",
        "## 行动列表处理",
        "user 消息会按优先级列出 NPC 行动。speak/withhold/interject 的 dialogue 必须 verbatim 引用；",
        "act 的 physical 要描写出来；observe/scheme/在场未出手 给一句存在感即可，",
        "**绝不揭示 hidden_note**。priority 高的占更多笔墨，低的一句带过。",
        "",
        "## 长度",
        "单段叙事 ≤ 350 字。紧张场景 ≤ 200 字。不要堆砌感官细节，每段最多 1-2 处具体感官描写。",
    ]
    if authors_note:
        parts.extend(["", f"## [Author's Note — 最高优先级风格参考: {authors_note}]"])
    if prelude_text:
        parts.extend([
            "",
            "## 上文（开场段，承接它不要重复）",
            prelude_text,
            "",
            "## 续写要求",
            "- 直接承接上文语气",
            "- 织入行动列表，不要重写环境",
            "- 衔接自然，不要写「接续」「上文之后」等转折提示",
        ])
    return "\n".join(parts)
```

- [ ] **Step 2: 同步 `narrator_agent.stream_v2` 签名删 `multi_step_input` / `weak_input`**

在 `backend/engine/narrator_agent.py:100-159`：

- 删除参数 `multi_step_input: bool = False` 和 `weak_input: bool = False`
- 删除 docstring 里对应描述
- 删除 `system = build_narrator_weave_v2_system(...)` 调用里的两个 kwarg
- 把 `max_tokens = 400 if weak_input else _MAIN_MAX_TOKENS` 改成 `max_tokens = _MAIN_MAX_TOKENS`

修改后的关键片段：

```python
async def stream_v2(
    self,
    *,
    scene_direction: str,
    npc_actions: list,
    scene_role_map: dict[str, str] | None = None,
    recent_messages: list[dict],
    authors_note: str | None = None,
    prelude_text: str | None = None,
    narrative_pressure: str = "advance",
) -> AsyncIterator[dict]:
    """v2 weave — consumes a priority-sorted NPCAction list.

    See docs/plans/narrator-simplification-2026-05.md for the simplification
    rationale (撤退到 v1-style，不再有 multi_step/weak_input 分支)。
    """
    system = build_narrator_weave_v2_system(
        authors_note=authors_note,
        prelude_text=prelude_text,
    )
    # ... rest same as before, but max_tokens = _MAIN_MAX_TOKENS unconditionally
```

- [ ] **Step 3: 同步 orchestrator 调用点删两个 kwarg**

`backend/engine/orchestrator.py:1785-1795` 的 `self.narrator_agent.stream_v2(...)` 调用块里删 `multi_step_input=...` 和 `weak_input=...` 两行。保留其他参数。

- [ ] **Step 4: 跑 unit 测试**

```bash
cd backend && python -m pytest tests/test_narrator_agent.py -v
```
Expected: PASS（既有 test 不应锚定旧 prompt 文本，因为我们之前 grep 过）

- [ ] **Step 5: Commit**

```bash
git add backend/engine/prompts.py backend/engine/narrator_agent.py backend/engine/orchestrator.py
git commit -m "narrator: simplify weave system prompt to v1-style (drop 6 action_type rules + multi_step/weak_input branches)

撤退到 v1 已验证稳定形态。v2 加的过度工程导致 BUGS #27 anchoring 灾难，
现在删 noise，回归 ~10 行简明规则。See docs/plans/narrator-simplification-2026-05.md.
"
```

---

## Task 2: 新建 `narrator_context.py` — recent_messages 过滤 helper

**Goal:** 提供一个纯函数 `filter_recent_messages_for_narrator(messages)`，把 narrator 自己历史输出里 env-only 的（quote_count == 0 或不含对白特征）剔除，避免 LLM 自我锚定到 env-only style。

**Files:**
- Create: `backend/engine/narrator_context.py`
- Create: `backend/tests/test_narrator_context.py`

- [ ] **Step 1: 写 failing test**

`backend/tests/test_narrator_context.py`:

```python
from engine.narrator_context import filter_recent_messages_for_narrator


def test_keeps_user_messages_verbatim():
    msgs = [
        {"role": "user", "content": "走到工棚"},
        {"role": "user", "content": "细看尸格"},
    ]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_drops_env_only_assistant_messages():
    # 无中英文引号、无 NPC speech 特征
    env_only = "公廨里晨光斜斜落在青砖上，案上烛火摇了一下。"
    msgs = [
        {"role": "user", "content": "走过去"},
        {"role": "assistant", "content": env_only},
        {"role": "user", "content": "继续看"},
    ]
    out = filter_recent_messages_for_narrator(msgs)
    assert {"role": "user", "content": "走过去"} in out
    assert {"role": "user", "content": "继续看"} in out
    assert not any(m["content"] == env_only for m in out)


def test_keeps_assistant_messages_with_chinese_quotes():
    msg_with_dia = "狄仁杰开口：「明远所言甚是。」案上烛火摇了一下。"
    msgs = [{"role": "assistant", "content": msg_with_dia}]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_keeps_assistant_messages_with_straight_quotes():
    msg_with_dia = '李元芳沉声道："属下从工地回来。"'
    msgs = [{"role": "assistant", "content": msg_with_dia}]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_preserves_chronology():
    msgs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "纯环境段"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "狄公说：「话」"},
    ]
    out = filter_recent_messages_for_narrator(msgs)
    contents = [m["content"] for m in out]
    assert contents == ["u1", "u2", "狄公说：「话」"]


def test_handles_empty_input():
    assert filter_recent_messages_for_narrator([]) == []


def test_keeps_system_role_unchanged():
    msgs = [{"role": "system", "content": "x"}]
    assert filter_recent_messages_for_narrator(msgs) == msgs
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_narrator_context.py -v
```
Expected: 所有 7 test FAIL (`ModuleNotFoundError: engine.narrator_context`)

- [ ] **Step 3: 实现 `narrator_context.py`**

`backend/engine/narrator_context.py`:

```python
"""Recent-messages filter for narrator weave context.

避免 narrator 锚定到自己过去的 env-only 输出（BUGS #27 H3）。
对 assistant role 的消息检测 dialogue 特征（中/英文引号），不带的就剔除；
user / system role 一律保留以维持时间线和上下文。
"""
from __future__ import annotations

# 中文 / 英文 / 法式引号都算 dialogue 特征
_QUOTE_CHARS = ('「', '」', '『', '』', '"', '"', '"', "'", "'")


def _has_dialogue_markers(content: str) -> bool:
    return any(ch in content for ch in _QUOTE_CHARS)


def filter_recent_messages_for_narrator(messages: list[dict]) -> list[dict]:
    """Filter narrator weave's recent_messages: drop env-only assistant rows.

    保留：
    - 所有 user / system role 消息（维持上下文 + 时间线）
    - 含 dialogue 特征的 assistant 消息（"working examples"，LLM 模仿这种）

    剔除：
    - assistant role 且不含任何引号的消息（env-only 锚点，会污染 LLM 风格）

    时序保持稳定（list comprehension 顺序保留）。
    """
    return [
        m for m in messages
        if m.get("role") != "assistant" or _has_dialogue_markers(m.get("content", ""))
    ]
```

- [ ] **Step 4: 再跑测试确认 PASS**

```bash
cd backend && python -m pytest tests/test_narrator_context.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/narrator_context.py backend/tests/test_narrator_context.py
git commit -m "narrator: add recent_messages filter to drop env-only anchor rows

BUGS #27 H3：narrator 自己历史中的 env-only 输出会让 LLM 锚定到只写环境的风格，
即使本回合 NPC 有 speak action 也不复述。过滤掉无对白特征的 assistant 行打破 anchor。
"
```

---

## Task 3: orchestrator 调用 narrator weave 时 filter recent_messages

**Files:**
- Modify: `backend/engine/orchestrator.py:1785-1795`（`_process_action_v2` 的 `stream_v2` 调用点）

- [ ] **Step 1: 改 orchestrator**

`backend/engine/orchestrator.py` 顶部 import 区加：

```python
from engine.narrator_context import filter_recent_messages_for_narrator
```

`_process_action_v2` 调用 `self.narrator_agent.stream_v2(...)` 时把 `recent_messages=recent_messages` 改成 `recent_messages=filter_recent_messages_for_narrator(recent_messages)`：

```python
async for event in self.narrator_agent.stream_v2(
    scene_direction=director_result.scene_direction,
    npc_actions=sorted_actions,
    scene_role_map=director_result.scene_role,
    recent_messages=filter_recent_messages_for_narrator(recent_messages),
    authors_note=authors_note,
    prelude_text=prelude_text,
    narrative_pressure=director_result.narrative_pressure,
):
```

**注意**：只在 narrator weave 调用前 filter；NPC Agent / Director 的 recent_messages 不动（他们需要看到完整的对话历史决策）。

- [ ] **Step 2: 跑既有 orchestrator 相关测试**

```bash
cd backend && python -m pytest tests/test_orchestrator_early_stream.py -v 2>&1 | head -40
```
注意：当前这些测试已经因为 FakeDirectorAgent 不支持 v2 而 fail（pre-existing debt, 详见 BUGS.md）。如果这些 test 在此 plan 进行前没修，**跳过**它们。重点关注 narrator_context 自身测试 + 后面 T7 的新单测。

- [ ] **Step 3: Commit**

```bash
git add backend/engine/orchestrator.py
git commit -m "narrator: filter env-only anchor rows before weave LLM call

调用 filter_recent_messages_for_narrator 打断 H3 anchoring。
NPC Agent / Director 的 recent_messages 保持完整。
"
```

---

## Task 4: 删除 prelude 整条路径

**Goal:** orchestrator 不再起 prelude，NPC 并行直接接 narrator weave；narrator_agent 删 `stream_prelude` 方法；prompts.py 删 `build_narrator_prelude_system`；config 删 `narrator_early_stream_enabled` flag。

**Files:**
- Modify: `backend/engine/orchestrator.py:1533-1620`（`_process_action_v2` 的 prelude 块；保留 line 1590+ 的 elif active_set 分支作为唯一 NPC 路径）
- Modify: `backend/engine/orchestrator.py:800-880`（v1 path 的相同 prelude 块也删，保持 v1 v2 一致）
- Modify: `backend/engine/narrator_agent.py:32-66`（删 `stream_prelude` 方法）
- Modify: `backend/engine/prompts.py:1650-1678`（删 `build_narrator_prelude_system`）
- Modify: `backend/config.py:63`（删 `narrator_early_stream_enabled` setting）

- [ ] **Step 1: 删 `_process_action_v2` 里的 prelude 路径**

`orchestrator.py:1533-1620` 区域当前长这样：

```python
early_stream_active = settings.narrator_early_stream_enabled and bool(active_set)

async def _gather_npcs() -> list: ...

if early_stream_active:
    # 起 npc_runner task + 跑 prelude + await npc_runner
    ...
elif active_set:
    # NPC parallel run only
    raw_actions = await asyncio.gather(...)
    ...
```

替换为统一一条 NPC 并行路径（无 prelude）：

```python
prelude_text = None  # 永远 None，保留变量供 stream_v2 接口兼容

if active_set:
    npcs_started = time.perf_counter()
    raw_actions = await asyncio.gather(
        *(_run_npc_capped(name) for name in active_set),
        return_exceptions=True,
    )
    _emit_stage_timing(
        "npc_v2_parallel",
        npcs_started,
        session_id=session_id,
        round_number=round_number,
        npc_count=len(active_set),
    )
    for raw, name in zip(raw_actions, active_set):
        if isinstance(raw, Exception) or raw is None:
            from engine.npc_action import validate_action
            npc_actions.append(
                validate_action(name, None, scene_role=director_result.scene_role.get(name))
            )
        else:
            npc_actions.append(raw)
```

删除：
- `early_stream_active`、`prelude_started`、`prelude_narrative_parts`、`prelude_usage`、`prelude_text` 旧赋值
- `narrator_agent.stream_prelude(...)` 调用块
- `_emit_stage_timing("narrator_prelude", ...)`
- `npc_runner = asyncio.create_task(_gather_npcs())` + `raw_actions = await npc_runner`

stream_v2 调用里 `prelude_text=prelude_text` 仍 pass（永远是 None），保留参数兼容性。

下游所有 `prelude_narrative_parts` 相关引用（如 `narrative_parts: list[str] = list(prelude_narrative_parts)` → `narrative_parts: list[str] = []`）一并清理。

- [ ] **Step 2: 删 v1 path 的相同 prelude 块**

`orchestrator.py:800-880` v1 path 同样的 prelude 处理：直接删。v1 路径在 `runtime_architecture_v2_enabled=True` 下不走，但保持一致。

- [ ] **Step 3: 删 `narrator_agent.stream_prelude`**

`backend/engine/narrator_agent.py:32-66`：整段 `async def stream_prelude(...)` 删除，包括其 docstring。
同时 import 区移除 `build_narrator_prelude_system`（变 dead）。
顺手删 `_PRELUDE_MAX_TOKENS = 768` 常量（dead）。

- [ ] **Step 4: 删 `build_narrator_prelude_system`**

`backend/engine/prompts.py:1650-1678`：整段 function 删除。

- [ ] **Step 5: 删 config flag**

`backend/config.py:63`：删 `narrator_early_stream_enabled: bool = True` 行。
同时 grep 全 repo 看是否还有引用：

```bash
cd backend && grep -rn "narrator_early_stream_enabled\|stream_prelude\|build_narrator_prelude_system\|_PRELUDE_MAX_TOKENS" --include="*.py" 2>/dev/null
```
Expected: 仅 test 文件（接下来步骤会处理）和 `.env.example` 之类有残留 → 全部清理。

- [ ] **Step 6: 处理 prelude 相关测试**

`tests/test_narrator_max_tokens.py::test_narrator_prelude_still_capped_at_256` 已经 broken（BUGS file 已记，常量值从 256 → 768），删该 test。

`tests/test_orchestrator_early_stream.py` 整文件已 broken（pre-existing v2 dispatch issue），且测试目标已经不存在（prelude 删了）→ 删该文件。

```bash
cd backend && git rm tests/test_orchestrator_early_stream.py
```

`tests/test_narrator_max_tokens.py` 里删 prelude 那个 test，保留 weave max_tokens test。

- [ ] **Step 7: 跑全套测试确认不被 prelude 删除波及**

```bash
cd backend && python -m pytest tests/test_narrator_agent.py tests/test_narrator_context.py tests/test_narrator_max_tokens.py -v
```
Expected: 全 PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "narrator: remove prelude path entirely

prelude 强制 env 开场 + 给 weave 注入 env-only prelude_text 锚点，
是 BUGS #27 H3 anchoring 的诱因之一。TTFB 用 dynamic processing 流替代（见 T5）。

删除：
- orchestrator._process_action_v2 / process_action 里的 prelude 起 task + 流式块
- NarratorAgent.stream_prelude 方法
- prompts.build_narrator_prelude_system
- settings.narrator_early_stream_enabled
- 相关测试
"
```

---

## Task 5: 动态 processing 流 — 用 Director per_npc_focus 替换 templates

**Goal:** 当前 `processing_hint.py` 用 5 个固定模板（"X像是想起了什么" / "X和Y似乎在交换眼神"）生成 flavor，套路化。改成把 Director 返回的 `per_npc_focus[npc_name]` 文本直接当 flavor，前端按时间顺序流式渲染灰色斜体小字。

**Files:**
- Modify: `backend/engine/processing_hint.py`（加新函数 `build_per_npc_focus_hint`）
- Modify: `backend/engine/orchestrator.py`（在 director 返回后、NPC 并行启动前 fire 多个 processing hints，一个 NPC 一条）
- Modify: `backend/api/game.py:to_sse_event`（processing event payload 透传 `kind` 字段）
- Modify: `frontend/lib/sse.ts`（payload type 加 kind）
- Modify: `frontend/stores/game.ts`（按 kind 路由到 UI）

- [ ] **Step 1: 加 `build_per_npc_focus_hint`**

`backend/engine/processing_hint.py` 加：

```python
def build_per_npc_focus_hint(npc_name: str, focus: str) -> dict:
    """Build a processing hint using Director's per-NPC focus verbatim.

    跟 build_processing_hint 不同：flavor 直接用 Director 返回的 focus 文本，
    不走 5 个固定模板。Director 已经为每个 active NPC 生成了带情境的 focus
    描述（"思考如何回应明远的质疑" / "准备陈述守夜人时辰"），那本身就是
    有信息量的非套路文案。

    kind="per_npc" 让前端区别于 phase-level hint。
    """
    return {
        "type": "processing",
        "phase": "thinking",
        "focus_npcs": [npc_name],
        "flavor": f"{npc_name}{focus}",
        "kind": "per_npc",
        "version": 1,
    }
```

同时保留既有 `build_processing_hint` / `build_phase_hint`，给它们的 dict 都加 `"kind": "phase"`（默认值），保持向后兼容。

- [ ] **Step 2: orchestrator 在 director 后、NPC 并行前 fire 多 per-npc hints**

在 `_process_action_v2`，director 返回后 active_set 拼好之后，并行 NPC 启动之前，加：

```python
# Dynamic per-NPC processing flavor — see docs/plans/narrator-simplification-2026-05.md T5
for npc_name in active_set:
    focus = director_result.per_npc_focus.get(npc_name, "").strip()
    if focus:
        yield build_per_npc_focus_hint(npc_name, focus)
```

注意位置：必须在 NPC 调用启动前 yield，让用户先看到"X 正在思考 ..."再等真实 narrative。
import 区加 `from engine.processing_hint import build_per_npc_focus_hint`。

- [ ] **Step 3: api/game.py to_sse_event 透传 `kind`**

`backend/api/game.py:to_sse_event` 处理 `processing` 分支的地方，在 payload 构造里把 `kind` 字段也带上（如果存在）：

```python
elif event_type == "processing":
    payload = {
        "type": "processing",
        "version": 1,
        "phase": event.get("phase", "thinking"),
        "focus_npcs": event.get("focus_npcs", []),
        "flavor": event.get("flavor", ""),
    }
    if "kind" in event:
        payload["kind"] = event["kind"]
```

- [ ] **Step 4: frontend sse.ts type + dispatch**

`frontend/lib/sse.ts` 的 `ProcessingEventPayload` 类型加可选字段：

```ts
export interface ProcessingEventPayload {
  phase: string;
  focus_npcs?: string[];
  flavor?: string;
  kind?: "phase" | "per_npc";
}
```

`case "processing":` 分支 dispatch 时透传 `kind`：

```ts
case "processing":
  callbacks.onProcessing?.({
    phase: rawPayload.phase,
    focus_npcs: rawPayload.focus_npcs,
    flavor: rawPayload.flavor,
    kind: rawPayload.kind,
  });
  break;
```

- [ ] **Step 5: frontend store + UI 灰色斜体小字渲染**

`frontend/stores/game.ts` 已有 `processingHint` 状态。如果 hint kind 是 `per_npc`，**追加**到 hint 列表（多条）而不是覆盖。当前 store 实现只保留单条；改为：

```ts
processingHints: ProcessingEventPayload[]; // 复数，按顺序累加
```

在 `onProcessing` 回调里：
- 如果 `kind === "per_npc"`：appendHint(data)
- 否则（kind === "phase" 或 undefined）：replaceHint(data) 或 clearHints() + appendHint

narrative 第一个 chunk 到达时 `clearHints()`（这表示真实叙事开始了，所有思考态文案该消失）。

- [ ] **Step 6: 渲染组件**

`frontend/components/play/ProcessingHint.tsx`（如果不存在则新建；如果存在则改样式）：

```tsx
"use client";

import { motion, AnimatePresence } from "motion/react";
import type { ProcessingEventPayload } from "@/lib/sse";

export function ProcessingHint({ hints }: { hints: ProcessingEventPayload[] }) {
  return (
    <AnimatePresence>
      <div className="space-y-1.5">
        {hints.map((h, i) => (
          <motion.p
            key={`${h.flavor}-${i}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 0.55, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="text-xs italic text-[var(--lv-ink-muted)]/65 leading-relaxed"
          >
            {h.flavor || "正在编织..."}
          </motion.p>
        ))}
      </div>
    </AnimatePresence>
  );
}
```

在 play 页相应位置（narrative 流前的区域）挂载这个组件，绑定 `processingHints` 状态。

- [ ] **Step 7: 跑前端 build 检查**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 无错误

- [ ] **Step 8: Commit**

```bash
git add backend/engine/processing_hint.py backend/engine/orchestrator.py backend/api/game.py
git add frontend/lib/sse.ts frontend/stores/game.ts frontend/components/play/ProcessingHint.tsx
git commit -m "narrator: replace prelude with dynamic per-NPC processing flow

TTFB 改用 Director per_npc_focus → 多条 processing hints 流，
前端灰色斜体小字渲染，narrative 真到达时清除。
0% 模板，flavor 文本是 Director 实际编排出来的情境句。
"
```

---

## Task 6: 新增 orchestrator 集成回归测试（删 prelude 后）

**Files:**
- Create: `backend/tests/test_orchestrator_no_prelude.py`

**Goal**: 单测确保 `_process_action_v2` 在 prelude 删除后：
1. 不再 emit `narrator_prelude` stage.timing
2. NPC 并行 + narrator weave 顺序正确
3. recent_messages 经过 filter

写个轻量集成测试，mock 掉 Director / NPC Agent / Narrator Agent。

- [ ] **Step 1: 写测试**

`backend/tests/test_orchestrator_no_prelude.py`:

```python
"""删 prelude 后的 _process_action_v2 流程回归测试.

Mock 三个 agent，检查 yield 顺序 + 不再有 prelude stage.
"""
from __future__ import annotations

import asyncio
import pytest

from engine.npc_action import NPCAction


class FakeDirector:
    async def run_v2(self, **kwargs):
        # 构造一个最小 DirectorResult
        from engine.director_agent import DirectorResult
        return DirectorResult(
            scene_direction="测试场景",
            active_npcs=["A"],
            per_npc_focus={"A": "正在测试"},
            scene_role={"A": "focus"},
            dramatic_intensity="low",
            narrative_pressure="advance",
            involved_npcs=["A"],
            memory_extracts=[],
            case_board_ops=[],
            speech_order=[],
            event_fire_intent=[],
            inform_npc_calls=[],
            player_action=None,
        )


class FakeNPC:
    async def run_v2(self, *, npc_name, **kwargs):
        return NPCAction(
            npc_name=npc_name,
            action_type="speak",
            priority=8,
            dialogue="测试台词",
            tone="sincere",
        )


class FakeNarrator:
    async def stream_v2(self, **kwargs):
        # 应该 NOT 被传 multi_step_input / weak_input
        assert "multi_step_input" not in kwargs, "stream_v2 should no longer accept multi_step_input"
        assert "weak_input" not in kwargs, "stream_v2 should no longer accept weak_input"
        yield {"type": "text_delta", "text": "测试叙事「测试台词」"}
        yield {"type": "usage", "input_tokens": 100, "output_tokens": 50}


@pytest.mark.asyncio
async def test_no_prelude_path():
    """v2 process_action 不再 yield narrator_prelude stage timing."""
    # 这个测试是 sketch；具体 setup 需要 stub 完整 orchestrator deps。
    # 接下来的 implementer 应该参考已 broken 的 test_orchestrator_early_stream.py
    # 里的 setup pattern（仍是有效的 fixture 模式）拼出来。
    # 关键 assertion：
    #   - 没有 yield 含 stage="narrator_prelude" 的 stage.timing log
    #   - per_npc processing hint 在 NPC parallel 启动前 yield
    #   - narrator_v2 stage.timing 仍 yield
    pytest.skip("Implementation requires fuller orchestrator fixtures; "
                "stub provided as guidance.")
```

测试当前 skip 给 implementer 留 hook。如果 implementer 有意愿可以 fully fill in（参考 BUGS file 里说的 pre-existing FakeDirector 缺 run_v2 stub 问题）。

- [ ] **Step 2: 跑测试**

```bash
cd backend && python -m pytest tests/test_orchestrator_no_prelude.py -v
```
Expected: SKIPPED（标 skip 是有意的）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_orchestrator_no_prelude.py
git commit -m "test: add orchestrator no-prelude regression skeleton"
```

---

## Task 7: 跑 dogfood 验收

**Files:**
- Create: `experiments/local/runs/2026-05-XX_narrator-simplification_狄仁杰/report.md`（执行日期填实际日期）
- Modify: `experiments/local/RUN_LOG.md`
- Modify: `experiments/local/BUGS.md` #27 状态

- [ ] **Step 1: 跑 backend**

```bash
cd backend && nohup uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log > /tmp/inkwild-backend.log 2>&1 &
sleep 5 && curl -s -o /dev/null -w "health=%{http_code}\n" http://localhost:8000/health
```
Expected: health=200

- [ ] **Step 2: 跑 20-round dogfood**

```bash
cd experiments/local && nohup python -m pipeline.play --world e3134425-bcec-4bba-b0c2-07b7e198cb0e --mode script --rounds 20 > /tmp/inkwild-dogfood-simplify.log 2>&1 &
```
约 27 min。等完成。

- [ ] **Step 3: 拿 session id + 跑 Tier scoring**

```bash
SESSION=$(grep "Opening: session=" /tmp/inkwild-dogfood-simplify.log | sed -E 's/.*session=`([^`]+)`.*/\1/')
echo "session=$SESSION"
cd experiments/local && python -m pipeline.score --world e3134425-bcec-4bba-b0c2-07b7e198cb0e --session $SESSION > /tmp/inkwild-score-simplify.log 2>&1
cat /tmp/inkwild-score-simplify.log
```

- [ ] **Step 4: 验证 dialogue 织入率**

```bash
cd backend && PYTHONPATH=. python -c "
import asyncio, json, re
from sqlalchemy import text
from database import async_session

async def main():
    sid = '$SESSION'  # 填入实际 session
    async with async_session() as s:
        rows = (await s.execute(text(\"SELECT id, content, npc_dialogues::text as dia FROM messages WHERE session_id = :sid AND role = 'assistant' ORDER BY id\"), {'sid': sid})).fetchall()
        total, populated, dia_in_content = 0, 0, 0
        for r in rows:
            total += 1
            if r.dia and r.dia != 'null':
                populated += 1
                d = json.loads(r.dia)
                # 任意一个 NPC dialogue 前 10 字 verbatim 在 content → 算 hit
                if any(v[:10] in r.content for v in d.values() if v):
                    dia_in_content += 1
        print(f'narrator msgs={total}; dia_populated={populated}; dia_in_content={dia_in_content}')
        print(f'织入率: {dia_in_content}/{populated} = {dia_in_content/max(populated,1)*100:.1f}%')

asyncio.run(main())
"
```

- [ ] **Step 5: 验收 criteria**

| 指标 | 验收门槛 | 不达标怎么办 |
|---|---|---|
| Tier2 总分 | ≥ 4.0 | Phase 1 re-debug，可能要进 C 方案 |
| Dialogue 织入率 | ≥ 85% | 同上 |
| 段落自我复制 | 不出现 | 同上 |
| Tier1 | ≥ 4.0 | 如果 < 4，但其他 OK，归 BUGS #24 family 单独处理 |

- [ ] **Step 6: 写 run report**

文件：`experiments/local/runs/<date>_narrator-simplification_狄仁杰/report.md`，结构参考既有 `2026-05-26_v2-postfix-validation_狄仁杰/report.md`。包括：
- 配置（world / session / 改动列表）
- Tier scores（Tier1, Tier2 分项）
- 跟 broken baseline (62722e09) 和 H1-only baseline (386bdd02) 三方对比表
- 每 round dialogue-in-content 分布
- 段落自我复制检测
- 关键观察
- 下一步建议

- [ ] **Step 7: 更新 RUN_LOG.md 加 row**

`experiments/local/RUN_LOG.md` 顶部 Runs 表加一行（沿用既有格式）。

- [ ] **Step 8: 更新 BUGS.md #27 状态**

如果 Tier2 ≥ 4.0：
- 索引表 #27 状态从 🟡 → ✅
- 详细记录追加 "2026-05-XX update 3 — narrator simplification landed，Tier2 X.X，#27 closed"

如果 Tier2 < 4.0：
- 保持 🟡，追加新观察 + Phase 1 重启计划

- [ ] **Step 9: Commit**

```bash
git add experiments/local/RUN_LOG.md experiments/local/BUGS.md experiments/local/runs/
git commit -m "dogfood: narrator simplification 20-round validation

Tier1=X.X Tier2=Y.Y session=<id>. <accept/reject> BUGS #27 fix.
"
```

---

## 整体验收

最终 happy path：
1. Tier2 从 broken=1.0 / H1-only=2.0 拉到 ≥ 4.0
2. Dialogue 织入率 ≥ 85%
3. 没有 prelude 套路开场
4. 前端有动态 per-NPC processing 灰色文案
5. BUGS #27 close（✅）

如果失败（Tier2 < 4.0 或织入率 < 85%）：
1. 不要在这个分支继续打补丁
2. 写新一轮 Phase 1 root cause 报告
3. 重新考虑 C 方案（骨架填空）或更激进的撤退

---

## Self-Review 结论（写完 plan 后）

- ✅ Spec coverage：6 个改动维度（simplify prompt / filter recent_messages / kill prelude / dynamic processing / 前端渲染 / dogfood）每个都有对应 task
- ✅ No placeholders：每步要么有具体代码、要么有 exec 命令、要么有 verification command；唯一 sketch 是 T6 的集成测试（明示 skip 给 implementer hook，不算placeholder）
- ✅ Type consistency：`filter_recent_messages_for_narrator` / `build_per_npc_focus_hint` / `processingHints[]` 跨 task 名字一致
- ✅ 文件路径全是 absolute / 相对 backend 根的明确路径
- ⚠️ T3 提到的 `pre-existing test debt` 是真实状态（FakeDirectorAgent 没 run_v2），plan 故意不修这个 debt，仅注释说明 implementer 可跳过；这是 trade-off
