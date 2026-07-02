#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class TestCase:
    name: str
    payload: dict[str, Any]


def post_json(url: str, key: str, payload: dict[str, Any], timeout: float) -> tuple[int, float, dict[str, Any]]:
    started = time.perf_counter()
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:1000]}
        return resp.status_code, elapsed, data
    except Exception as exc:
        return 0, time.perf_counter() - started, {"error": {"message": str(exc)}}


def list_grok_models(base_url: str, key: str) -> list[str]:
    resp = requests.get(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return sorted(
        item["id"]
        for item in data.get("data", [])
        if isinstance(item, dict) and str(item.get("id", "")).startswith("grok")
    )


def usage_summary(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt": usage.get("prompt_tokens"),
        "completion": usage.get("completion_tokens"),
        "total": usage.get("total_tokens"),
        "cached": prompt_details.get("cached_tokens"),
        "reasoning": completion_details.get("reasoning_tokens"),
    }


def summarize_response(status: int, elapsed: float, data: dict[str, Any]) -> dict[str, Any]:
    err = data.get("error")
    if err:
        return {
            "ok": False,
            "status": status,
            "sec": round(elapsed, 2),
            "error": (err.get("message") if isinstance(err, dict) else str(err))[:220],
        }

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = (msg.get("content") or "").strip()
    return {
        "ok": status == 200,
        "status": status,
        "sec": round(elapsed, 2),
        "finish": choice.get("finish_reason") or choice.get("native_finish_reason"),
        "content_preview": content[:240].replace("\n", " / "),
        "content_len": len(content),
        "reasoning_chars": len(msg.get("reasoning_content") or ""),
        "tool_calls": len(msg.get("tool_calls") or []),
        "usage": usage_summary(data),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("CPA_BASE_URL", "https://cpa.pokonyan.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("CPA_KEY"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Set CPA_KEY or pass --api-key")

    cases = [
        TestCase(
            "json",
            {
                "messages": [
                    {"role": "system", "content": "你是严格 JSON 输出助手。"},
                    {"role": "user", "content": '请只输出 JSON，不要 markdown：{"status":"ok","scene":"雨夜旧戏院"}'},
                ],
                "max_tokens": 120,
            },
        ),
        TestCase(
            "ip_recognition",
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "判断用户描述是否指向已知 IP。严格输出 JSON："
                            '{"kind":"known_ip|hybrid|original","confidence":0到1,"ip_name":null或作品名,'
                            '"ip_type":"tv|movie|novel|anime|game|other","one_liner":"30字内"}'
                        ),
                    },
                    {"role": "user", "content": "我想做一个十日终焉风格的多人密室生存世界，保留齐夏那种推理压迫感。"},
                ],
                "max_tokens": 300,
            },
        ),
        TestCase(
            "world_seed",
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是 InkWild 创作工坊的世界生成助手。输出中文，结构清晰，"
                            "包含世界钩子、3个地点、3个NPC、核心秘密。不要写代码。"
                        ),
                    },
                    {"role": "user", "content": "生成一个雨夜旧戏院里的民国悬疑互动世界种子，500字以内。"},
                ],
                "max_tokens": 900,
            },
        ),
        TestCase(
            "tool_use",
            {
                "messages": [{"role": "user", "content": "请调用 probe_echo，并把 text 设置为 probe-ok"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "probe_echo",
                            "description": "回显测试文本",
                            "parameters": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
                "max_tokens": 180,
            },
        ),
    ]

    models = list_grok_models(args.base_url, args.api_key)
    print(json.dumps({"base_url": args.base_url, "models": models}, ensure_ascii=False))
    for model in models:
        print(f"\n## {model}", flush=True)
        for case in cases:
            status, elapsed, data = post_json(
                f"{args.base_url.rstrip('/')}/chat/completions",
                args.api_key,
                {"model": model, **case.payload},
                args.timeout,
            )
            result = summarize_response(status, elapsed, data)
            print(json.dumps({"case": case.name, **result}, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
