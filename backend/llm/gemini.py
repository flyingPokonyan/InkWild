from __future__ import annotations

from llm.openai_compatible import OpenAICompatibleImageProvider, OpenAICompatibleProvider


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(OpenAICompatibleProvider):
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None):
        super().__init__(
            api_key=api_key,
            base_url=(base_url or GEMINI_OPENAI_BASE_URL).rstrip("/"),
            model=model,
        )


class GeminiImageProvider(OpenAICompatibleImageProvider):
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None):
        super().__init__(
            api_key=api_key,
            base_url=(base_url or GEMINI_OPENAI_BASE_URL).rstrip("/"),
            model=model,
        )
