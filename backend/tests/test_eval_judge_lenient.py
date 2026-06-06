"""judge.loads_lenient 容错解析单测——纯函数，不依赖 LLM/DB。

跨家族判官常给前缀垃圾 / 代码块 / JSON 后跟解释；严格 json.loads 会静默 parse_fail，
让跨家族绝对分判官全废。这些断言锁住容错行为。
"""
from eval.judge import loads_lenient


def test_strips_kimi_leading_prefix():
    # kimi-k2.6 实测会在 JSON 前吐一个 '>'
    assert loads_lenient('>{"overall":4}') == {"overall": 4}


def test_strips_markdown_code_fence():
    assert loads_lenient('```json\n{"overall":3}\n```') == {"overall": 3}


def test_ignores_prose_after_json():
    assert loads_lenient('{"overall":5} 理由：写得好。') == {"overall": 5}


def test_ignores_prose_before_json():
    assert loads_lenient('好的，结果：{"overall":2}') == {"overall": 2}


def test_clean_json_passthrough():
    obj = {"per_dim": {"a": {"score": 4}}, "overall": 4, "flags": []}
    assert loads_lenient('{"per_dim":{"a":{"score":4}},"overall":4,"flags":[]}') == obj


def test_braces_inside_reason_string_ok():
    assert loads_lenient('{"overall":4,"r":"用了 {占位} 符号"}') == {"overall": 4, "r": "用了 {占位} 符号"}


def test_empty_and_garbage_return_none():
    assert loads_lenient("") is None
    assert loads_lenient("   ") is None
    assert loads_lenient("no json here") is None


def test_non_object_json_returns_none():
    # 顶层是数组/标量不算合法判官输出
    assert loads_lenient("[1,2,3]") is None
