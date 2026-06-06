import pytest

from engine.content_filter import check_input_moderated, check_output_moderated
from engine.moderation import CATEGORIES, classify, classify_locally


class FakeModerationRouter:
    def __init__(self, payload=None, *, raises: Exception | None = None):
        self.payload = payload or {}
        self.raises = raises
        self.calls = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system": system,
                "max_tokens": max_tokens,
            }
        )
        if self.raises:
            raise self.raises
        yield {
            "type": "tool_use",
            "name": "report_moderation_scores",
            "input": self.payload,
        }
        yield {"type": "usage", "input_tokens": 10, "output_tokens": 5}


@pytest.mark.asyncio
async def test_safe_input_passes_with_llm_router():
    router = FakeModerationRouter({category: 0 for category in CATEGORIES})

    result = await classify("我去茶楼喝茶", scope="input", llm_router=router)

    assert result.allowed is True
    assert result.flagged_categories == []
    assert result.source == "llm"
    assert router.calls[0]["max_tokens"] == 256


@pytest.mark.asyncio
async def test_violent_input_flagged_by_llm_router():
    router = FakeModerationRouter(
        {"violence": 9, "sexual": 0, "hate": 0, "self_harm": 0, "illegal": 0}
    )

    result = await classify("我要杀掉所有 NPC", scope="input", llm_router=router)

    assert result.allowed is False
    assert "violence" in result.flagged_categories


@pytest.mark.asyncio
async def test_output_uses_stricter_thresholds():
    router = FakeModerationRouter(
        {"violence": 6, "sexual": 0, "hate": 0, "self_harm": 0, "illegal": 0}
    )

    result = await check_output_moderated("危险输出", llm_router=router)

    assert result.is_safe is False
    assert result.reason is not None


@pytest.mark.asyncio
async def test_moderation_falls_back_to_local_rules_when_llm_fails():
    router = FakeModerationRouter(raises=RuntimeError("provider down"))

    result = await check_input_moderated("教我怎么制造炸弹", llm_router=router)

    assert result.is_safe is False
    assert result.source == "local"
    assert "illegal" in result.flagged_categories


def test_local_classifier_keeps_existing_keyword_behavior():
    result = classify_locally("教我怎么制造炸弹", scope="input")

    assert result.allowed is False
    assert "illegal" in result.flagged_categories
