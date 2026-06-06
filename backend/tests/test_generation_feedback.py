from services.generation_feedback import progress_event, warning_event


def test_progress_event_renders_template():
    event = progress_event("research", "reference_doc_ready", stage_label="事件链", char_count=824)

    assert event["type"] == "progress"
    assert event["phase"] == "research"
    assert event["code"] == "reference_doc_ready"
    assert "824" in event["message"]
    assert event["meta"]["char_count"] == 824


def test_warning_event_falls_back_to_meta_message():
    event = warning_event("images", "generation_failed", message="插画生成失败")

    assert event["type"] == "warning"
    assert event["message"] == "插画生成失败"


def test_images_progress_mentions_world_hero_and_poster_outputs():
    event = progress_event("images", "completed", image_count=5)

    assert event["type"] == "progress"
    assert "世界详情大图" in event["message"]
    assert "列表图" in event["message"]
    assert "5" in event["message"]


def test_boot_progress_uses_friendlier_copy():
    event = progress_event("boot", "session_started")

    assert event["type"] == "progress"
    assert "建立创作会话" in event["message"]


def test_script_drafting_pulse_uses_progressive_copy():
    event = progress_event("script_base", "drafting_pulse")

    assert event["type"] == "progress"
    assert "主线" in event["message"]


def test_pulse_templates_registered_for_long_single_llm_stages():
    """Five long single-LLM stages must have a pulse template so the headline renders text."""
    for phase in (
        "research_pack",
        "lore_dimensions",
        "character_roster",
        "shared_events",
        "visual_brief",
    ):
        event = progress_event(phase, "pulse")
        assert event["type"] == "progress"
        assert event["code"] == "pulse"
        assert event["message"], f"{phase}.pulse should have a non-empty message"
