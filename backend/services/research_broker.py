from __future__ import annotations

import asyncio
import uuid
from uuid import uuid4

import structlog

from llm.base import LLMProvider, WebSearcher
from schemas.generation_strategy import ResearchArtifact, ResearchContext, ResearchRequest
from schemas.research_pack import Passage
from services.tavily_search import TavilySearch

logger = structlog.get_logger()

MAX_TAVILY_RESULTS_PER_QUERY = 3
MAX_SUMMARY_CHARS = 2000


async def _collect_text(provider: LLMProvider, messages: list[dict], system: str, max_tokens: int = 2048) -> str:
    parts: list[str] = []
    async for event in provider.stream_with_tools(messages=messages, tools=[], system=system, max_tokens=max_tokens):
        if event["type"] == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


class ResearchBroker:
    def __init__(
        self,
        tavily: TavilySearch | None = None,
        web_searcher: WebSearcher | None = None,
        synthesizer: LLMProvider | None = None,
    ):
        self.tavily = tavily
        self.web_searcher = web_searcher
        self.synthesizer = synthesizer
        self._artifact_cache: dict[str, list[ResearchArtifact]] = {}

    async def research(self, request: ResearchRequest) -> ResearchContext:
        artifacts = await self.collect_artifacts(request)
        summary = await self.summarize(request, artifacts)
        return self.build_context(request, artifacts, summary)

    async def collect_artifacts(self, request: ResearchRequest) -> list[ResearchArtifact]:
        queries = self._dedupe_queries(request.query_candidates, request.max_queries)
        if not queries:
            return []

        artifacts_by_query: dict[str, list[ResearchArtifact]] = {}
        pending_queries: dict[str, asyncio.Task[list[ResearchArtifact]]] = {}
        for query in queries:
            if query in self._artifact_cache:
                artifacts_by_query[query] = self._artifact_cache[query]
            else:
                pending_queries[query] = asyncio.create_task(self._run_query(query))

        if pending_queries:
            raw_results = await asyncio.gather(*pending_queries.values(), return_exceptions=True)
            for query, result in zip(pending_queries.keys(), raw_results, strict=False):
                if isinstance(result, Exception):
                    logger.warning("research_query_failed", query=query, exc_info=True)
                    artifacts_by_query[query] = []
                    continue
                self._artifact_cache[query] = result
                artifacts_by_query[query] = result

        artifacts: list[ResearchArtifact] = []
        for query in queries:
            artifacts.extend(artifacts_by_query.get(query, []))
        return artifacts

    async def collect_passages(self, request: ResearchRequest, max_chars: int) -> list[Passage]:
        """从 Tavily 检索结果产出结构化 Passage list（保留原文段，最多 max_chars 字符）。

        - tavily 不可用 → 返回空 list
        - 单条 query 异常 → 跳过该 query，继续其他
        - 整体 tavily 异常 → 返回空 list（不抛错）
        """
        if not self.tavily:
            return []
        passages: list[Passage] = []
        queries = self._dedupe_queries(request.query_candidates, request.max_queries)
        for query in queries:
            try:
                results = await self.tavily.search(query, max_results=MAX_TAVILY_RESULTS_PER_QUERY)
            except Exception:
                logger.warning("collect_passages_query_failed", query=query, exc_info=True)
                continue
            for r in results:
                content = (r.get("content") or "")[:max_chars]
                if not content:
                    continue
                passages.append(
                    Passage(
                        id=f"p_tav_{uuid.uuid4().hex[:8]}",
                        text=content,
                        tags=[f"source:{r.get('url', '')}", f"query:{query}"],
                        source="tavily",
                    )
                )
        return passages

    async def summarize(self, request: ResearchRequest, artifacts: list[ResearchArtifact]) -> str:
        return await self._summarize(request, artifacts)

    async def summarize_passages(self, passages: list[Passage]) -> str:
        """把 passages 压缩成简短摘要字符串。

        - 空列表直接返回 ""，不调 LLM。
        - 超过 30 条时只取前 30，避免 token 爆。
        - 有 synthesizer 时走 LLM 总结；否则 fallback 到前 6 条文本拼接。
        """
        if not passages:
            return ""
        capped = passages[:30]
        if self.synthesizer:
            passage_text = "\n\n".join(
                f"[{p.source}] {p.text}" for p in capped
            )
            summary = await _collect_text(
                self.synthesizer,
                messages=[{
                    "role": "user",
                    "content": (
                        f"资料：\n{passage_text}\n\n"
                        "请整理成一份简洁的创作参考摘要，突出最关键的信息。输出纯文本。"
                    ),
                }],
                system="你是一个创作研究助手，负责把原文段落压缩成可直接用于生成环节的参考摘要。",
                max_tokens=1024,
            )
            if summary:
                return summary
        # fallback：前 6 条文本拼接
        return "\n".join(p.text for p in capped[:6])[:MAX_SUMMARY_CHARS]

    def build_context(self, request: ResearchRequest, artifacts: list[ResearchArtifact], summary: str) -> ResearchContext:
        tags = list(dict.fromkeys([*request.focuses, *[artifact.source for artifact in artifacts]]))
        return ResearchContext(stage=request.stage, summary=summary[:MAX_SUMMARY_CHARS], artifacts=artifacts, tags=tags)

    def _dedupe_queries(self, queries: list[str], max_queries: int) -> list[str]:
        result: list[str] = []
        for query in queries:
            normalized = _normalize_query(query)
            if not normalized or normalized in result:
                continue
            result.append(normalized)
            if len(result) >= max_queries:
                break
        return result

    async def _run_query(self, query: str) -> list[ResearchArtifact]:
        tasks = [asyncio.create_task(self._search_tavily(query)), asyncio.create_task(self._search_web(query))]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        artifacts: list[ResearchArtifact] = []
        for result in raw_results:
            if isinstance(result, Exception):
                logger.warning("research_query_failed", query=query, exc_info=True)
                continue
            artifacts.extend(result)
        return artifacts

    async def _search_tavily(self, query: str) -> list[ResearchArtifact]:
        if not self.tavily:
            return []
        results = await self.tavily.search(query, max_results=MAX_TAVILY_RESULTS_PER_QUERY)
        artifacts: list[ResearchArtifact] = []
        for item in results:
            excerpt = str(item.get("content", ""))[:300]
            artifacts.append(
                ResearchArtifact(
                    artifact_id=str(uuid4()),
                    query=query,
                    source="tavily",
                    title=str(item.get("title", "")),
                    excerpt=excerpt,
                    summary=excerpt,
                    url=str(item.get("url", "")),
                )
            )
        return artifacts

    async def _search_web(self, query: str) -> list[ResearchArtifact]:
        if not self.web_searcher:
            return []
        result = await self.web_searcher.web_search(query)
        summary = result.text[:600]
        if not summary.strip() and not result.citations:
            return []
        return [
            ResearchArtifact(
                artifact_id=str(uuid4()),
                query=query,
                source="web_search",
                title=query,
                excerpt=summary,
                summary=summary,
            )
        ]

    async def _summarize(self, request: ResearchRequest, artifacts: list[ResearchArtifact]) -> str:
        if not artifacts:
            return ""
        if self.synthesizer:
            artifact_text = "\n\n".join(
                f"[{artifact.source}] {artifact.title}\n{artifact.summary or artifact.excerpt}"
                for artifact in artifacts[:8]
            )
            summary = await _collect_text(
                self.synthesizer,
                messages=[{
                    "role": "user",
                    "content": (
                        f"阶段：{request.stage}\n"
                        f"目标：{request.goal}\n"
                        f"关注点：{'、'.join(request.focuses) or '通用创作参考'}\n\n"
                        f"资料：\n{artifact_text}\n\n"
                        "请整理成一份简洁的创作参考摘要，突出和当前阶段最相关的信息。输出纯文本。"
                    ),
                }],
                system="你是一个创作研究助手，负责把搜索结果压缩成可直接用于生成环节的参考摘要。",
                max_tokens=1024,
            )
            if summary:
                return summary
        return "\n".join(artifact.summary or artifact.excerpt for artifact in artifacts[:6])[:MAX_SUMMARY_CHARS]
