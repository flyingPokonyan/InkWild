"""Grok web_search → list[Passage] + candidate character names.

Grok 一次 web_search 返回的 text 通常已是结构化中文清单（演员表 + 角色定位 + 剧情），
作为高质量上下文喂给下游 LLM 抽取，并解析出候选角色名供百度补抓使用。
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()


def _build_query(ip_name: str, ip_type: str, focus: str = "") -> str:
    base = f"《{ip_name}》"
    if ip_type in ("tv", "movie"):
        q = f"电视剧/电影{base} 主要角色 演员表 角色介绍 人物关系 剧情"
    elif ip_type == "novel":
        q = f"小说{base} 主要人物 角色介绍 人物关系 剧情简介"
    elif ip_type == "anime":
        q = f"动漫{base} 主要角色 声优 人物关系 剧情"
    elif ip_type == "game":
        q = f"游戏{base} 主要角色 剧情 角色介绍"
    else:
        q = f"{base} 主要角色 介绍 关系"
    # 多角度 fan-out：focus 把一条大杂烩 query 收窄到某一片（核心/对立/外围/设定），
    # 多条并发的并集比单条更宽，专门解决"单 query 只捞到最有名几个"。
    return f"{q} {focus}".strip() if focus else q


def _extract_candidate_names(grok_text: str) -> list[str]:
    """从 Grok summary 文本里抽出候选角色名（用于下游百度补抓）。

    简单 heuristic：匹配「饰 X」「饰演 X」，中文人名 2-12 字符。
    """
    names: list[str] = []
    for m in re.finditer(r"饰演?\s*\*?\*?\s*([一-鿿·]{2,12})", grok_text):
        names.append(m.group(1).strip("·"))
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique[:20]


async def fetch_via_grok_search(
    ip_name: str,
    ip_type: str,
    grok_provider: Any | None,
    *,
    max_chars: int = 4000,
    focus: str = "",
) -> tuple[list[Passage], list[str]]:
    """跑一次 Grok web_search，返回 (passages, candidate_names)。

    ``focus`` 为多角度 fan-out 的某一轴（核心人物 / 对立方 / 外围 NPC / 设定）。
    grok_provider 为 None / web_search 失败 → 返回 ([], [])。
    """
    if grok_provider is None or not ip_name:
        return [], []
    query = _build_query(ip_name, ip_type, focus)
    try:
        result = await grok_provider.web_search(query, max_tokens=2048)
    except Exception as exc:  # noqa: BLE001
        logger.warning("grok_search_failed", ip_name=ip_name, error=str(exc))
        return [], []

    text = (getattr(result, "text", "") or "").strip()
    if not text:
        return [], []

    citations = list(getattr(result, "citations", None) or [])
    tags = [f"query:{query}"] + [
        f"citation:{c.get('url', '')}" for c in citations if isinstance(c, dict)
    ]

    passages = [Passage(
        id=f"p_grok_{uuid.uuid4().hex[:8]}",
        text=text[:max_chars],
        tags=tags,
        source="grok_search",
    )]
    candidates = _extract_candidate_names(text)
    logger.info(
        "grok_search_ok",
        ip_name=ip_name,
        text_len=len(text),
        citations=len(citations),
        candidates=len(candidates),
    )
    return passages, candidates
