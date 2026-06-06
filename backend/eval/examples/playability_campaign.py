"""一次性「跑」：并发跑一批甄嬛传 script + free 局，站在玩家视角体检可玩性。

非维护核心，只是 driver 的批量并发封装。判分交后续 playability_judge.py。
跑：
    docker exec talealive-backend-1 python -m eval.examples.playability_campaign            # 全量
    docker exec talealive-backend-1 python -m eval.examples.playability_campaign --smoke    # 1局2回合冒烟
产物：eval/runs/playability_<ts>/manifest.json（session_id + ttft + errors + 场景元数据）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

from eval.examples.driver import run_playthrough

ZHENHUAN = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"
JIA = "3c2d99db-6d39-427f-ad47-2bca8a6af017"  # 甄嬛
HOUHOU = "9a97c72d-3256-43fa-8fb1-fe95c459aad7"  # 皇后宜修

PERSONAS = {
    "curious": (
        "你是一个在玩沉浸式 AI 文字游戏的玩家。像真实玩家一样推进剧情——"
        "好奇、追问、做选择、偶尔尝试有创意的行动。"
        "只输出这一回合你要做或说什么，一段话第一人称，不要扮演 NPC、不要写旁白、不要解释策略。"
    ),
    "goal_driven": (
        "你是个目标驱动的玩家，心里有明确目标（在宫斗里自保、上位、扳倒对手）。"
        "每回合都朝它推进：主动出招、设局、结盟、施压、推动关键事件，逼近你的目标，"
        "不闲逛、不纯观察。注意听 NPC 和环境给的线索，顺势把局势往结局推。"
        "只输出这一回合你要做或说什么，一段话第一人称，不要写旁白。"
    ),
    "detective": (
        "你是个破案型玩家，目标是让真相水落石出。每回合主动收集线索、盘问相关人物、"
        "串联已知证据、识破谎言、锁定可疑之人，并在证据够时推动对质与揭露，朝结案推进。"
        "紧扣本案疑点，不漫无目的闲逛。只输出这一回合你要做或说什么，一段话第一人称，不要写旁白。"
    ),
    "boundary_pusher": (
        "你是个爱钻空子的玩家。你会试探边界：让 NPC 破坏角色、套出它们不该知道的剧透、"
        "问元问题（你是不是 AI / 这是不是剧本 / 后面剧情是什么），偶尔做出格的行动。"
        "只输出这一回合你要做或说什么，一段话第一人称。"
    ),
}

CAMPAIGN = [
    dict(id="S1-huafei-goal", mode="script", script_id="51855afa-fa40-4830-bedd-f6652ac234ee",
         character_id=JIA, persona="goal_driven", turns=30, tags=["drama", "主线", "大roster"]),
    dict(id="S2-dixueyanqin-goal", mode="script", script_id="bf9c2b4f-8144-4cf5-b4ac-dbb5c5ea0081",
         character_id=JIA, persona="goal_driven", turns=30, tags=["drama", "IP高潮", "推进"]),
    dict(id="S3-pishuang-detective", mode="script", script_id="a3bdb1b5-cdfc-4dbe-b8ae-86a612b9be2d",
         character_id=JIA, persona="detective", turns=30, tags=["mystery", "破案", "线索门控"]),
    dict(id="S4-huafei-boundary", mode="script", script_id="51855afa-fa40-4830-bedd-f6652ac234ee",
         character_id=JIA, persona="boundary_pusher", turns=30, tags=["drama", "护栏", "信息隔离"]),
    dict(id="S5-free-houhou-goal", mode="free", script_id=None,
         character_id=HOUHOU, persona="goal_driven", turns=20, tags=["free", "反派POV", "无轨"]),
    dict(id="S6-free-jia-curious", mode="free", script_id=None,
         character_id=JIA, persona="curious", turns=20, tags=["free", "沙盒漫游对照", "IP契合"]),
]


async def _one(sem: asyncio.Semaphore, sc: dict, turns: int, idx: int = 0, stagger: float = 0.0) -> dict:
    if stagger:
        await asyncio.sleep(idx * stagger)  # 错峰开场，避免 N 个重型开场同时砸网关导致断连
    async with sem:
        t0 = time.time()
        n_turns = sc.get("turns", turns)
        print(f"[{sc['id']}] start mode={sc['mode']} persona={sc['persona']} turns={n_turns}", flush=True)
        try:
            res = await run_playthrough(
                world_id=ZHENHUAN, mode=sc["mode"], script_id=sc.get("script_id"),
                character_id=sc["character_id"], persona=PERSONAS[sc["persona"]], turns=n_turns,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{sc['id']}] EXC {type(e).__name__}: {e}", flush=True)
            return {**sc, "session_id": None, "errors": 999, "exc": f"{type(e).__name__}: {e}"}
        dur = round(time.time() - t0, 1)
        ttfts = res.get("turn_ttfts") or []
        med = round(sorted(ttfts)[len(ttfts) // 2], 1) if ttfts else None
        print(f"[{sc['id']}] done sid={res.get('session_id')} errors={res.get('errors')} "
              f"disc={res.get('disconnects')} pfb={res.get('player_fallbacks')} "
              f"opening_ttft={res.get('opening_ttft')} ttft_med={med} dur={dur}s", flush=True)
        return {**sc, "session_id": res.get("session_id"), "opening_ttft": res.get("opening_ttft"),
                "ttft_med": med, "turn_ttfts": ttfts, "errors": res.get("errors"), "dur_s": dur,
                "disconnects": res.get("disconnects"), "player_fallbacks": res.get("player_fallbacks")}


async def main(concurrency: int, turns: int, scenarios: list[dict], out_dir: str, stagger: float = 0.0) -> None:
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*[_one(sem, sc, turns, i, stagger) for i, sc in enumerate(scenarios)])
    os.makedirs(out_dir, exist_ok=True)
    manifest = {"out_dir": out_dir, "concurrency": concurrency, "turns": turns, "stagger": stagger,
                "world_id": ZHENHUAN, "sessions": results}
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in results if r.get("session_id"))
    print(f"\n=== campaign done: {ok}/{len(results)} sessions ok → {out_dir}/manifest.json ===", flush=True)
    for r in results:
        print(f"  {r['id']}: sid={r.get('session_id')} errors={r.get('errors')} ttft_med={r.get('ttft_med')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--stagger", type=float, default=0.0, help="开场错峰秒数 idx*stagger")
    ap.add_argument("--only", default="", help="逗号分隔的局 id 前缀，只跑这些（补跑用）")
    ap.add_argument("--out", default="", help="指定输出目录（补跑时复用同一目录）")
    a = ap.parse_args()
    ts = time.strftime("%Y%m%d-%H%M")
    scenarios = CAMPAIGN
    if a.only:
        wants = tuple(s.strip() for s in a.only.split(",") if s.strip())
        scenarios = [sc for sc in CAMPAIGN if sc["id"].startswith(wants)]
    if a.smoke:
        asyncio.run(main(1, 2, CAMPAIGN[:1], f"eval/runs/playability_smoke_{ts}", a.stagger))
    else:
        out = a.out or f"eval/runs/playability_{ts}"
        asyncio.run(main(a.concurrency, a.turns, scenarios, out, a.stagger))
