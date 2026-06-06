import uuid
from urllib.parse import quote

import httpx
import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()

WIKI_BASE = "https://zh.wikipedia.org/wiki/"
USER_AGENT = "InkWild-IPResearch/0.1 (admin tool; contact: dev)"


async def fetch_wikipedia(
    ip_name: str,
    *,
    max_chars: int = 2000,
    max_chunks: int = 2,
    timeout: float = 8.0,
) -> list[Passage]:
    """抓 zh.wikipedia.org/wiki/<ip_name>，返回纯文本切成最多 max_chunks 段，每段最多 max_chars 字符。

    失败返回空 list（不抛错）。
    """
    if not ip_name:
        return []
    url = WIKI_BASE + quote(ip_name)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("wikipedia_fetch_failed", ip_name=ip_name, error=str(exc))
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup_not_installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    # Strip noise but preserve infobox tables (they hold canonical IP data).
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all("table"):
        # Some bs4 nodes (eg. doctype-like) expose attrs=None; tag.get() then
        # blows up. Skip those — they're not <table> anyway.
        if getattr(tag, "attrs", None) is None:
            continue
        classes = tag.get("class", []) or []
        if not any(c.startswith("infobox") for c in classes):
            tag.decompose()
    content = soup.find(id="mw-content-text")
    text = content.get_text(separator="\n", strip=True) if content else ""

    passages: list[Passage] = []
    for offset in range(0, len(text), max_chars):
        if len(passages) >= max_chunks:
            break
        chunk = text[offset: offset + max_chars]
        if chunk.strip():
            passages.append(Passage(
                id=f"p_wiki_{uuid.uuid4().hex[:8]}",
                text=chunk,
                tags=[f"source:{url}", f"query:{ip_name}"],
                source="wikipedia",
            ))
    return passages
