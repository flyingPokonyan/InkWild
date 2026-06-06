from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

from schemas.research_pack import Passage

if TYPE_CHECKING:
    from services.tavily_search import TavilySearch

logger = structlog.get_logger()

# ip_type → 推荐站点列表
SITE_MAP: dict[str, list[str]] = {
    "tv": ["baike.baidu.com", "douban.com"],
    "movie": ["baike.baidu.com", "douban.com"],
    "novel": ["baike.baidu.com", "jjwxc.net", "qidian.com"],
    "anime": ["baike.baidu.com", "moegirl.icu"],
    "game": ["baike.baidu.com", "gamersky.com"],
    "other": ["baike.baidu.com"],
}


async def fetch_via_tavily_site(
    ip_name: str,
    ip_type: str,
    tavily: "TavilySearch | None",
    *,
    max_per_site: int = 3,
    max_chars: int = 2000,
) -> list[Passage]:
    """对每个推荐站点用 include_domains 限定的 Tavily 搜索，合并结果为 Passage list。"""
    if not ip_name or tavily is None:
        return []
    sites = SITE_MAP.get(ip_type, SITE_MAP["other"])
    passages: list[Passage] = []
    for site in sites:
        try:
            results = await tavily.search(
                query=ip_name,
                max_results=max_per_site,
                include_domains=[site],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily_site_failed", site=site, ip_name=ip_name, error=str(exc))
            continue
        for r in results:
            text = (r.get("content") or r.get("snippet") or "").strip()
            if not text:
                continue
            passages.append(Passage(
                id=f"p_site_{uuid.uuid4().hex[:8]}",
                text=text[:max_chars],
                tags=[f"source:{r.get('url', '')}", f"site:{site}", f"query:{ip_name}"],
                source="tavily_site",
            ))
    return passages
