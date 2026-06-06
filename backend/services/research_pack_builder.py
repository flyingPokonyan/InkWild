"""ResearchPack 构建：admin_note 切片 / IP probing / 三路合并。

本文件实现 ResearchPack 的 builder 函数：
- slice_admin_note_to_passages: 把 admin description 拆段落 → Passage list（无 LLM）
- probe_ip_canon: LLM 自查 IP 结构化知识 → IPCanon
- build_research_pack: 三路并发合并（在 Task 1.7 加）

LLMRouter API 说明：
  LLMRouter 只暴露 stream_with_tools(messages, tools, system, max_tokens, ...)。
  本文件用 tools=[] 触发纯文本流，收集 text_delta 事件后拼接，再 json.loads 解析。
  这与 world_creator_agent._collect_text 的模式一致。
"""
import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog

from schemas.research_pack import IPCanon, Passage, ResearchPack

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# admin_note 切片
# ---------------------------------------------------------------------------


def slice_admin_note_to_passages(text: str, max_chars: int) -> list[Passage]:
    """把 admin description 按段落切片，超长段落硬切到 max_chars。

    返回的 Passage.source 都标 "admin_note"。
    空字符串或全空白输入返回空列表。
    """
    text = (text or "").strip()
    if not text:
        return []

    # 按双换行切段落；过滤空段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    passages: list[Passage] = []
    for para in paragraphs:
        for offset in range(0, len(para), max_chars):
            chunk = para[offset : offset + max_chars]
            if not chunk:
                continue
            passages.append(
                Passage(
                    id=f"p_admin_{uuid.uuid4().hex[:8]}",
                    text=chunk,
                    tags=[],
                    source="admin_note",
                )
            )
    return passages


# ---------------------------------------------------------------------------
# IP probing（LLM 自查）
# ---------------------------------------------------------------------------

_IP_PROBE_SYSTEM = """你是一个 IP / 题材识别助手。
给你一段世界生成描述，输出你（作为 LLM）已知的、与该描述强相关的：
- 候选作品名（title_guesses）
- 标志性人名（canonical_names）
- 标志性地名（canonical_places）
- 标志性物件（iconic_objects）
- 标志性称谓 / 台词风格（lingo）
- 著名事件名（notable_events）

如果描述指向你不熟悉的 IP / 原创世界，所有字段输出空数组即可。
严格 JSON 输出，不包含解释文字。格式示例：
{"title_guesses":[],"canonical_names":[],"canonical_places":[],"iconic_objects":[],"lingo":[],"notable_events":[]}"""


async def _collect_stream_text(llm_router: Any, *, system: str, messages: list[dict], max_tokens: int) -> str:
    """通过 stream_with_tools(tools=[]) 收集纯文本输出。"""
    parts: list[str] = []
    async for event in llm_router.stream_with_tools(
        messages=messages,
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _extract_json_from_text(text: str) -> dict | None:
    """从 LLM 返回的文本中提取 JSON 对象，兼容 Markdown 代码块包裹。"""
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


async def probe_ip_canon(description: str, llm_router: Any) -> IPCanon:
    """让 LLM 自查它对该 IP 的结构化知识，返回 IPCanon。

    失败（LLM 异常 / 返回非法 JSON）时返回空 IPCanon，不抛错。
    """
    try:
        text = await _collect_stream_text(
            llm_router,
            system=_IP_PROBE_SYSTEM,
            messages=[{"role": "user", "content": description}],
            max_tokens=1024,
        )
        data = _extract_json_from_text(text)
        if data is None:
            logger.warning("ip_probe_json_parse_failed", text_preview=text[:200])
            return IPCanon()
        return IPCanon(
            title_guesses=data.get("title_guesses") or [],
            canonical_names=data.get("canonical_names") or [],
            canonical_places=data.get("canonical_places") or [],
            iconic_objects=data.get("iconic_objects") or [],
            lingo=data.get("lingo") or [],
            notable_events=data.get("notable_events") or [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_probe_failed", error=str(exc))
        return IPCanon()


# ---------------------------------------------------------------------------
# 三路并发合并
# ---------------------------------------------------------------------------


async def build_research_pack(
    description: str,
    broker: Any,                            # ResearchBroker 实例
    llm_router: Any,                        # LLMRouter
    max_passages: int,
    max_passage_chars: int,
    research_request: Any | None = None,    # schemas.generation_strategy.ResearchRequest | None
) -> ResearchPack:
    """三路并发合并产出 ResearchPack：

    - admin_note: 把 description 按段落切片
    - tavily: broker.collect_passages 拉原文段
    - ip_probe: probe_ip_canon LLM 自查

    优先级：admin_note > tavily（ip_probe 不出 passages 只出 ip_canon）
    总 passages 数受 max_passages 上限裁剪。
    """
    from schemas.generation_strategy import ResearchRequest

    # admin_note 切片是同步操作，用 asyncio.to_thread 跟另外两路并发
    admin_passages_coro = asyncio.to_thread(
        slice_admin_note_to_passages, description, max_passage_chars,
    )

    request = research_request or ResearchRequest(
        stage="world_base",
        goal=description,
        query_candidates=[description] if description.strip() else [],
    )
    tavily_coro = broker.collect_passages(request, max_chars=max_passage_chars)
    canon_coro = probe_ip_canon(description, llm_router=llm_router)

    admin_passages, tavily_passages, ip_canon = await asyncio.gather(
        admin_passages_coro, tavily_coro, canon_coro,
    )

    # 容量裁剪：admin 全保留，剩余配额给 tavily
    passages: list[Passage] = list(admin_passages)
    remaining = max_passages - len(passages)
    if remaining > 0:
        passages.extend(tavily_passages[:remaining])

    summary = await broker.summarize_passages(passages) if passages else ""

    return ResearchPack(
        summary=summary,
        passages=passages,
        ip_canon=ip_canon,
    )
