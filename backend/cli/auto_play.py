"""End-to-end auto-play harness for InkWild case-board research.

Drives the full workshop + game flow against a running backend:

  1. dev-login (cookie)
  2. for each (description, genre, era) pack:
       - POST /workshop/world-generation-tasks  (phase A Stage 0)
       - consume SSE until done; grab draft_id
       - POST /workshop/world-drafts/{id}/continue-generation (phase B)
       - consume SSE until done
       - POST /workshop/world-drafts/{id}/publish -> world_id
       - POST /workshop/script-generation-tasks (world_id) -> script draft
       - consume SSE until done
       - POST /workshop/script-drafts/{id}/publish -> script_id
       - pick a character from the world
       - POST /api/game/start -> session_id
       - loop N rounds:
            * sample a simulated-player utterance via Xiaomi mimo
            * POST /api/game/{sid}/action; drain SSE; capture narrative/errors
       - at session end: pull all messages + final state + research jsonl
       - call Xiaomi (or any LLM) with a synthesis prompt; write summary.md

Outputs go to ``backend/research/`` (settings.case_board_research_dir).

Usage::

    cd backend
    source .venv/bin/activate
    ENABLE_DEV_AUTH=true CASE_BOARD_RESEARCH=true MOCK_IMAGES=true \\
      python -m cli.auto_play  --rounds 25

Each world is wrapped in a try; one failure does not abort the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _load_dotenv() -> None:
    """Minimal .env reader so XIAOMI_* / MOCK_IMAGES / CASE_BOARD_RESEARCH are
    visible to the harness (pydantic-settings only feeds the backend process)."""
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


_load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("AUTOPLAY_BACKEND_URL", "http://localhost:8000")
XIAOMI_BASE = os.environ.get("XIAOMI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
XIAOMI_KEY = os.environ.get("XIAOMI_API_KEY", "")
XIAOMI_MODEL = os.environ.get("XIAOMI_MODEL", "mimo-v2.5")
RESEARCH_DIR = BACKEND_DIR / os.environ.get("CASE_BOARD_RESEARCH_DIR", "research")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

# Per-step / per-stream timeouts (generous because LLM gen is slow).
HTTP_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)
SSE_IDLE_TIMEOUT_S = 480.0
WORLD_TASK_TIMEOUT_S = 900.0  # 15 min upper bound on a single workshop task


# ---------------------------------------------------------------------------
# Pre-defined world packs to generate
# ---------------------------------------------------------------------------


@dataclass
class WorldPack:
    slug: str          # short id, used in filenames
    description: str   # 给 workshop 的自然语言描述
    genre: str
    era: str
    fidelity: str      # "strict" | "loose" | "none"
    kind: str          # "original" | "ip"
    ip_name: str = ""  # 只 IP 用，方便后续还原度评估
    canonical_elements: list[str] = field(default_factory=list)  # IP 必备元素清单
    script_outline: str = ""   # 给 script 生成的剧本提示
    # Game mode at /game/start time. "script" needs a script_id; "free" skips
    # script gen entirely and runs the world as open sandbox.
    mode: str = "script"
    # When set, skip world+script generation and use this existing world_id
    # for the playthrough. Useful for free-mode verification against a
    # previously-published world.
    reuse_world_id: str = ""
    # When set together with reuse_world_id and mode="script", skip script
    # generation too and play this existing published script. Lets a script-mode
    # playthrough isolate game-loop cost without any workshop generation noise.
    reuse_script_id: str = ""


WORLD_PACKS: list[WorldPack] = [
    # Cost-reconciliation — reuse a published world+script, script mode, no
    # workshop generation. Isolates pure game-loop spend on the bound provider.
    WorldPack(
        slug="jiyu-dangpu-reuse",
        kind="original",
        mode="script",
        reuse_world_id="5147d389-c292-4405-9d96-cbaef59e3f3c",
        reuse_script_id="167fd1d7-5543-4a63-aa7f-ce7be398ab6e",
        description=(
            "（复用已发布的『记忆典当行』世界 + 剧本）"
            "现代都市表层之下的一家记忆典当行，老板娘收购顾客的记忆。"
            "玩家是新搬进同栋楼的房客，被卷入三天三夜的典当客故事，"
            "在 NPC 关系与道德抉择中逼近老板娘记忆抽屉的真相。"
        ),
        genre="都市奇幻 / 情感",
        era="当代",
        fidelity="none",
        script_outline="情感类（emotional），三晚结构，重在 NPC 关系 + 道德抉择，弱推理强情感",
    ),
    # Free-mode verification — reuse the existing yexingguan world; play 30
    # rounds in open sandbox to validate: case_board stays empty, /case-board
    # 404 throughout, no orchestrator crashes, compression path triggers
    # past max_context_rounds=15, stage_summary fires.
    WorldPack(
        slug="yexingguan-free",
        kind="original",
        mode="free",
        reuse_world_id="783ee03a-cb71-4d5d-98c2-9d7fa902130e",
        description=(
            "（自由模式 · 复用已发布的『夜行馆疑云』世界）"
            "民国上海法租界深处的私人会所『夜行馆』。"
            "玩家是一个能自由走动的访客，没有谁雇你、没有谁要被找回——"
            "你想做什么都可以：跟客人闲聊、撬锁、偷酒、跟踪馆员、"
            "甚至跟馆主对赌一局。开放沙盒。"
        ),
        genre="民国都市沙盒",
        era="1934 上海法租界",
        fidelity="none",
        script_outline="自由模式无剧本（剧本字段不会被使用）",
    ),
    WorldPack(
        slug="yexingguan",
        kind="original",
        description=(
            "民国 1934 年上海法租界，霞飞路深处一栋叫『夜行馆』的私人会所。"
            "近两个月有 5 位常客陆续失踪，最后一次都在馆内打过照面。"
            "玩家是一个被馆主匿名雇来的私家侦探，被允许在馆内自由走动一夜，"
            "需要在拂晓鸣钟前找出第 6 位即将消失的人。"
        ),
        genre="民国悬疑推理",
        era="1934 上海法租界",
        fidelity="none",
        script_outline="推理类（mystery），单晚发生，4 个嫌疑常客 + 2 个馆员；以连环失踪为主线",
    ),
    WorldPack(
        slug="memory-pawnshop",
        kind="original",
        description=(
            "现代都市表层之下的一家『记忆典当行』，老板娘可以收购顾客的某段记忆，"
            "换给他们当下最缺的东西——勇气、时间、谅解、甚至别人的一段记忆。"
            "玩家是新搬进同栋楼的房客，第一晚就被推门进来的老熟客拖入店内。"
            "剧情聚焦在三天三夜里玩家见过的 3 位典当客户、典当后的代价、"
            "以及一个谜团：老板娘自己的记忆抽屉里到底锁着什么。"
        ),
        genre="都市奇幻 / 情感",
        era="当代",
        fidelity="none",
        script_outline="情感类（emotional），三晚结构，重在 NPC 关系 + 道德抉择，弱推理强情感",
    ),
    WorldPack(
        slug="hp-forbidden-forest",
        kind="ip",
        ip_name="哈利·波特",
        description=(
            "原作设定『哈利·波特』系列。"
            "故事设定在哈利六年级开学第二周的霍格沃茨。"
            "禁林边缘的护林小屋附近，连续三天发现学生失踪后又在拂晓被找回，"
            "但他们一句话都说不出。海格被怀疑，邓布利多让哈利、罗恩、赫敏暗中调查。"
            "玩家扮演这三人中的任一位，可以使用魔法、参考霍格沃茨课程与建筑。"
        ),
        genre="奇幻 / 学院悬疑",
        era="霍格沃茨 学年中",
        fidelity="strict",
        canonical_elements=[
            "霍格沃茨", "邓布利多", "麦格教授", "海格", "禁林",
            "格兰芬多", "斯莱特林", "魔杖", "魔咒", "金色飞贼",
            "对角巷", "猫头鹰邮递", "魔法部",
        ],
        script_outline="推理类（mystery），HP 风格学院悬疑；3 嫌疑人候选 + 海格清白线索",
    ),
    WorldPack(
        slug="changan-12-shichen",
        kind="ip",
        ip_name="长安十二时辰",
        description=(
            "原作设定『长安十二时辰』。"
            "时间往后推一个月，上元节阙楼疑案后，靖安司收到密报："
            "平康坊某位歌姬连续三晚醒来都看见有人在窗口看她，第四晚她失踪了。"
            "李必将这件看似小事交给重新启用的张小敬独自处理，"
            "玩家扮演张小敬或其副手檀棋，需要在 12 时辰内找出真相。"
            "保留原作的望楼传讯、坊市制度、不良人体系。"
        ),
        genre="古装悬疑 / 历史",
        era="大唐天宝三载",
        fidelity="strict",
        canonical_elements=[
            "长安", "靖安司", "张小敬", "李必", "檀棋",
            "望楼", "不良人", "平康坊", "西市", "东市",
            "圣人", "右骁卫", "鱼肠", "陇右节度使",
        ],
        script_outline="推理类（mystery），张小敬独自查案，12 时辰倒计时；3 个嫌疑人都跟坊市相关",
    ),
]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


async def login(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{BACKEND_URL}/api/dev/login")
    r.raise_for_status()
    j = r.json()
    assert j.get("code") == 0, f"dev_login failed: {j}"


async def consume_sse(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    label: str = "sse",
    on_event: callable | None = None,
    idle_timeout_s: float = SSE_IDLE_TIMEOUT_S,
) -> list[dict]:
    """Drain an SSE stream. Returns list of parsed event dicts.

    `on_event(evt)` is called for every parsed event; useful for early-exit
    callers (e.g. capture narrative without buffering everything).
    """
    events: list[dict] = []
    last_event_at = time.time()
    headers = {"Accept": "text/event-stream"}

    async with client.stream(method, url, json=json_body, headers=headers, timeout=HTTP_TIMEOUT) as r:
        if r.status_code != 200:
            text = (await r.aread()).decode("utf-8", errors="ignore")
            raise RuntimeError(f"{label} HTTP {r.status_code}: {text[:500]}")
        buffer = ""
        async for chunk in r.aiter_text():
            if not chunk:
                if time.time() - last_event_at > idle_timeout_s:
                    raise RuntimeError(f"{label}: SSE idle > {idle_timeout_s}s")
                continue
            last_event_at = time.time()
            # sse-starlette emits CRLF; normalize so a single split works.
            buffer += chunk.replace("\r\n", "\n")
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                data_lines = [
                    line[5:].lstrip()
                    for line in raw.splitlines()
                    if line.startswith("data:")
                ]
                if not data_lines:
                    continue
                payload = "\n".join(data_lines)
                if payload in ("[DONE]", "ping"):
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                events.append(evt)
                if on_event is not None:
                    if on_event(evt) is False:
                        return events
    return events


# ---------------------------------------------------------------------------
# Workshop flow
# ---------------------------------------------------------------------------


async def wait_task_finished(
    client: httpx.AsyncClient, task_id: str, *, label: str
) -> dict:
    """Poll task status via SSE stream until terminal state. Returns last task row."""
    url = f"{BACKEND_URL}/api/workshop/generation-tasks/{task_id}/stream"
    terminal_event: dict | None = None

    def on_evt(evt: dict) -> bool:
        nonlocal terminal_event
        et = evt.get("type") or evt.get("event")
        # Stream emits status snapshots; once status reaches succeeded/failed/cancelled,
        # short-circuit.
        if et in ("task_status", "status", "snapshot"):
            status = (evt.get("data") or evt).get("status")
            if status in ("succeeded", "failed", "cancelled"):
                terminal_event = evt
                return False
        # Some backends emit a final "done" event without status.
        if et == "done":
            terminal_event = evt
            return False
        return True

    started = time.time()
    while time.time() - started < WORLD_TASK_TIMEOUT_S:
        try:
            await consume_sse(client, "GET", url, label=f"{label}.stream", on_event=on_evt)
        except Exception as exc:
            print(f"  ! {label}: SSE error: {exc} — re-querying status …")
        # Re-fetch status definitively
        r = await client.get(f"{BACKEND_URL}/api/workshop/generation-tasks/{task_id}")
        if r.status_code == 200:
            row = (r.json() or {}).get("data") or {}
            status = row.get("status")
            if status in ("succeeded", "failed", "cancelled"):
                return row
        await asyncio.sleep(2)
    raise TimeoutError(f"{label}: task {task_id} did not finish within {WORLD_TASK_TIMEOUT_S}s")


async def generate_world(
    client: httpx.AsyncClient, pack: WorldPack
) -> tuple[str, str]:
    """Run phase A + phase B; publish; return (world_id, draft_id)."""
    print(f"[{pack.slug}] phase A: kickoff …")
    r = await client.post(
        f"{BACKEND_URL}/api/workshop/world-generation-tasks",
        json={"description": pack.description, "genre": pack.genre, "era": pack.era},
    )
    if r.status_code >= 400:
        raise RuntimeError(f"phase A kickoff failed: {r.status_code} {r.text[:300]}")
    j = r.json()["data"]
    draft_id = j["draft_id"]
    task_a = j["task_id"]
    print(f"  draft_id={draft_id} task_a={task_a}")

    row = await wait_task_finished(client, task_a, label=f"{pack.slug}.phaseA")
    if row.get("status") != "succeeded":
        raise RuntimeError(f"phase A failed: status={row.get('status')} err={row.get('error_message')!r}")
    print(f"  phase A done.")

    print(f"[{pack.slug}] phase B: continue with fidelity={pack.fidelity} …")
    r = await client.post(
        f"{BACKEND_URL}/api/workshop/world-drafts/{draft_id}/continue-generation",
        json={"fidelity_mode": pack.fidelity},
    )
    if r.status_code >= 400:
        raise RuntimeError(f"phase B kickoff failed: {r.status_code} {r.text[:300]}")
    task_b = r.json()["data"]["task_id"]
    row = await wait_task_finished(client, task_b, label=f"{pack.slug}.phaseB")
    if row.get("status") != "succeeded":
        raise RuntimeError(f"phase B failed: status={row.get('status')} err={row.get('error_message')!r}")
    print(f"  phase B done.")

    print(f"[{pack.slug}] publish world …")
    r = await client.post(f"{BACKEND_URL}/api/workshop/world-drafts/{draft_id}/publish")
    if r.status_code >= 400:
        raise RuntimeError(f"publish world failed: {r.status_code} {r.text[:300]}")
    world_id = (r.json().get("data") or {}).get("world_id") or (r.json().get("data") or {}).get("id")
    if not world_id:
        raise RuntimeError(f"publish world: no world_id in response {r.text[:300]}")
    print(f"  world_id={world_id}")
    return world_id, draft_id


async def generate_and_publish_script(
    client: httpx.AsyncClient, pack: WorldPack, world_id: str
) -> str:
    print(f"[{pack.slug}] script: kickoff …")
    r = await client.post(
        f"{BACKEND_URL}/api/workshop/script-generation-tasks",
        json={"world_id": world_id, "outline": pack.script_outline},
    )
    if r.status_code >= 400:
        raise RuntimeError(f"script kickoff failed: {r.status_code} {r.text[:300]}")
    data = r.json()["data"]
    draft_id = data.get("draft_id") or data.get("script_draft_id")
    task_id = data["task_id"]
    print(f"  script_draft_id={draft_id} task={task_id}")

    row = await wait_task_finished(client, task_id, label=f"{pack.slug}.script")
    if row.get("status") != "succeeded":
        raise RuntimeError(f"script failed: status={row.get('status')} err={row.get('error_message')!r}")

    r = await client.post(f"{BACKEND_URL}/api/workshop/script-drafts/{draft_id}/publish")
    if r.status_code >= 400:
        raise RuntimeError(f"publish script failed: {r.status_code} {r.text[:300]}")
    body = r.json().get("data") or {}
    script_id = body.get("script_id") or body.get("id")
    if not script_id:
        raise RuntimeError(f"publish script: no script_id in {body!r}")
    print(f"  script_id={script_id}")
    return script_id


async def pick_character(client: httpx.AsyncClient, world_id: str) -> str:
    r = await client.get(f"{BACKEND_URL}/api/worlds/{world_id}")
    r.raise_for_status()
    chars = ((r.json().get("data") or {}).get("characters") or [])
    if not chars:
        raise RuntimeError("world has no characters")
    # Prefer the first listed character (workshop tends to order by importance).
    return chars[0].get("id")


# ---------------------------------------------------------------------------
# Game play loop
# ---------------------------------------------------------------------------


async def xiaomi_chat(
    client: httpx.AsyncClient,
    messages: list[dict],
    *,
    max_tokens: int = 800,
    purpose: str = "player",
) -> str:
    if not XIAOMI_KEY:
        raise RuntimeError("XIAOMI_API_KEY not set")
    r = await client.post(
        f"{XIAOMI_BASE}/chat/completions",
        json={"model": XIAOMI_MODEL, "messages": messages, "max_tokens": max_tokens},
        headers={"Authorization": f"Bearer {XIAOMI_KEY}"},
        timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
    )
    if r.status_code >= 400:
        raise RuntimeError(f"xiaomi[{purpose}] HTTP {r.status_code}: {r.text[:300]}")
    j = r.json()
    return (j["choices"][0]["message"].get("content") or "").strip()


PLAYER_SYS_PROMPT = (
    "你是一个在玩沉浸式 AI 文字游戏的玩家。"
    "你要扮演的角色与游戏背景见对话开头给出的「设定」段。"
    "你的目标：像真实玩家一样推进剧情——好奇、追问、做选择、偶尔尝试有创意的行动。"
    "每轮我会给你刚刚发生的叙事（最近几段）和你之前的几条输入；"
    "你只需要输出**这一回合你要做或说什么**，一段话，30-100 字之间。"
    "不要扮演 NPC，不要写第三人称叙事，不要解释你的策略。直接以第一人称给行动/对话。"
)


async def simulate_player_input(
    client: httpx.AsyncClient,
    role_setup: str,
    recent_narrative: list[str],
    recent_inputs: list[str],
    round_number: int,
) -> str:
    """Ask Xiaomi to produce the next player utterance."""
    history = "\n".join(f"叙事 R{round_number-len(recent_narrative)+i+1}: {t}" for i, t in enumerate(recent_narrative[-4:]))
    prior_inputs = "\n".join(f"- {x}" for x in recent_inputs[-3:]) or "（开局）"
    user_msg = (
        f"【设定】\n{role_setup}\n\n"
        f"【最近叙事】\n{history or '（开局，刚进入故事）'}\n\n"
        f"【你最近三轮输入】\n{prior_inputs}\n\n"
        f"现在是第 {round_number} 回合，给出你的下一步行动/对话（30-100 字，纯第一人称）。"
    )
    out = await xiaomi_chat(
        client,
        messages=[{"role": "system", "content": PLAYER_SYS_PROMPT}, {"role": "user", "content": user_msg}],
        max_tokens=1200,
        purpose="player",
    )
    # Strip surrounding quotes if any.
    out = out.strip().strip("「」\"'`").strip()
    if not out:
        out = "我环顾四周，再仔细听听有没有什么动静。"
    if len(out) > 500:
        out = out[:500]
    return out


async def play_turn(
    client: httpx.AsyncClient,
    session_id: str,
    action_text: str,
    log: list[dict],
) -> dict:
    """Send one player action; drain SSE; return summary dict."""
    narrative_parts: list[str] = []
    errors: list[dict] = []
    ending_payload: dict | None = None
    # Client-side latency: t_start → first narrative token (TTFT) and → done.
    t_start = time.time()
    ttft: float | None = None

    def on_evt(evt: dict) -> None:
        nonlocal ttft
        et = evt.get("type")
        if et in ("text_delta", "narrative_chunk", "narrative"):
            if ttft is None:
                ttft = time.time() - t_start
            narrative_parts.append(evt.get("text") or evt.get("content") or "")
        elif et == "error":
            errors.append({"code": evt.get("code"), "message": evt.get("message")})
        elif et == "ending":
            nonlocal_capture(evt)
        # silent for others

    def nonlocal_capture(evt: dict) -> None:
        nonlocal ending_payload
        ending_payload = evt

    raw_events = await consume_sse(
        client,
        "POST",
        f"{BACKEND_URL}/api/game/{session_id}/action",
        json_body={"action_text": action_text},
        label=f"play.{session_id[:8]}",
        on_event=lambda e: (on_evt(e), True)[1],
    )
    done_s = time.time() - t_start
    with (RESEARCH_DIR / f"{session_id}-latency.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ttft_s": ttft, "done_s": done_s}, ensure_ascii=False) + "\n")

    summary = {
        "action": action_text,
        "ttft_s": ttft,
        "done_s": done_s,
        "narrative": "".join(narrative_parts).strip(),
        "errors": errors,
        "ending": ending_payload,
        "event_count": len(raw_events),
    }
    log.append(summary)
    return summary


async def playthrough(
    client: httpx.AsyncClient,
    pack: WorldPack,
    world_id: str,
    character_id: str,
    script_id: str | None,
    rounds: int,
) -> dict:
    print(f"[{pack.slug}] start game session …")
    # /api/game/start is an SSE stream too (it streams the opening narrative).
    session_id: str | None = None

    def on_evt(evt: dict) -> None:
        nonlocal session_id
        sid = evt.get("session_id") or (evt.get("data") or {}).get("session_id")
        if sid and not session_id:
            session_id = sid

    start_body: dict = {
        "world_id": world_id,
        "character_id": character_id,
        "mode": pack.mode,
    }
    if pack.mode == "script" and script_id:
        start_body["script_id"] = script_id
    await consume_sse(
        client, "POST",
        f"{BACKEND_URL}/api/game/start",
        json_body=start_body,
        label=f"{pack.slug}.start",
        on_event=lambda e: (on_evt(e), True)[1],
    )
    if not session_id:
        # Fallback: list user's sessions and grab newest.
        r = await client.get(f"{BACKEND_URL}/api/game/sessions") if False else None
        raise RuntimeError("could not extract session_id from /game/start SSE")
    print(f"  session_id={session_id}")

    role_setup = f"世界：{pack.description}\n剧本提示：{pack.script_outline}"
    log: list[dict] = []
    bug_path = RESEARCH_DIR / f"{session_id}-bugs.jsonl"

    for r_no in range(1, rounds + 1):
        # Build recent narrative + recent inputs for the simulated player.
        recent_narrative = [t["narrative"] for t in log[-4:] if t.get("narrative")]
        recent_inputs = [t["action"] for t in log[-3:]]
        try:
            action = await simulate_player_input(
                client, role_setup, recent_narrative, recent_inputs, r_no
            )
        except Exception as exc:
            print(f"  ! R{r_no} player gen failed: {exc}")
            action = "我看看周围有没有什么细节，仔细听。"
        print(f"  R{r_no} player: {action[:80]}{'…' if len(action) > 80 else ''}")

        try:
            t0 = time.time()
            res = await play_turn(client, session_id, action, log)
            dt = time.time() - t0
            print(f"  R{r_no} done in {dt:.1f}s, errs={len(res['errors'])}, ending={'Y' if res['ending'] else '-'}")
            for err in res["errors"]:
                with bug_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "session_id": session_id, "round": r_no, "kind": "sse_error",
                        "action": action, "error": err,
                    }, ensure_ascii=False) + "\n")
            if res["ending"]:
                print(f"  >> session ended at R{r_no}")
                break
        except Exception as exc:
            print(f"  ! R{r_no} action failed: {exc}\n{traceback.format_exc(limit=2)}")
            with bug_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "session_id": session_id, "round": r_no, "kind": "exception",
                    "action": action, "error": str(exc),
                }, ensure_ascii=False) + "\n")
            # Keep going — one broken turn shouldn't kill the run.
            await asyncio.sleep(2)

    print(f"[{pack.slug}] playthrough finished, {len(log)} turns logged.")
    return {"session_id": session_id, "log": log, "bug_path": str(bug_path)}


# ---------------------------------------------------------------------------
# Synthesis (Phase C)
# ---------------------------------------------------------------------------


SYNTHESIS_SYS = (
    "你是一个资深游戏设计师，正在复盘一局玩家通关数据。"
    "目标 1：用一段 200 字总结整局推进、关键转折、玩家最常做的事。"
    "目标 2：列出整局里玩家最常想知道的 3-5 类信息（最好按出现频次排）。"
    "目标 3：列出当前案件板字段中【实际有用】和【没必要】的字段（结合每回合 research_note）。"
    "目标 4：如果重新设计案件板，你会保留哪些字段、新增哪些字段？给出具体字段名 + 类型。"
    "目标 5：如果是 IP 世界，评估还原度（0-100）+ 漂移点 + 优化建议。"
    "输出用 markdown，不要寒暄。"
)


async def synthesize_summary(
    client: httpx.AsyncClient,
    pack: WorldPack,
    session_id: str,
    log: list[dict],
) -> Path | None:
    """Pull the research jsonl + final state + transcript; ask Xiaomi for a report."""
    jsonl_path = RESEARCH_DIR / f"{session_id}.jsonl"
    notes_text = jsonl_path.read_text(encoding="utf-8") if jsonl_path.exists() else "（空）"

    # Truncate transcript: keep first 5 + last 10 turns; that's usually enough.
    short_log = log[:5] + (log[5:-10] and ["...(中段省略)..."] or []) + log[-10:]
    transcript_lines = []
    for i, t in enumerate(short_log, 1):
        if isinstance(t, str):
            transcript_lines.append(t)
            continue
        transcript_lines.append(f"R{i} 玩家: {t.get('action', '')[:200]}")
        narr = (t.get("narrative") or "")[:600]
        if narr:
            transcript_lines.append(f"     叙事: {narr}")

    # Try to fetch final state for context.
    state_text = ""
    try:
        r = await client.get(f"{BACKEND_URL}/api/game/{session_id}/state")
        if r.status_code == 200:
            state_text = json.dumps(r.json().get("data") or {}, ensure_ascii=False, indent=2)[:2000]
    except Exception:
        pass

    cb_text = ""
    try:
        r = await client.get(f"{BACKEND_URL}/api/game/{session_id}/case-board")
        if r.status_code == 200:
            cb_text = json.dumps(r.json().get("data") or {}, ensure_ascii=False, indent=2)[:3000]
    except Exception:
        pass

    pack_info = (
        f"slug: {pack.slug}\n"
        f"kind: {pack.kind} ({'IP=' + pack.ip_name if pack.ip_name else '原创'})\n"
        f"description: {pack.description}\n"
        f"script_outline: {pack.script_outline}\n"
        f"canonical_elements (IP only): {pack.canonical_elements}\n"
    )

    user_msg = (
        f"# 世界包\n{pack_info}\n\n"
        f"# Director per-turn research notes (JSONL)\n```\n{notes_text[:8000]}\n```\n\n"
        f"# Transcript（节选）\n" + "\n".join(transcript_lines)[:8000] + "\n\n"
        f"# 最终 game state\n```\n{state_text}\n```\n\n"
        f"# 最终 case_board\n```\n{cb_text}\n```\n"
    )

    print(f"[{pack.slug}] synthesizing summary via xiaomi ({len(user_msg)} chars in)…")
    try:
        md = await xiaomi_chat(
            client,
            messages=[{"role": "system", "content": SYNTHESIS_SYS}, {"role": "user", "content": user_msg}],
            max_tokens=4000,
            purpose="synthesis",
        )
    except Exception as exc:
        print(f"  ! synthesis failed: {exc}")
        return None

    out_path = RESEARCH_DIR / f"{session_id}-summary.md"
    out_path.write_text(f"# {pack.slug} ({pack.kind}) — synthesis\n\n{md}\n", encoding="utf-8")
    print(f"  -> {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_one(client: httpx.AsyncClient, pack: WorldPack, rounds: int) -> dict:
    out = {"slug": pack.slug, "ok": False, "stage": "init", "session_id": None, "error": None}
    try:
        if pack.reuse_world_id:
            out["stage"] = "world_reuse"
            world_id = pack.reuse_world_id
            print(f"[{pack.slug}] reusing world {world_id} (skipping generation)")
        else:
            out["stage"] = "world"
            world_id, _draft = await generate_world(client, pack)
        out["world_id"] = world_id

        script_id: str | None = None
        if pack.mode == "script":
            if pack.reuse_world_id:
                if not pack.reuse_script_id:
                    raise RuntimeError("script-mode reuse needs reuse_script_id")
                script_id = pack.reuse_script_id
                print(f"[{pack.slug}] reusing script {script_id} (skipping generation)")
            else:
                out["stage"] = "script"
                script_id = await generate_and_publish_script(client, pack, world_id)
            out["script_id"] = script_id

        out["stage"] = "character"
        character_id = await pick_character(client, world_id)

        out["stage"] = "play"
        play = await playthrough(client, pack, world_id, character_id, script_id, rounds)
        out["session_id"] = play["session_id"]
        out["bugs"] = play["bug_path"]

        out["stage"] = "synthesis"
        summary_path = await synthesize_summary(client, pack, play["session_id"], play["log"])
        out["summary"] = str(summary_path) if summary_path else None
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{exc}\n{traceback.format_exc(limit=4)}"
        print(f"!! {pack.slug} aborted at stage={out['stage']}: {exc}")
    return out


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=25, help="rounds per playthrough")
    parser.add_argument(
        "--only", type=str, default="",
        help="comma-separated slugs to run; default = all four",
    )
    args = parser.parse_args()

    picked = WORLD_PACKS
    if args.only:
        wanted = set(s.strip() for s in args.only.split(",") if s.strip())
        picked = [p for p in WORLD_PACKS if p.slug in wanted]
        if not picked:
            print(f"no matching slugs in {args.only}; available: {[p.slug for p in WORLD_PACKS]}")
            return 2

    results: list[dict] = []
    # trust_env=False so we bypass the macOS system proxy (e.g. Clash on 127.0.0.1:7890)
    # which doesn't honor the system "localhost exception" list when httpx reads it.
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, trust_env=False) as client:
        await login(client)
        for pack in picked:
            print(f"\n========== {pack.slug} ({pack.kind}) ==========")
            res = await run_one(client, pack, args.rounds)
            results.append(res)
            run_log = RESEARCH_DIR / "run-index.jsonl"
            with run_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({**res, "ts": time.time()}, ensure_ascii=False) + "\n")

    print("\n========== DONE ==========")
    for r in results:
        print(f"  {r['slug']:30s} ok={r['ok']} stage={r['stage']} session={r.get('session_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
