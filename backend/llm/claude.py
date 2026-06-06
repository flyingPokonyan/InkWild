from typing import AsyncIterator

import anthropic

from config import settings
from llm.base import LLMProvider


def _finish_reason_from_stop(stop_reason: str | None) -> str | None:
    """Normalize Anthropic ``stop_reason`` to the OpenAI-style ``finish_reason``
    the director's truncation detector consumes. ``max_tokens`` is the only one
    that must become ``length``; ``end_turn``/``stop_sequence`` collapse to
    ``stop``; ``tool_use`` passes through; ``None`` stays ``None``."""
    if stop_reason is None:
        return None
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason in {"end_turn", "stop_sequence"}:
        return "stop"
    return stop_reason


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        self.client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
        self.model = model or settings.llm_default_model

    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        response_format: dict | None = None,  # Anthropic does not support; ignored.
        tool_choice: str | dict | None = None,
        reasoning: bool | None = None,  # extended-thinking control not plumbed here yet; accepted for parity
    ) -> AsyncIterator[dict]:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
            # Convert OpenAI-style {"type":"function","function":{"name":"X"}}
            # to Anthropic's {"type":"tool","name":"X"}; pass-through for
            # native Anthropic shapes; default to {"type":"auto"}.
            if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
                fn = tool_choice.get("function") or {}
                kwargs["tool_choice"] = {"type": "tool", "name": fn.get("name", "")}
            elif isinstance(tool_choice, dict):
                kwargs["tool_choice"] = tool_choice
            else:
                kwargs["tool_choice"] = {"type": "auto"}

        async with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text_delta", "text": event.delta.text}
                    elif event.delta.type == "input_json_delta":
                        yield {"type": "input_json_delta", "partial_json": event.delta.partial_json}
                elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                    yield {
                        "type": "tool_use_start",
                        "name": event.content_block.name,
                        "id": event.content_block.id,
                    }

            final = await stream.get_final_message()

            for block in final.content:
                if block.type == "tool_use":
                    yield {"type": "tool_use", "name": block.name, "input": block.input}

            yield {
                "type": "usage",
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
                "finish_reason": _finish_reason_from_stop(
                    getattr(final, "stop_reason", None)
                ),
            }
