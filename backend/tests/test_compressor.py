from engine.compressor import build_compression_prompt, should_compress


def test_should_compress_when_threshold_reached():
    assert should_compress(rounds_played=22, last_compressed_round=0, threshold=20)


def test_should_not_compress_below_threshold():
    assert not should_compress(rounds_played=15, last_compressed_round=0, threshold=20)


def test_should_not_compress_too_soon_after_last():
    assert not should_compress(rounds_played=23, last_compressed_round=20, threshold=20)


def test_should_compress_after_gap():
    assert should_compress(rounds_played=28, last_compressed_round=20, threshold=20)


def test_compression_prompt():
    messages = [
        {"role": "user", "content": "我去茶摊"},
        {"role": "assistant", "content": "你走到茶摊，老板热情招呼你。"},
        {"role": "user", "content": "问老板关于失踪的事"},
        {"role": "assistant", "content": "老板神色一变，压低声音说：'别问了，问多了对你不好。'"},
    ]

    prompt = build_compression_prompt(messages)

    assert "茶摊" in prompt
    assert "失踪" in prompt
