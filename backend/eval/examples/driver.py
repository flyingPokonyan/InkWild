"""跑一局新播放（任意世界/剧本/persona）→ 返回 session_id。

LLM 玩家用 Xiaomi mimo（.env 已配，与 auto_play 同源）。失败回退默认动作。
hermes 想自己跑也行——这只是个方便的内置 driver，评测引擎不依赖它。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time

import httpx

_DISCONNECT_ERRORS = (
    httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError,
    httpx.ReadTimeout, httpx.WriteError, httpx.PoolTimeout,
)

BACKEND = os.environ.get("AUTOPLAY_BACKEND_URL", "http://localhost:8000")
XIAOMI_BASE = os.environ.get("XIAOMI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
XIAOMI_KEY = os.environ.get("XIAOMI_API_KEY", "")
XIAOMI_MODEL = os.environ.get("XIAOMI_MODEL", "mimo-v2.5")
HTTP_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)


async def _drain_sse(client, method, url, body, on_text=None) -> dict:
    cap: dict = {"session_id": None, "text": "", "ttft": None, "errors": 0}
    t0 = time.time()
    async with client.stream(method, url, json=body, headers={"Accept": "text/event-stream"}, timeout=HTTP_TIMEOUT) as r:
        if r.status_code != 200:
            cap["errors"] += 1
            return cap
        buf = ""
        async for chunk in r.aiter_text():
            if not chunk:
                continue
            buf += chunk.replace("\r\n", "\n")
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                dl = [l[5:].lstrip() for l in raw.splitlines() if l.startswith("data:")]
                if not dl:
                    continue
                payload = "\n".join(dl)
                if payload in ("[DONE]", "ping"):
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                sid = evt.get("session_id") or (evt.get("data") or {}).get("session_id")
                if sid and not cap["session_id"]:
                    cap["session_id"] = sid
                et = evt.get("type")
                if et in ("text_delta", "narrative_chunk", "narrative", "prelude"):
                    txt = evt.get("text") or evt.get("content") or ""
                    if txt:
                        if cap["ttft"] is None:
                            cap["ttft"] = round(time.time() - t0, 2)
                        cap["text"] += txt
                elif et == "error":
                    cap["errors"] += 1
    return cap


async def _player(client, persona: str, recent: list[str], turn: int) -> tuple[str, bool]:
    """返回 (玩家输入, ok)。ok=False 表示 mimo 多次失败、用了 canned 回退（弱观察会触发引擎弱输入
    clamp，污染评测，所以要统计）。mimo 在并发下会限流，故退避重试 3 次再回退。"""
    history = "\n".join(f"- {t}" for t in recent[-3:]) or "（开局，刚进入故事）"
    user = f"【最近叙事】\n{history}\n\n现在是第 {turn} 回合，给出你的下一步行动/对话（30-100字，纯第一人称，不要旁白）。"
    for attempt in range(3):
        try:
            r = await client.post(
                f"{XIAOMI_BASE}/chat/completions",
                json={"model": XIAOMI_MODEL, "messages": [{"role": "system", "content": persona},
                                                          {"role": "user", "content": user}], "max_tokens": 800},
                headers={"Authorization": f"Bearer {XIAOMI_KEY}"},
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
            )
            if r.status_code != 200:
                raise RuntimeError(f"mimo HTTP {r.status_code}")
            out = (r.json()["choices"][0]["message"].get("content") or "").strip().strip("「」\"'`").strip()
            if out:
                return out[:500], True
        except Exception:
            pass
        await asyncio.sleep(1.5 * (2 ** attempt) + random.random())
    return "我环顾四周，仔细观察。", False


async def _drain_safe(client, method, url, body, *, retries: int = 0) -> dict:
    """_drain_sse + 对网关断连（RemoteProtocolError 等）退避重试。
    retries=0 → 不重试（适合 action：重试有重复施加同一动作的风险，宁可记错跳过）。
    retries>0 → 重试（适合开场：失败就重开一局，拿不到 sid 没法继续）。"""
    last = {"session_id": None, "text": "", "ttft": None, "errors": 1}
    for attempt in range(retries + 1):
        try:
            cap = await _drain_sse(client, method, url, body)
            if cap.get("text") or cap.get("session_id") or attempt == retries:
                return cap
            last = cap
        except _DISCONNECT_ERRORS:
            last = {"session_id": None, "text": "", "ttft": None, "errors": 1, "disconnected": True}
        if attempt < retries:
            await asyncio.sleep(3.0 * (2 ** attempt) + random.random())
    return last


async def run_playthrough(*, world_id: str, mode: str, script_id: str | None, character_id: str,
                          persona: str, turns: int) -> dict:
    """返回 {session_id, opening_ttft, turn_ttfts, errors, disconnects}。

    韧性：开场断连重试至多 3 次；回合断连不重试（避免重复施加动作），记一次 error 并继续，
    单回合掉线不再杀整局。"""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as c:
        await c.post(f"{BACKEND}/api/dev/login")
        start = {"world_id": world_id, "character_id": character_id, "mode": mode}
        if mode == "script" and script_id:
            start["script_id"] = script_id
        op = await _drain_safe(c, "POST", f"{BACKEND}/api/game/start", start, retries=3)
        sid = op["session_id"]
        if not sid:
            return {"session_id": None, "errors": op.get("errors", 1) + 1, "disconnects": 1}
        recent = [op["text"]] if op["text"] else []
        ttfts: list[float] = []
        errs = op.get("errors", 0)
        disconnects = 0
        player_fallbacks = 0
        for i in range(1, turns + 1):
            action, ok = await _player(c, persona, recent, i)
            if not ok:
                player_fallbacks += 1
            cap = await _drain_safe(c, "POST", f"{BACKEND}/api/game/{sid}/action",
                                    {"action_text": action}, retries=0)
            errs += cap.get("errors", 0)
            if cap.get("disconnected"):
                disconnects += 1
            if cap.get("ttft") is not None:
                ttfts.append(cap["ttft"])
            if cap.get("text"):
                recent.append(cap["text"])
        return {"session_id": sid, "opening_ttft": op.get("ttft"), "turn_ttfts": ttfts,
                "errors": errs, "disconnects": disconnects, "player_fallbacks": player_fallbacks}
