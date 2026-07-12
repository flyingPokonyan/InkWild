from __future__ import annotations

import base64
import json
from typing import AsyncIterator

import httpx
from openai import AsyncOpenAI

from llm.base import ImageGenerator, ImageResult, LLMProvider

# httpx-level safety net for streaming calls. ``read`` is the per-chunk
# inter-arrival gap: if the upstream emits no bytes for this long the SDK
# raises ReadTimeout, which the router classifies as transient.
_DEFAULT_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=150.0, write=10.0, pool=10.0)

_GPT_IMAGE_OUTPUT_FORMAT = "webp"
_GPT_IMAGE_OUTPUT_COMPRESSION = 85

# Image generation is non-streaming and legitimately slow, but the OpenAI SDK
# default is 600s/attempt. Use a bounded per-attempt read timeout; the workshop
# image ladder retries timeout/unknown failures above this layer.
def _image_timeout_seconds() -> float:
    from config import settings

    return max(float(getattr(settings, "image_generation_timeout_seconds", 100.0)), 0.001)


def _image_httpx_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10.0, read=_image_timeout_seconds(), write=10.0, pool=10.0)


def _convert_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    """Map an aspect-ratio string to a Seedream/DALL·E-style ``WxH`` size.

    The keys here are the only ratios our image pipeline emits. Unknown ratios
    fall back to 1024×1024.
    """
    normalized = (aspect_ratio or "1:1").strip()
    return {
        "1:1": "1024x1024",
        "16:9": "1536x1024",
        "3:4": "1024x1536",
        "4:3": "1536x1024",
        # New (2026-05): cinematic / portrait variants
        "21:9": "1792x768",     # ~21:9 super-wide hero
        "3:2": "1536x1024",     # cinematic horizontal card (alias for 16:9 with intent)
        "2:3": "1024x1536",     # vertical character portrait (alias for 3:4 with intent)
    }.get(normalized, "1024x1024")


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        reasoning_off_extra_body: dict | None = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_DEFAULT_HTTPX_TIMEOUT,
        )
        self.model = model
        # Vendor-specific OpenAI ``extra_body`` recipe for DISABLING reasoning,
        # applied only when a call passes ``reasoning=False``. This endpoint is
        # vendor-agnostic, so the recipe is configured per provider via
        # ``model_providers.extra_config["reasoning_off"]``. Examples:
        #   DeepSeek V4 Pro:  {"thinking": {"type": "disabled"}}
        #   Gemini (compat):  {"google": {"thinking_config": {"thinking_budget": 0}}}
        self._reasoning_off_extra_body = dict(reasoning_off_extra_body or {})

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

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [_convert_tool_to_openai(t) for t in tools]
            kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        if response_format:
            kwargs["response_format"] = response_format
        if reasoning is False and self._reasoning_off_extra_body:
            kwargs["extra_body"] = dict(self._reasoning_off_extra_body)

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

        event = {
            "type": "usage",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "finish_reason": finish_reason,
        }
        # Prompt cache 命中量。两种 API shape：
        # - DeepSeek 直连：usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens
        # - OpenAI 标准（含 mgtv 等聚合网关）：usage.prompt_tokens_details.cached_tokens
        if usage is not None:
            hit = getattr(usage, "prompt_cache_hit_tokens", None)
            miss = getattr(usage, "prompt_cache_miss_tokens", None)
            if hit is None:
                details = getattr(usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = getattr(details, "cached_tokens", None)
                    if cached is not None:
                        hit = int(cached)
                        miss = max(int(event["input_tokens"]) - hit, 0)
            if hit is not None:
                event["cache_hit_tokens"] = int(hit)
            if miss is not None:
                event["cache_miss_tokens"] = int(miss)
        if reasoning_content_chunks:
            event["reasoning_content_chunks"] = reasoning_content_chunks
            event["reasoning_content_chars"] = reasoning_content_chars
        yield event


class OpenAICompatibleImageProvider(ImageGenerator):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
    ):
        # Bounded per-attempt timeout (see _image_httpx_timeout). max_retries=0:
        # we run our own retry/fallback ladder upstream, so the SDK's built-in
        # retries would only compound the worst-case latency.
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_image_httpx_timeout(),
            max_retries=0,
        )
        self.model = model

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
        quality: str | None = None,
    ) -> ImageResult:
        # GPT Image 2 / OpenAI 兼容支持 quality="low|medium|high|auto"。
        # 通过 settings 注入而不是硬编码 — 便于 admin 在 prod / preview 间切。
        if quality is None:
            from config import settings as _settings
            quality = getattr(_settings, "image_generation_quality", "high")
        request = {
            "model": self.model,
            "prompt": prompt,
            "size": _size_for_aspect_ratio(aspect_ratio),
            "quality": quality,
        }
        if self.model.startswith("gpt-image"):
            # GPT Image defaults to lossless PNG. Covers are photographic and
            # cross-region OSS uploads are substantially faster as WebP.
            request["output_format"] = _GPT_IMAGE_OUTPUT_FORMAT
            request["output_compression"] = _GPT_IMAGE_OUTPUT_COMPRESSION
        else:
            request["extra_body"] = {"aspect_ratio": aspect_ratio, "resolution": resolution}
        response = await self.client.images.generate(**request)
        data = response.data[0] if getattr(response, "data", None) else None
        if not data:
            return ImageResult(model=self.model)
        if getattr(data, "url", None):
            return ImageResult(url=data.url or "", model=self.model)
        if getattr(data, "b64_json", None):
            return ImageResult(
                base64_data=base64.b64decode(data.b64_json),
                format=(
                    _GPT_IMAGE_OUTPUT_FORMAT
                    if self.model.startswith("gpt-image")
                    else "png"
                ),
                model=self.model,
            )
        return ImageResult(model=self.model)
