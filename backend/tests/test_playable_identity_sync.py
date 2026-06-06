"""Phase 4 tests: playable identity ↔ base_setting cross-reference."""
from services.world_creator_agent_v2 import _validate_player_identity_in_setting


def test_setting_references_known_playable_name():
    base_setting = "你叫林怀瑾，是工作室的核心剪辑师。"
    assert _validate_player_identity_in_setting(base_setting, ["林怀瑾", "苏婉"]) == []


def test_setting_references_unknown_name_returns_issue():
    base_setting = "你叫张三，是工作室的实习生。"
    issues = _validate_player_identity_in_setting(base_setting, ["林怀瑾", "苏婉"])
    assert any("张三" in i for i in issues)


def test_setting_with_no_player_reference_passes():
    """If base_setting does not address the player by name, no constraint applies."""
    base_setting = "工作室位于上海陆家嘴某幢甲级写字楼的 32 层。"
    assert _validate_player_identity_in_setting(base_setting, ["林怀瑾"]) == []


def test_setting_with_multiple_player_refs_all_must_be_known():
    base_setting = "你叫林怀瑾。在某些路径下，你也可以扮演苏婉。"
    # 第二个引用不在列表里时应该报告
    issues = _validate_player_identity_in_setting(base_setting, ["林怀瑾"])
    # The regex matches both `你叫林怀瑾` and `扮演苏婉`? No — regex only matches `你叫X`.
    # Make sure ONLY `你叫X` patterns trigger.
    assert issues == []


def test_setting_with_two_explicit_player_refs():
    base_setting = "你叫林怀瑾。在另一支线里，你叫苏婉。"
    issues = _validate_player_identity_in_setting(base_setting, ["林怀瑾"])
    # The unknown name `苏婉` should produce exactly one issue;
    # the known `林怀瑾` should not produce an issue of its own.
    unknown_issues = [i for i in issues if "references player name '苏婉'" in i]
    known_issues = [i for i in issues if "references player name '林怀瑾'" in i]
    assert len(unknown_issues) == 1
    assert len(known_issues) == 0


def test_empty_base_setting_returns_no_issue():
    assert _validate_player_identity_in_setting("", ["林怀瑾"]) == []


def test_pinyin_or_latin_name_accepted_in_regex():
    base_setting = "你叫Alex，工作室的实习生。"
    issues_known = _validate_player_identity_in_setting(base_setting, ["Alex"])
    assert issues_known == []
    issues_unknown = _validate_player_identity_in_setting(base_setting, ["林怀瑾"])
    assert any("Alex" in i for i in issues_unknown)
