from schemas.generation_strategy import VisualBrief
from services.generation_prompt_builder import GenerationPromptBuilder


def _visual_brief() -> VisualBrief:
    return VisualBrief(
        cover_subject="雨夜中的港口城",
        mood="moody, mysterious",
        palette="cold blue, dim amber",
        composition="layered cinematic composition",
        camera_language="wide lens, low-angle atmosphere",
        style_tags=["cinematic", "atmospheric"],
        negative_tags=["text", "watermark"],
        consistency_notes="keep the architecture and wardrobe grounded in the setting",
    )


def test_build_hero_prompt_targets_world_detail_fullscreen_use():
    builder = GenerationPromptBuilder()

    prompt = builder.build_hero_prompt(
        {
            "name": "雾港",
            "description": "一座被海雾和旧工业阴影笼罩的沿海城市。",
            "genre": "悬疑",
            "era": "架空近代",
            "locations": [{"name": "旧码头"}, {"name": "潮汐街"}],
        },
        _visual_brief(),
    )

    assert "world detail page" in prompt
    assert "100% viewport hero background" in prompt
    assert "characters are optional" in prompt
    assert "avoid staged poses" in prompt
    assert "16:9 composition" in prompt


def test_build_poster_prompt_targets_list_thumbnail_use_and_world_setting_first():
    builder = GenerationPromptBuilder()

    prompt = builder.build_poster_prompt(
        {
            "name": "雾港",
            "description": "一座被海雾和旧工业阴影笼罩的沿海城市。",
            "genre": "悬疑",
            "era": "架空近代",
            "locations": [{"name": "旧码头"}, {"name": "潮汐街"}],
        },
        characters=[{"name": "顾巡", "personality": "寡言调查员"}],
        playable_data=[{"name": "顾巡"}],
        hook_map={"顾巡": {"appearance": "lean silhouette", "costume": "weathered trench coat", "mood": "watchful"}},
        visual_brief=_visual_brief(),
    )

    assert "world lists, discovery cards, and admin thumbnails" in prompt
    assert "world-setting-first composition" in prompt
    assert "readable at thumbnail size" in prompt
    assert "characters are optional" in prompt
    assert "avoid mandatory handheld props" in prompt
    assert "focal characters:" not in prompt

