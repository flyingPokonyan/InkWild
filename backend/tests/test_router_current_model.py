"""Phase 7 router helper: current_model_id() lookup."""
import pytest
from llm.router import LLMRouter
from llm.base import LLMProvider


class _StubProvider(LLMProvider):
    def __init__(self, model: str):
        self.model = model
    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048,
                                response_format=None, tool_choice=None):
        if False:
            yield {}


def test_current_model_id_reads_identity():
    router = LLMRouter(
        providers={"deepseek-v4-pro": _StubProvider("deepseek-v4-pro")},
        identity={"provider_name": "deepseek", "model_id": "deepseek-v4-pro"},
    )
    assert router.current_model_id() == "deepseek-v4-pro"


def test_current_model_id_falls_back_to_provider_model():
    router = LLMRouter(
        providers={"x": _StubProvider("claude-sonnet-4-6")},
        identity={},
    )
    assert router.current_model_id() == "claude-sonnet-4-6"


def test_current_model_id_empty_when_no_provider():
    router = LLMRouter(providers={}, identity={})
    assert router.current_model_id() == ""
