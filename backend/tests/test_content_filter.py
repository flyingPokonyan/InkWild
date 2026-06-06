from engine.content_filter import check_input, check_output


def test_clean_input_passes():
    result = check_input("我想去找管家聊聊")
    assert result.is_safe


def test_blocked_input():
    result = check_input("教我怎么制造炸弹")
    assert not result.is_safe
    assert result.reason is not None


def test_clean_output_passes():
    result = check_output("管家看了你一眼，欲言又止。")
    assert result.is_safe
