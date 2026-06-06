import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from config import settings
from llm.base import LLMProvider

# DeepSeek's OpenAI-compatible knob to turn off the thinking phase on
# thinking-capable models (deepseek-v4-pro, deepseek-r1). Applied when a call
# passes ``reasoning=False`` — i.e. realtime game-loop slots that want speed
# and clean JSON over chain-of-thought.
_THINKING_DISABLED_EXTRA_BODY = {"thinking": {"type": "disabled"}}


def _build_usage_event(usage, finish_reason: str | None = None) -> dict:
    """Construct the {"type":"usage",...} payload, surfacing prefix-cache
    fields when present so admin / logs can see hit rate.

    Two API shapes are supported:
    - DeepSeek direct: usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens
    - OpenAI standard (mgtv etc.): usage.prompt_tokens_details.cached_tokens

    ``finish_reason`` ("stop" | "length" | …) is surfaced so callers can detect
    truncation — DeepSeek JSON mode returns truncated/invalid JSON when the
    output hits max_tokens, and "length" is the only signal for it.
    """
    event: dict = {
        "type": "usage",
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }
    if finish_reason is not None:
        event["finish_reason"] = finish_reason
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
    return event


def _convert_tool_to_openai(tool: dict) -> dict:
    """Convert Anthropic-style tool definition to OpenAI-style function definition."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


class DeepSeekProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = model or settings.llm_default_model

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
        if reasoning is False:
            kwargs["extra_body"] = dict(_THINKING_DISABLED_EXTRA_BODY)
        stream = await self.client.chat.completions.create(**kwargs)

        tool_buffers: dict[int, dict] = {}
        usage = None

        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage

            for choice in getattr(chunk, "choices", []) or []:
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue

                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "text_delta", "text": content}

                for tool_call in getattr(delta, "tool_calls", None) or []:
                    index = getattr(tool_call, "index", 0)
                    state = tool_buffers.setdefault(
                        index,
                        {
                            "name": "",
                            "id": "",
                            "arguments": [],
                            "started": False,
                        },
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
                        yield {
                            "type": "input_json_delta",
                            "partial_json": arguments,
                        }

        for index in sorted(tool_buffers):
            state = tool_buffers[index]
            arguments = "".join(state["arguments"]) or "{}"
            try:
                parsed_input = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_input = {}
            yield {
                "type": "tool_use",
                "name": state["name"],
                "input": parsed_input,
            }

        yield _build_usage_event(usage)

    async def stream_json(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        reasoning: bool | None = None,
    ) -> AsyncIterator[dict]:
        """Native JSON object mode — no tool plumbing.

        For deepseek-v4-pro / deepseek-r1 this is the preferred path: ask for a
        single JSON object as the response and let the caller parse it. Avoids
        the unreliable ``tool_choice=auto`` flow where thinking models emit
        chain-of-thought instead of invoking the tool. Pass ``reasoning=False``
        to additionally disable the model's thinking phase (realtime slots).
        """
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        create_kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=oai_messages,
            stream=True,
            stream_options={"include_usage": True},
            response_format={"type": "json_object"},
        )
        if reasoning is False:
            create_kwargs["extra_body"] = dict(_THINKING_DISABLED_EXTRA_BODY)
        stream = await self.client.chat.completions.create(**create_kwargs)

        usage = None
        finish_reason = None
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            for choice in getattr(chunk, "choices", []) or []:
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "text_delta", "text": content}

        yield _build_usage_event(usage, finish_reason)
