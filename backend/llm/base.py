"""LLM provider abstractions.

LLMProvider — core text/tool streaming (all providers).
ImageGenerator — image generation capability (optional).
WebSearcher — built-in web search capability (optional).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


class LLMProvider(ABC):
    """Core LLM interface: streaming text + tool use."""

    @abstractmethod
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
        """Yield provider events like text deltas, tool calls, and usage.

        ``reasoning``: tri-state thinking/reasoning control. ``None`` = use the
        model's own default; ``False`` = disable thinking (realtime game-loop
        slots ask for this — see resolve_slot_router); ``True`` = force on.
        Providers translate to their vendor knob (DeepSeek ``thinking``,
        Gemini ``thinking_config``); those without one MUST silently ignore.

        ``response_format``: optional OpenAI-compatible response_format payload
        (e.g. ``{"type": "json_object"}`` or
        ``{"type": "json_schema", "json_schema": {...}}``). Providers that do
        not natively support it (e.g. Anthropic) MUST silently ignore.

        ``tool_choice``: when ``tools`` is non-empty, controls how the model
        chooses among them. Pass ``"auto"`` (default), ``"required"``, or
        OpenAI-style ``{"type":"function","function":{"name":"X"}}`` to force
        a specific tool. Providers that don't natively support forced choice
        SHOULD treat it as ``"auto"``.

        Usage-event contract: the final event yielded MUST be
        ``{"type": "usage", "input_tokens": int, "output_tokens": int,
        "finish_reason": str | None}``. ``finish_reason`` follows OpenAI
        semantics ("stop" | "length" | "tool_calls" | provider-native | None);
        downstream truncation detection (director_agent) depends on "length"
        being surfaced here. ``cache_hit_tokens``/``cache_miss_tokens`` optional.
        """

    async def stream_json(  # type: ignore[empty-body]
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        reasoning: bool | None = None,
    ) -> AsyncIterator[dict]:
        """Native JSON object mode — no tool plumbing.

        Implementations should ask the underlying API to emit a single JSON
        object as plain text and yield ``text_delta`` events (and a final
        ``usage`` event). Caller parses the concatenated text as JSON.

        Default implementation: providers that don't override this fall back
        to ``stream_with_tools`` with ``response_format={"type":"json_object"}``
        and no tools — works for OpenAI-compatible endpoints.
        """
        async for ev in self.stream_with_tools(
            messages=messages,
            tools=[],
            system=system,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            reasoning=reasoning,
        ):
            yield ev


@dataclass
class ImageResult:
    """Result of an image generation request."""

    url: str = ""
    base64_data: bytes = b""
    format: str = "png"
    model: str = ""

    @property
    def has_url(self) -> bool:
        return bool(self.url)

    @property
    def has_data(self) -> bool:
        return bool(self.base64_data)


@dataclass
class WebSearchResult:
    """Result of a web search query."""

    text: str = ""
    citations: list[dict] = field(default_factory=list)
    query: str = ""


class ImageGenerator(ABC):
    """Capability: generate images from text prompts."""

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
    ) -> ImageResult:
        """Generate a single image from a text prompt."""


class WebSearcher(ABC):
    """Capability: built-in web search (e.g. Grok web_search tool)."""

    @abstractmethod
    async def web_search(
        self,
        query: str,
        max_tokens: int = 2048,
    ) -> WebSearchResult:
        """Search the web and return synthesized text with citations."""
