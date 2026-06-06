from engine.prompts import (
    DIRECTOR_TOOL,
    RECALL_MEMORY_TOOL,
    build_director_system,
    build_director_system_v2,
    build_director_tool,
    build_narrator_system,
    build_npc_system,
    format_ending_menu,
)


def _build_v2(**kw):
    base = dict(
        base_setting="一个测试世界",
        script_setting="",
        npc_descriptions="（无）",
        ending_conditions="",
        game_mode="free",
    )
    base.update(kw)
    return build_director_system_v2(**base)


def test_ending_menu_instructs_per_turn_adjudication_and_honors_decisive_intent():
    endings = [
        {"ending_type": "perfect", "title": "真相大白", "soft_conditions": "玩家正确指认凶手"},
        {"ending_type": "good", "title": "部分真相", "soft_conditions": "线索不全但方向对"},
    ]
    menu = format_ending_menu(endings)
    # 主动裁决是每回合固定职责，不是被动等条件
    assert "每一回合" in menu or "每回合" in menu
    # honor 玩家明确收束动作（最终指认 / 下结论 / 了断）
    assert "收束" in menu
    # 护栏仍在：没满足任何条件不凭空触发
    assert "没满足" in menu or "凭空" in menu
    # 合法 ending_type 清单仍然渲染
    assert "perfect" in menu and "good" in menu


def test_ending_menu_empty_without_usable_endings():
    assert format_ending_menu([]) == ""
    assert format_ending_menu(None) == ""


def test_director_tool_has_required_fields():
    assert DIRECTOR_TOOL["name"] == "director_decision"
    props = DIRECTOR_TOOL["input_schema"]["properties"]
    assert {
        "involved_npcs",
        "npc_instructions",
        "scene_direction",
        "state_updates",
        "quick_actions",
        "ending_triggered",
        "memory_extracts",
    }.issubset(props)


def test_director_tool_uses_case_board_ops_for_script_mode():
    tool = build_director_tool(script_type="mystery", game_mode="script")
    props = tool["input_schema"]["properties"]

    assert "case_board_ops" in props
    assert "case_board" not in props
    assert {"set_field", "upsert_list_item", "remove_list_item"} == set(
        props["case_board_ops"]["items"]["properties"]["op_type"]["enum"]
    )


def test_director_system_includes_script_mode_context():
    prompt = build_director_system(
        base_setting="雾隐镇是一个民国小镇。",
        script_setting="凶手是管家王福。",
        npc_descriptions="管家王福：表面忠厚。",
        ending_conditions="当玩家指认凶手时触发完美结局。",
        game_mode="script",
        memory_context="玩家刚和茶摊老板聊过天。",
    )

    assert "雾隐镇是一个民国小镇。" in prompt
    assert "凶手是管家王福。" in prompt
    assert "管家王福：表面忠厚。" in prompt
    assert "当玩家指认凶手时触发完美结局。" in prompt
    assert "玩家刚和茶摊老板聊过天。" in prompt


def test_director_system_omits_script_secret_in_free_mode():
    prompt = build_director_system(
        base_setting="雾隐镇是一个民国小镇。",
        script_setting="凶手是管家王福。",
        npc_descriptions="管家王福：表面忠厚。",
        ending_conditions="",
        game_mode="free",
    )

    assert "雾隐镇是一个民国小镇。" in prompt
    assert "管家王福：表面忠厚。" in prompt
    assert "凶手是管家王福。" not in prompt


def test_npc_system_includes_name_personality_secret_instruction():
    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret="他知道遗嘱被改过。",
        instruction="试探玩家的来意。",
    )

    assert "王福" in prompt
    assert "忠厚寡言" in prompt
    assert "他知道遗嘱被改过。" in prompt
    assert "试探玩家的来意。" in prompt


def test_narrator_system_includes_author_note_when_provided():
    prompt = build_narrator_system(authors_note="保持悬疑感，不要一次揭穿真相。")

    assert "Author's Note" in prompt
    assert "保持悬疑感，不要一次揭穿真相。" in prompt


def test_narrator_system_omits_author_note_when_not_provided():
    prompt = build_narrator_system()

    assert "Author's Note" not in prompt


def test_recall_memory_tool_schema():
    assert RECALL_MEMORY_TOOL["name"] == "recall_memory"
    assert "keyword" in RECALL_MEMORY_TOOL["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# Phase 1.B.5 — typed player_action surface
# ---------------------------------------------------------------------------


def test_director_tool_includes_player_action_schema():
    """Director must declare the typed player_action field so the LLM produces
    a structured categorization the orchestrator can persist."""
    from engine.prompts import DIRECTOR_TOOL

    props = DIRECTOR_TOOL["input_schema"]["properties"]
    assert "player_action" in props
    schema = props["player_action"]
    assert schema["type"] == "object"
    assert "action_type" in schema["properties"]
    assert "summary" in schema["properties"]
    enum = schema["properties"]["action_type"]["enum"]
    for required_kind in (
        "visit_location",
        "ask_about",
        "tell_npc",
        "give_item",
        "examine",
        "confront",
        "wait",
        "other",
    ):
        assert required_kind in enum


def test_npc_system_renders_recent_player_actions_section():
    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="敷衍。",
        recent_player_actions=[
            {
                "round": 5,
                "action_type": "ask_about",
                "target_npc": "王福",
                "target": "遗嘱",
                "summary": "玩家追问遗嘱",
            },
            {
                "round": 6,
                "action_type": "confront",
                "target_npc": "王福",
                "summary": "玩家当面质问王福",
            },
        ],
    )

    assert "玩家最近做过的事" in prompt
    assert "玩家追问遗嘱" in prompt
    assert "玩家当面质问王福" in prompt
    # Header should carry the round + typed labels for cross-turn anchoring.
    assert "[第5轮]" in prompt
    assert "ask_about" in prompt
    assert "confront" in prompt


def test_npc_system_skips_player_actions_section_when_empty():
    prompt = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="敷衍。",
        recent_player_actions=[],
    )

    assert "玩家最近做过的事" not in prompt


# ---------------------------------------------------------------------------
# S1 — Director proactively steers lost players (spec §5)
# ---------------------------------------------------------------------------


def test_v2_prompt_grants_steering_on_weak_input():
    prompt = _build_v2(player_input_weak=True)
    # The new steering directive lands (unique phrase, not pre-existing words):
    # the Director should push the WORLD (a stimulus) to re-surface the crux.
    assert "推世界" in prompt
    # Guardrail retained: must not script the player's actions.
    assert "替玩家" in prompt


def test_v2_steering_gated_to_weak_input():
    # The steering directive is part of the weak-input block; it must NOT
    # appear when the player gave a strong/normal input.
    assert "推世界" not in _build_v2(player_input_weak=False)


# ---------------------------------------------------------------------------
# Structural block — reaction-setup kept, flag added, judgment removed
# (spec 2026-06-03 redesign)
# ---------------------------------------------------------------------------


def test_v2_prompt_keeps_structural_reaction_setup():
    prompt = _build_v2()
    # World only changes through its own logic; bare assertions get NPC reaction
    # / environmental non-recognition (S2 reaction-setup retained).
    assert "世界底色" in prompt
    assert "不予承认" in prompt  # environmental non-recognition for no-actor scenes


def test_v2_prompt_instructs_structural_in_play_flag_not_judgment():
    prompt = _build_v2()
    # The Director sets the cheap flag; it does NOT judge legitimacy.
    assert "structural_in_play" in prompt
    # The old judgment vocabulary is gone.
    assert "supported" not in prompt
    assert "world_reaction" not in prompt
