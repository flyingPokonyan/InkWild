"""一次性「跑」示例：跨家族判官面板对 NPC voice A/B 做盲 pairwise。

为什么需要它：repo 内唯一配过的跨家族判官（xai/grok）网关上游 403，qwen 槽位 503，
导致 npc_pairwise 只剩同源 deepseek 判官（4/7 弱信号）。本脚本把判官指向一个**有货的
跨家族网关**（qwen / glm / kimi 三家族），复用 Scorer 的纯函数（build_pairs / _ask_pair /
parse_pairwise_verdict / aggregate_pairwise / render_pairwise），不碰生产 slot、不改 Scorer。

判官走 env，不写死密钥：
    XFAM_BASE   网关 base_url（含 /v1）
    XFAM_KEY    令牌
    XFAM_MODELS 逗号分隔模型 id（默认 qwen3.7-max,glm-5.1,kimi-k2.6）
    SID_NO_VOICE / SID_VOICE  两个对照 session
跑：
    docker exec -e XFAM_BASE=... -e XFAM_KEY=... talealive-backend-1 \
        python -m eval.examples.xfamily_pairwise
"""
from __future__ import annotations

import asyncio
import json
import os

from database import async_session
from eval.capture import capture_session
from eval.judge import load_rubric
from eval.judge_pairwise import (
    _ask_pair,
    aggregate_pairwise,
    build_pairs,
    parse_pairwise_verdict,
)
from eval.report import render_pairwise
from llm.openai_compatible import OpenAICompatibleProvider
from llm.router import LLMRouter

BASE = os.environ["XFAM_BASE"]
KEY = os.environ["XFAM_KEY"]
MODELS = os.environ.get(
    "XFAM_MODELS", "dashscope/qwen3.7-max,dashscope/glm-5.1,dashscope/kimi-k2.6"
).split(",")
SID_NO_VOICE = os.environ.get("SID_NO_VOICE", "f8a7e31a-7e65-4c8e-a70f-62e4c4096b56")
SID_VOICE = os.environ.get("SID_VOICE", "9810c6fb-3b56-4233-a047-7ec8821b9bbf")
SEED = int(os.environ.get("XFAM_SEED", "42"))
OUT = os.environ.get("XFAM_OUT", "eval/runs/npc_xfamily_pairwise")


def _router(model: str) -> LLMRouter:
    provider = OpenAICompatibleProvider(api_key=KEY, base_url=BASE, model=model)
    return LLMRouter(
        providers={model: provider},
        fallback_chain=[model],
        identity={"model_id": model},
        reasoning=False,
    )


async def main() -> None:
    async with async_session() as db:
        rubric = load_rubric("npc_pairwise")
        cap_a = await capture_session(db, SID_NO_VOICE)
        cap_b = await capture_session(db, SID_VOICE)

    pairs = build_pairs(cap_a, cap_b, "no_voice", "voice", seed=SEED)
    print(f"对齐到 {len(pairs)} 个共同回合：{[p['turn'] for p in pairs]}")

    judge_results: dict[str, list[dict]] = {}
    for model in MODELS:
        name = model.split("/")[-1]
        router = _router(model)
        results: list[dict] = []
        for p in pairs:
            text = await _ask_pair(router, rubric, p)
            results.append(parse_pairwise_verdict(text, p))
        errs = sum(1 for r in results if "error" in r)
        judge_results[name] = results
        print(f"  判官 {name}: {len(results)} 对，解析失败 {errs}")

    result = {
        "labels": ["no_voice", "voice"],
        "pairs": [
            {"turn": p["turn"], "A_label": p["A_label"], "B_label": p["B_label"]}
            for p in pairs
        ],
        "judge_results": judge_results,
        "aggregate": aggregate_pairwise(judge_results, ("no_voice", "voice")),
    }
    md = render_pairwise(result, "npc_pairwise", SEED)
    with open(f"{OUT}.md", "w") as f:
        f.write(md)
    with open(f"{OUT}.jsonl", "w") as f:
        f.write(json.dumps(result, ensure_ascii=False))
    print("\n" + md)


if __name__ == "__main__":
    asyncio.run(main())
