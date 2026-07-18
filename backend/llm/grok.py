"""Grok (xAI) LLM Provider — text/tool streaming + web search + image generation.

Uses OpenAI-compatible API for chat/tool calls and Live Search (search_parameters
on chat.completions) for web search, and xAI SDK for image generation (Imagine API).
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx
import structlog
from openai import AsyncOpenAI

from config import settings
from llm.base import ImageGenerator, ImageResult, LLMProvider, WebSearcher, WebSearchResult

logger = structlog.get_logger()


class GrokProvider(LLMProvider, ImageGenerator, WebSearcher):
    """xAI Grok — implements all three LLM capabilities.

    - LLMProvider: chat completions via OpenAI-compatible API
    - WebSearcher: real-time web search via xAI Responses API
    - ImageGenerator: image generation via Grok Imagine API
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        image_model: str | None = None,
    ):
        self._api_key = api_key or settings.grok_api_key
        self._base_url = base_url or settings.grok_base_url
        self.model = model or settings.grok_model
        self.image_model = image_model or settings.grok_image_model

        # OpenAI-compatible client for chat completions
        self.client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    # -------------------------------------------------------------------
    # LLMProvider — chat completions with tool use
    # -------------------------------------------------------------------

    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        response_format: dict | None = None,
        tool_choice: str | dict | None = None,
        reasoning: bool | None = None,
    ) -> AsyncIterator[dict]:
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [_convert_tool(t) for t in tools]
            kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        if response_format:
            kwargs["response_format"] = response_format
        # Play/realtime slots pass reasoning=False. Official xAI cannot fully
        # disable thinking; lowest supported control is effort=low (object form).
        if reasoning is False:
            kwargs["extra_body"] = {"reasoning": {"effort": "low"}}

        stream = await self.client.chat.completions.create(**kwargs)

        tool_buffers: dict[int, dict] = {}
        usage = None
        finish_reason: str | None = None
        reasoning_content_chunks = 0
        reasoning_content_chars = 0

        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage

            for choice in getattr(chunk, "choices", []) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue

                reasoning_content = getattr(delta, "reasoning_content", None)
                if isinstance(reasoning_content, str) and reasoning_content:
                    reasoning_content_chunks += 1
                    reasoning_content_chars += len(reasoning_content)

                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "text_delta", "text": content}

                for tool_call in getattr(delta, "tool_calls", None) or []:
                    index = getattr(tool_call, "index", 0)
                    state = tool_buffers.setdefault(
                        index,
                        {"name": "", "id": "", "arguments": [], "started": False},
                    )

                    if getattr(tool_call, "id", None):
                        state["id"] = tool_call.id

                    function = getattr(tool_call, "function", None)
                    if function and getattr(function, "name", None):
                        state["name"] = function.name

                    if not state["started"] and state["name"]:
                        state["started"] = True
                        yield {
                            "type": "tool_use_start",
                            "name": state["name"],
                            "id": state["id"],
                        }

                    arguments = function.arguments if function and getattr(function, "arguments", None) else ""
                    if arguments:
                        state["arguments"].append(arguments)
                        yield {"type": "input_json_delta", "partial_json": arguments}

        for index in sorted(tool_buffers):
            state = tool_buffers[index]
            raw = "".join(state["arguments"]) or "{}"
            try:
                parsed_input = json.loads(raw)
            except json.JSONDecodeError:
                parsed_input = {}
            yield {"type": "tool_use", "name": state["name"], "input": parsed_input}

        usage_event = {
            "type": "usage",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "finish_reason": finish_reason,
        }
        if reasoning_content_chunks:
            usage_event["reasoning_content_chunks"] = reasoning_content_chunks
            usage_event["reasoning_content_chars"] = reasoning_content_chars
        yield usage_event

    # -------------------------------------------------------------------
    # WebSearcher — Grok server-side Web Search via Responses API
    # -------------------------------------------------------------------

    async def web_search(
        self,
        query: str,
        max_tokens: int = 2048,
    ) -> WebSearchResult:
        """Run Grok Web Search and preserve its structured source citations.

        xAI exposes server-side web search through the Responses API. Some
        OpenAI-compatible gateways accept ``search_parameters`` on Chat
        Completions but silently ignore the search tool, returning plausible
        model-memory text with no sources. Responses API output annotations are
        the authoritative citation channel used here.
        """
        url = f"{self._base_url.rstrip('/')}/responses"
        payload = {
            "model": self.model,
            "input": [{"role": "user", "content": query}],
            "tools": [{"type": "web_search"}],
            "max_output_tokens": max_tokens,
            "max_tool_calls": 8,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            total_timeout = max(
                float(settings.grok_web_search_total_timeout_seconds),
                0.001,
            )
            async with asyncio.timeout(total_timeout):
                async with httpx.AsyncClient(timeout=100.0) as http:
                    resp = await http.post(url, headers=headers, json=payload)
        except TimeoutError:
            logger.warning(
                "grok_web_search_timeout",
                query=query,
                timeout_seconds=settings.grok_web_search_total_timeout_seconds,
            )
            return WebSearchResult(query=query)
        except Exception:  # noqa: BLE001
            logger.warning("grok_web_search_failed", query=query, exc_info=True)
            return WebSearchResult(query=query)

        if resp.status_code != 200:
            logger.warning(
                "grok_web_search_http_error",
                query=query,
                status=resp.status_code,
                body=resp.content[:300],
            )
            return WebSearchResult(query=query)

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("grok_web_search_invalid_json", query=query)
            return WebSearchResult(query=query)

        text_parts: list[str] = []
        citations: list[dict] = []
        seen: set[str] = set()

        def _add_citation(raw: object) -> None:
            if isinstance(raw, str):
                url_ = raw.strip()
                title = ""
            elif isinstance(raw, dict):
                nested = raw.get("url_citation") or raw.get("web_citation") or raw
                if not isinstance(nested, dict):
                    return
                url_ = str(nested.get("url") or "").strip()
                title = str(nested.get("title") or raw.get("title") or "")
            else:
                return
            if not url_ or url_ in seen:
                return
            seen.add(url_)
            citations.append({"url": url_, "title": title})

        for raw in data.get("citations") or []:
            _add_citation(raw)
        for item in data.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict) or content.get("type") != "output_text":
                    continue
                piece = str(content.get("text") or "")
                if piece:
                    text_parts.append(piece)
                for annotation in content.get("annotations") or []:
                    _add_citation(annotation)

        text = "".join(text_parts).strip()

        return WebSearchResult(text=text, citations=citations, query=query)

    # -------------------------------------------------------------------
    # ImageGenerator — Grok Imagine API via xAI SDK
    # -------------------------------------------------------------------

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> ImageResult:
        """Generate an image using Grok Imagine (Aurora model)."""
        try:
            import xai_sdk

            client = xai_sdk.AsyncClient(api_key=self._api_key)
            response = await client.image.sample(
                prompt=prompt,
                model=self.image_model,
                aspect_ratio=aspect_ratio,
            )

            return ImageResult(
                url=response.url or "",
                format="png",
                model=self.image_model,
            )
        except ImportError:
            logger.warning("xai_sdk_not_installed", msg="pip install xai-sdk to enable Grok image generation")
            return ImageResult()
        except Exception:
            logger.warning("grok_image_generation_failed", prompt=prompt[:80], exc_info=True)
            return ImageResult()


def _convert_tool(tool: dict) -> dict:
    """Convert Anthropic-style tool schema to OpenAI function calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }
