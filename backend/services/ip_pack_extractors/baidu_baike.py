"""百度百科直抓 → list[Passage]。

提供三个入口：
- fetch_baike_show: 抓剧/作品主页（演员表 + 角色介绍区段最丰富）
- fetch_baike_character: 抓单角色页（per-character 详细资料）
- fetch_baike_characters_batch: 批量抓多个角色页，并发受限 + 限速
"""
from __future__ import annotations

import asyncio
import re
import uuid
from urllib.parse import quote

import httpx
import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()

BAIKE_BASE = "https://baike.baidu.com/item/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0"


async def _fetch_html(url: str, timeout: float = 8.0) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get(url, follow_redirects=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("baike_fetch_failed", url=url, error=str(exc))
        return None


def _html_to_text(html: str, max_chars: int) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup_not_installed")
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = (
        soup.select_one("div.lemma-summary")
        or soup.select_one("div.J-lemma-content")
        or soup.body
    )
    text = main.get_text(separator="\n", strip=True) if main else ""
    return re.sub(r"\n{3,}", "\n\n", text)[:max_chars]


async def fetch_baike_show(
    ip_name: str,
    *,
    max_chars: int = 4000,
) -> list[Passage]:
    """抓 /item/<ip_name> 剧主页，切 2 段返回。"""
    if not ip_name:
        return []
    url = BAIKE_BASE + quote(ip_name)
    html = await _fetch_html(url)
    if not html:
        return []
    text = _html_to_text(html, max_chars * 2)
    if not text.strip():
        return []
    passages: list[Passage] = []
    chunk_size = max_chars
    for offset in range(0, min(len(text), chunk_size * 2), chunk_size):
        chunk = text[offset: offset + chunk_size]
        if chunk.strip():
            passages.append(Passage(
                id=f"p_baike_show_{uuid.uuid4().hex[:8]}",
                text=chunk,
                tags=[f"source:{url}", f"query:{ip_name}", "kind:show_page"],
                source="baidu_baike",
            ))
    return passages


async def fetch_baike_character(
    name: str,
    *,
    max_chars: int = 3000,
) -> Passage | None:
    """抓 /item/<name>（百度自动消歧）单角色页。"""
    if not name:
        return None
    url = BAIKE_BASE + quote(name)
    html = await _fetch_html(url)
    if not html:
        return None
    text = _html_to_text(html, max_chars)
    if not text.strip():
        return None
    return Passage(
        id=f"p_baike_char_{uuid.uuid4().hex[:8]}",
        text=text[:max_chars],
        tags=[f"source:{url}", f"query:{name}", "kind:character_page"],
        source="baidu_baike",
    )


async def fetch_baike_characters_batch(
    names: list[str],
    *,
    max_chars: int = 3000,
    concurrency: int = 4,
    sleep_between: float = 0.3,
) -> list[Passage]:
    """批量抓多个角色页，并发受限 + 限速防反爬。"""
    if not names:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def one(name: str) -> Passage | None:
        async with sem:
            p = await fetch_baike_character(name, max_chars=max_chars)
            await asyncio.sleep(sleep_between)
            return p

    results = await asyncio.gather(*(one(n) for n in names), return_exceptions=True)
    return [r for r in results if isinstance(r, Passage)]
