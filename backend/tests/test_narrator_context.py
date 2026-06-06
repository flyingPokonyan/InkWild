from engine.narrator_context import filter_recent_messages_for_narrator


def test_keeps_user_messages_verbatim():
    msgs = [
        {"role": "user", "content": "走到工棚"},
        {"role": "user", "content": "细看尸格"},
    ]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_drops_env_only_assistant_messages():
    env_only = "公廨里晨光斜斜落在青砖上，案上烛火摇了一下。"
    msgs = [
        {"role": "user", "content": "走过去"},
        {"role": "assistant", "content": env_only},
        {"role": "user", "content": "继续看"},
    ]
    out = filter_recent_messages_for_narrator(msgs)
    assert {"role": "user", "content": "走过去"} in out
    assert {"role": "user", "content": "继续看"} in out
    assert not any(m["content"] == env_only for m in out)


def test_keeps_assistant_messages_with_chinese_quotes():
    msg_with_dia = "狄仁杰开口：「明远所言甚是。」案上烛火摇了一下。"
    msgs = [{"role": "assistant", "content": msg_with_dia}]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_keeps_assistant_messages_with_straight_quotes():
    msg_with_dia = '李元芳沉声道："属下从工地回来。"'
    msgs = [{"role": "assistant", "content": msg_with_dia}]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_keeps_assistant_messages_with_curly_quotes():
    msg_with_dia = "他冷笑：“你以为我会信？”"
    msgs = [{"role": "assistant", "content": msg_with_dia}]
    assert filter_recent_messages_for_narrator(msgs) == msgs


def test_preserves_chronology():
    msgs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "纯环境段"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "狄公说：「话」"},
    ]
    out = filter_recent_messages_for_narrator(msgs)
    contents = [m["content"] for m in out]
    assert contents == ["u1", "u2", "狄公说：「话」"]


def test_handles_empty_input():
    assert filter_recent_messages_for_narrator([]) == []


def test_keeps_system_role_unchanged():
    msgs = [{"role": "system", "content": "x"}]
    assert filter_recent_messages_for_narrator(msgs) == msgs
