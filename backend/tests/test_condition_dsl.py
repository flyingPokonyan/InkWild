import pytest

from engine.condition_dsl import (
    parse,
    evaluate,
    parse_and_evaluate,
    ConditionDSLParseError,
)


# ---- 词法 / 语法 PASS ----

@pytest.mark.parametrize("source", [
    "time_after('day_3')",
    "location_is('朝堂')",
    "player_did('与梅长苏密谈')",
    "world_state.靖王军功 >= 2",
    "world_state.tech == 5",
    "world_state.flag != 0",
    "time_after('day_3') AND location_is('朝堂')",
    "(time_after('day_2') OR time_after('day_5')) AND world_state.x > 0",
    "NOT location_is('密室')",
    "NOT (time_after('day_3') AND world_state.x == 1)",
])
def test_parse_valid_syntax(source):
    expr = parse(source)
    assert expr is not None


# ---- 语法 ERROR ----

@pytest.mark.parametrize("source", [
    "",
    "AND",
    "time_after",
    "time_after()",
    "time_after('day_3'",
    "time_after('day_3') OR",
    "time_after('day_3') AND AND",
    "world_state",
    "world_state.",
    "(time_after('day_3')",
    "time_after('day_3'))",
    "1 + 1",  # 算术不支持
])
def test_parse_invalid_syntax(source):
    with pytest.raises(ConditionDSLParseError):
        parse(source)


# ---- 安全 / 注入拒绝 ----

@pytest.mark.parametrize("source", [
    "eval('1+1')",
    "__import__('os')",
    "open('/etc/passwd')",
    "exec('1')",
    "system_command('rm')",
    "world_state.__class__",
    "world_state.x.__init__",
    "time_after('day_3'); print('hacked')",
    "time_after('day_3') OR true",  # true 不是合法 atom（必须是 comparison/func_call）
])
def test_parse_rejects_injection(source):
    with pytest.raises(ConditionDSLParseError):
        parse(source)


# Phase 10 (2026-05) — function-style AND(x,y)/OR(...)/NOT(x) canonicalization
# was removed when generators switched to producing structured condition_tree
# nodes upstream (see engine/condition_tree.py). The parser now only accepts
# the canonical infix form; function-style logic ops are a syntax error.


@pytest.mark.parametrize("source", [
    "AND(time_after('day_2'), location_is('雪落镇'))",
    "OR(time_after('day_1'), location_is('A'))",
])
def test_parse_rejects_function_style_logic_ops_post_phase10(source):
    """After Phase 10, function-style logic ops are no longer canonicalized.
    The parser surfaces a clear ConditionDSLParseError instead of silently
    rewriting — letting drift in upstream generators be diagnosed at the
    publish schema gate rather than masked here.

    Note: ``NOT(x)`` is intentionally NOT in this list — the grammar reads
    that as ``NOT (x)`` (prefix unary + paren group) which is valid.
    """
    with pytest.raises(ConditionDSLParseError):
        parse(source)


# ---- 字符串内单引号拒绝 ----

def test_string_with_single_quote_rejected():
    with pytest.raises(ConditionDSLParseError):
        parse("location_is('it''s')")


# ---- evaluate ----

def test_evaluate_time_after_true():
    state = {"current_time": "day_5_morning", "current_location": "", "player_actions": [], "world_state": {}}
    expr = parse("time_after('day_3')")
    assert evaluate(expr, state) is True


def test_evaluate_time_after_false():
    state = {"current_time": "day_2_evening", "current_location": "", "player_actions": [], "world_state": {}}
    expr = parse("time_after('day_3')")
    assert evaluate(expr, state) is False


def test_evaluate_location_is():
    state = {"current_time": "", "current_location": "朝堂", "player_actions": [], "world_state": {}}
    assert evaluate(parse("location_is('朝堂')"), state) is True
    assert evaluate(parse("location_is('密室')"), state) is False


def test_evaluate_player_did():
    state = {"current_time": "", "current_location": "", "player_actions": ["问候梅长苏", "查阅卷宗"], "world_state": {}}
    assert evaluate(parse("player_did('查阅卷宗')"), state) is True
    assert evaluate(parse("player_did('未做之事')"), state) is False


def test_evaluate_world_state_int():
    state = {"current_time": "", "current_location": "", "player_actions": [], "world_state": {"军功": 3}}
    assert evaluate(parse("world_state.军功 >= 2"), state) is True
    assert evaluate(parse("world_state.军功 == 3"), state) is True
    assert evaluate(parse("world_state.军功 < 3"), state) is False


def test_evaluate_world_state_missing_returns_false():
    """缺失字段不抛错，比较返回 False。"""
    state = {"current_time": "", "current_location": "", "player_actions": [], "world_state": {}}
    assert evaluate(parse("world_state.缺失 >= 1"), state) is False


def test_evaluate_and_or_not():
    state = {"current_time": "day_5_morning", "current_location": "朝堂", "player_actions": ["A"], "world_state": {"x": 5}}
    assert evaluate(parse("time_after('day_3') AND location_is('朝堂')"), state) is True
    assert evaluate(parse("time_after('day_3') AND location_is('密室')"), state) is False
    assert evaluate(parse("time_after('day_99') OR location_is('朝堂')"), state) is True
    assert evaluate(parse("NOT location_is('密室')"), state) is True
    assert evaluate(parse("NOT location_is('朝堂')"), state) is False


def test_evaluate_complex_expression():
    state = {"current_time": "day_5_morning", "current_location": "朝堂", "player_actions": ["问候"], "world_state": {"军功": 3}}
    src = "(time_after('day_3') AND world_state.军功 >= 2) AND NOT location_is('密室')"
    assert evaluate(parse(src), state) is True


def test_evaluate_supports_object_with_attrs():
    """game_state 也可以是对象（属性访问），不仅 dict。"""
    class FakeState:
        current_time = "day_5_morning"
        current_location = "朝堂"
        player_actions = []
        world_state = {"x": 1}

    state = FakeState()
    assert evaluate(parse("time_after('day_3') AND world_state.x == 1"), state) is True


def test_parse_and_evaluate_convenience():
    state = {"current_time": "day_5_morning", "current_location": "", "player_actions": [], "world_state": {}}
    assert parse_and_evaluate("time_after('day_3')", state) is True


# ---- Fuzzer ----

def test_fuzzer_random_garbage_never_eval_executes():
    """随机字符不应通过 parse；即使通过也 eval 不应抛错。"""
    import random
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789(){}[]<>=!&|+-*/.,;:'\"\\"
    random.seed(0)
    crashes = 0
    parsed = 0
    for _ in range(2000):
        length = random.randint(0, 40)
        garbage = "".join(random.choice(chars) for _ in range(length))
        try:
            expr = parse(garbage)
            parsed += 1
            evaluate(expr, {"current_time": "", "current_location": "", "player_actions": [], "world_state": {}})
        except ConditionDSLParseError:
            pass
        except Exception:
            crashes += 1
    assert crashes == 0, f"fuzzer crashed parser/evaluator {crashes} times"


# ---- time_after 边界 ----

def test_time_after_handles_non_day_format():
    """current_time 不是 day_N_X 格式 → 返回 False。"""
    state = {"current_time": "noon", "current_location": "", "player_actions": [], "world_state": {}}
    assert evaluate(parse("time_after('day_3')"), state) is False


def test_time_after_accepts_day_only():
    state = {"current_time": "day_5", "current_location": "", "player_actions": [], "world_state": {}}
    assert evaluate(parse("time_after('day_3')"), state) is True
