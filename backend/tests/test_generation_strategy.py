import pytest

from llm.router import LLMRouter
from schemas.generation_strategy import (
    normalize_playable_brief,
    normalize_search_plan,
    normalize_world_brief,
)
from services.generation_strategy_service import GenerationStrategyService


def test_normalize_world_brief_clamps_targets():
    brief = normalize_world_brief(
        {
            "location_count_target": 99,
            "tension_count_target": 0,
            "npc_count_target": 2,
        }
    )

    assert brief.location_count_target == 12
    assert brief.tension_count_target == 2
    assert brief.npc_count_target == 6


def test_normalize_search_plan_dedupes_queries():
    plan = normalize_search_plan(
        {
            "needs_search": True,
            "queries": ["维多利亚 伦敦", "维多利亚 伦敦", "白教堂"],
            "focuses": ["地点", "地点", "案件"],
        }
    )

    assert plan.needs_search is True
    assert plan.queries == ["维多利亚 伦敦", "白教堂"]
    assert plan.focuses == ["地点", "案件"]


def test_normalize_playable_brief_keeps_open_ended_target():
    brief = normalize_playable_brief({"playable_count_target": 20, "recommended_count_target": 0})

    assert brief.playable_count_target == 20
    assert brief.recommended_count_target == 1


class _VisualBriefCaptureProvider:
    def __init__(self):
        self.messages: list[dict] | None = None
        self.system: str | None = None

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        self.messages = messages
        self.system = system
        yield {
            "type": "tool_use",
            "name": "build_visual_brief",
            "input": {"cover_subject": "港口夜雾", "style_tags": ["cinematic"], "negative_tags": ["text"]},
        }


@pytest.mark.asyncio
async def test_build_visual_brief_instructs_world_first_fullscreen_and_thumbnail_context():
    provider = _VisualBriefCaptureProvider()
    router = LLMRouter(providers={"fake": provider}, fallback_chain=["fake"])
    service = GenerationStrategyService(router)

    await service.build_visual_brief(
        {
            "name": "雾港",
            "genre": "悬疑",
            "era": "架空近代",
            "base_setting": "一座被海雾和旧工业阴影笼罩的沿海城市。",
        },
        [{"name": "顾巡", "personality": "寡言调查员"}],
        "旧港口城市视觉参考",
    )

    assert provider.messages is not None
    content = provider.messages[0]["content"]
    assert "游戏内世界详情页的大图展示" in content
    assert "世界列表、发现页、后台卡片等缩略展示" in content
    assert "世界图不要求必须出现人物" in content
    assert "不要设计固定姿势、手势、动作" in content
    assert provider.system is not None
    assert "优先确保世界主视觉准确传达世界背景和氛围" in provider.system
