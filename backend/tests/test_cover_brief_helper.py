"""Tests for ``services.cover_brief_helper`` — focuses on fallback / merge
behavior since the LLM call itself is mocked.
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest

from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack
from services.cover_brief_helper import (
    derive_script_cover_helpers,
    derive_world_cover_brief,
)
from services.ip_recognizer import IPRecognition


class _FakeLLM:
    """Fake LLM router yielding a pre-canned text response."""

    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    async def stream_with_tools(
        self,
        messages,
        tools,
        system: str | None = None,
        max_tokens: int = 2048,
        **kwargs,
    ) -> AsyncIterator[dict]:
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        yield {"type": "text_delta", "text": self.text}


class _FailingLLM:
    """Fake LLM that raises — used to assert graceful fallback."""

    async def stream_with_tools(self, *args, **kwargs) -> AsyncIterator[dict]:  # noqa: ANN001
        raise RuntimeError("simulated LLM failure")
        yield  # unreachable; needed for async generator typing


def _ip_pack_zhuyu() -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name="逐玉",
        ip_type="tv",
        fidelity_mode="strict",
        summary="...",
        characters=[
            IPCharacter(
                name="谢征",
                role_in_story="男主",
                relation_to_protagonist="本人",
                traits=["武安侯"],
                must_have=True,
            ),
            IPCharacter(
                name="樊长玉",
                role_in_story="女主",
                relation_to_protagonist="本人",
                traits=["屠户"],
                must_have=True,
            ),
        ],
        places=[],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )


# ---------------------------------------------------------------------------
# derive_world_cover_brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_world_cover_brief_known_ip_uses_ref_anchor():
    llm = _FakeLLM("""{
        "world_name_english": "Pursuit of Jade",
        "mood": "毛笔书法、朱印、墨色、暗金",
        "characters": {
            "谢征": {"name_english": "Xie Zheng", "mood_anchor": "隐忍深沉"},
            "樊长玉": {"name_english": "Fan Changyu", "mood_anchor": "干净利落带刀气"}
        }
    }""")
    rec = IPRecognition(kind="known_ip", confidence=0.95, ip_name="逐玉")

    world_brief, char_briefs = await derive_world_cover_brief(
        world_data={"name": "逐玉", "genre": "古装权谋爱情", "era": ""},
        characters=[
            {"name": "谢征", "is_image_target": True},
            {"name": "樊长玉", "is_image_target": True},
            {"name": "群众甲", "is_image_target": False},  # filtered out
        ],
        recognition=rec,
        ip_pack=_ip_pack_zhuyu(),
        llm=llm,
    )

    # V3: world_name == recognition.ip_name → ip_name preserved, no ip_mode field
    assert world_brief.ip_name == "逐玉"
    assert world_brief.world_name_english == "Pursuit of Jade"
    # mood is LLM-derived (no static typography table anymore)
    assert "毛笔书法" in world_brief.mood
    assert "朱印" in world_brief.mood

    # Only image_target chars produce briefs
    assert set(char_briefs.keys()) == {"谢征", "樊长玉"}

    # Both characters get reference_anchor (mechanical, from IP pack)
    assert char_briefs["谢征"].reference_anchor == "《逐玉》里的男主"
    assert char_briefs["樊长玉"].reference_anchor == "《逐玉》里的女主"

    # Mood from helper LLM
    assert char_briefs["谢征"].mood_anchor == "隐忍深沉"
    assert char_briefs["樊长玉"].mood_anchor == "干净利落带刀气"

    # 4-dim fields stay empty when ref is set
    assert char_briefs["谢征"].gender == ""
    assert char_briefs["谢征"].age_band == ""


@pytest.mark.asyncio
async def test_world_cover_brief_original_uses_4dim_fallback():
    llm = _FakeLLM("""{
        "world_name_english": "The Forgotten Winter",
        "mood": "民国铅字、暗红、灯影、烟雾",
        "characters": {
            "李婉": {
                "name_english": "Li Wan",
                "mood_anchor": "惊魂未定",
                "gender": "女",
                "age_band": "少女",
                "role_class": "药铺女儿"
            }
        }
    }""")

    world_brief, char_briefs = await derive_world_cover_brief(
        world_data={"name": "无人记得的冬", "genre": "悬疑", "era": "民国"},
        characters=[{"name": "李婉", "is_image_target": True}],
        recognition=None,
        ip_pack=None,
        llm=llm,
    )

    # Original world: no IP recognition → ip_name None
    assert world_brief.ip_name is None
    # mood is LLM-derived (no static genre/era mapping table)
    assert "民国铅字" in world_brief.mood

    li_wan = char_briefs["李婉"]
    assert li_wan.reference_anchor is None
    assert li_wan.gender == "女"
    assert li_wan.age_band == "少女"
    assert li_wan.role_class == "药铺女儿"
    assert li_wan.mood_anchor == "惊魂未定"


@pytest.mark.asyncio
async def test_world_cover_brief_low_confidence_drops_ip_name():
    """Below the 0.6 confidence floor, ip_name is dropped (don't feed bad guesses)."""
    llm = _FakeLLM('{"world_name_english": "X", "mood": "m", "characters": {}}')
    rec = IPRecognition(kind="known_ip", confidence=0.3, ip_name="某 IP")
    world_brief, _ = await derive_world_cover_brief(
        world_data={"name": "某世界", "genre": "X", "era": ""},
        characters=[],
        recognition=rec,
        ip_pack=None,
        llm=llm,
    )
    assert world_brief.ip_name is None


@pytest.mark.asyncio
async def test_world_cover_brief_seed_gender_overrides_llm_gender():
    """Admin-set gender on the WorldCharacter row is authoritative."""
    llm = _FakeLLM("""{
        "world_name_english": "X",
        "characters": {
            "Chris": {"name_english": "Chris", "mood_anchor": "...", "gender": "男"}
        }
    }""")

    _, char_briefs = await derive_world_cover_brief(
        world_data={"name": "X", "genre": "现代", "era": ""},
        characters=[{"name": "Chris", "is_image_target": True, "gender": "女"}],
        recognition=None,
        ip_pack=None,
        llm=llm,
    )
    assert char_briefs["Chris"].gender == "女"


@pytest.mark.asyncio
async def test_world_cover_brief_handles_llm_failure_gracefully():
    """When the LLM fails, return briefs with empty english + empty fallback fields."""
    world_brief, char_briefs = await derive_world_cover_brief(
        world_data={"name": "X", "genre": "悬疑", "era": ""},
        characters=[{"name": "李婉", "is_image_target": True, "gender": "女"}],
        recognition=None,
        ip_pack=None,
        llm=_FailingLLM(),
    )
    assert world_brief.world_name_english == ""
    li_wan = char_briefs["李婉"]
    assert li_wan.name_english == ""
    assert li_wan.mood_anchor == ""
    # Seed gender still flows through
    assert li_wan.gender == "女"


@pytest.mark.asyncio
async def test_world_cover_brief_handles_malformed_json():
    llm = _FakeLLM("not json at all")
    world_brief, _ = await derive_world_cover_brief(
        world_data={"name": "X", "genre": "悬疑", "era": ""},
        characters=[],
        recognition=None,
        ip_pack=None,
        llm=llm,
    )
    assert world_brief.world_name_english == ""


# ---------------------------------------------------------------------------
# derive_script_cover_helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_cover_helpers():
    llm = _FakeLLM("""{
        "script_title_english": "The Bridge Case",
        "endings": {
            "真相大白": {"title_english": "Truth Revealed"},
            "不了了之": {"title_english": "Unsolved"}
        }
    }""")

    title_en, endings = await derive_script_cover_helpers(
        script_data={"name": "桥下旧案", "description": "..."},
        endings=[
            {"title": "真相大白", "description": "案件水落石出"},
            {"title": "不了了之", "description": "案件成为悬案"},
        ],
        llm=llm,
    )
    assert title_en == "The Bridge Case"
    assert endings["真相大白"].title_english == "Truth Revealed"
    assert endings["真相大白"].description == "案件水落石出"
    assert endings["不了了之"].title_english == "Unsolved"


@pytest.mark.asyncio
async def test_script_cover_helpers_handles_missing_endings_in_llm_response():
    llm = _FakeLLM("""{"script_title_english": "X", "endings": {}}""")
    _, endings = await derive_script_cover_helpers(
        script_data={"name": "X", "description": ""},
        endings=[{"title": "结局A", "description": "..."}],
        llm=llm,
    )
    # Ending still produced with empty title_english
    assert endings["结局A"].title_english == ""
    assert endings["结局A"].description == "..."
