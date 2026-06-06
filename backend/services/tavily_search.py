"""Tavily Search API wrapper — async httpx, no SDK dependency."""

from __future__ import annotations

import httpx
import structlog

from config import settings

logger = structlog.get_logger()

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 10.0
MAX_CONTENT_LENGTH = 300


class TavilySearch:
    """Lightweight async wrapper around Tavily Search REST API."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        # Tavily 已停用（Grok web_search 覆盖联网检索，2026-05-31）。强制空 key →
        # search() 始终走 graceful skip 分支返回 []，不再发任何 HTTP / 产生 400。
        # 如需彻底移除可后续清理 10 处引用；此处停用即足以让 Tavily 退出流程。
        self.api_key = ""
        self.timeout = timeout

    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        include_domains: list[str] | None = None,
    ) -> list[dict]:
        """Search Tavily and return structured results.

        Args:
            query: search query
            max_results: max results to return
            include_domains: if provided, restrict search to these domains (Tavily API
                include_domains parameter). Note this is the correct way to do per-site
                search — query-string operators like `site:foo.com` are NOT honored.

        Returns:
            List of dicts with keys: title, url, content (truncated to ~300 chars).
            Returns empty list on failure (graceful degradation).
        """
        if not self.api_key:
            logger.warning("tavily_search_skipped", reason="no api key configured")
            return []

        payload: dict = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        if include_domains:
            payload["include_domains"] = include_domains

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(TAVILY_SEARCH_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("tavily_search_timeout", query=query)
            return []
        except Exception:
            logger.warning("tavily_search_error", query=query, exc_info=True)
            return []

        results: list[dict] = []
        for item in data.get("results", []):
            content = (item.get("content") or "")[:MAX_CONTENT_LENGTH]
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": content,
            })
        return results
