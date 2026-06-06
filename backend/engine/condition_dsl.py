"""condition_dsl — events_data trigger 条件的安全 mini-parser。

支持白名单 ops（AND/OR/NOT/比较）+ 3 个白名单函数（time_after / location_is / player_did）+
world_state.<key> 字段引用 + 整数 / 单引号字符串字面量。

不允许任何其他函数 / 表达式 / 字符串转义 —— 防注入。

文法（递归下降）：
    expr     := or_expr
    or_expr  := and_expr ( OR and_expr )*
    and_expr := not_expr ( AND not_expr )*
    not_expr := NOT not_expr | atom
    atom     := "(" expr ")" | func_call | comparison
    func_call  := IDENT "(" STRING ")"        # 仅白名单函数
    comparison := operand op operand
    operand    := func_call | field_ref | INT  # field_ref = "world_state" "." IDENT
    op         := > | >= | < | <= | == | !=
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class ConditionDSLParseError(ValueError):
    """Raised on any lexical or syntactic error in a condition DSL string."""


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


@dataclass
class _Expr:
    """Base class for all AST nodes."""


@dataclass
class _BinOp(_Expr):
    """AND / OR node."""
    op: str          # "AND" | "OR"
    left: _Expr
    right: _Expr


@dataclass
class _Not(_Expr):
    """NOT node."""
    inner: _Expr


@dataclass
class _Compare(_Expr):
    """Comparison node: left op right."""
    op: str          # ">", ">=", "<", "<=", "==", "!="
    left: _Expr
    right: _Expr


@dataclass
class _FuncCall(_Expr):
    """A whitelisted function call with a single string literal arg."""
    name: str        # "time_after" | "location_is" | "player_did"
    arg: str         # the string literal value (without quotes)


@dataclass
class _FieldRef(_Expr):
    """world_state.<key> reference."""
    key: str         # the part after "world_state."


@dataclass
class _IntLit(_Expr):
    """Integer literal."""
    value: int


@dataclass
class _StrLit(_Expr):
    """String literal (single-quoted in DSL form)."""
    value: str


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Token types (string constants for clarity)
_TK_AND = "AND"
_TK_OR = "OR"
_TK_NOT = "NOT"
_TK_GE = ">="
_TK_LE = "<="
_TK_EQ = "=="
_TK_NEQ = "!="
_TK_GT = ">"
_TK_LT = "<"
_TK_LP = "("
_TK_RP = ")"
_TK_DOT = "."
_TK_INT = "INT"
_TK_STRING = "STRING"
_TK_IDENT = "IDENT"
_TK_EOF = "EOF"

# Named groups in order of priority.  Multi-char operators MUST come before
# their single-char prefixes (>= before >, <= before <, == before =).
# IDENT pattern supports ASCII identifiers + CJK Unified Ideographs (一-鿿).
_TOKEN_RE = re.compile(
    r"(?P<SKIP>\s+)"
    r"|(?P<AND>(?i:AND)(?![A-Za-z_0-9一-鿿]))"
    r"|(?P<OR>(?i:OR)(?![A-Za-z_0-9一-鿿]))"
    r"|(?P<NOT>(?i:NOT)(?![A-Za-z_0-9一-鿿]))"
    r"|(?P<GE>>=)"
    r"|(?P<LE><=)"
    r"|(?P<EQ>==)"
    r"|(?P<NEQ>!=)"
    r"|(?P<GT>>)"
    r"|(?P<LT><)"
    r"|(?P<LP>\()"
    r"|(?P<RP>\))"
    r"|(?P<DOT>\.)"
    r"|(?P<INT>-?\d+)"
    r"|(?P<STRING>'[^']*')"
    r"|(?P<IDENT>[A-Za-z_一-鿿][A-Za-z_0-9一-鿿]*)"
)

# Whitelisted functions
_ALLOWED_FUNCTIONS: frozenset[str] = frozenset({"time_after", "location_is", "player_did"})

# Comparison operators
_CMP_OPS: frozenset[str] = frozenset({">", ">=", "<", "<=", "==", "!="})


def _tokenize(source: str) -> list[tuple[str, str]]:
    """Tokenize *source* into a list of (token_type, token_value) pairs.

    Raises ConditionDSLParseError if any character cannot be matched.
    """
    tokens: list[tuple[str, str]] = []
    pos = 0
    length = len(source)

    while pos < length:
        m = _TOKEN_RE.match(source, pos)
        if m is None:
            raise ConditionDSLParseError(
                f"Unexpected character {source[pos]!r} at position {pos}"
            )
        kind = m.lastgroup
        value = m.group()
        pos = m.end()

        if kind == "SKIP":
            continue  # discard whitespace
        elif kind in ("AND", "OR", "NOT"):
            tokens.append((kind, kind.upper()))
        elif kind == "GE":
            tokens.append((_TK_GE, ">="))
        elif kind == "LE":
            tokens.append((_TK_LE, "<="))
        elif kind == "EQ":
            tokens.append((_TK_EQ, "=="))
        elif kind == "NEQ":
            tokens.append((_TK_NEQ, "!="))
        elif kind == "GT":
            tokens.append((_TK_GT, ">"))
        elif kind == "LT":
            tokens.append((_TK_LT, "<"))
        elif kind == "LP":
            tokens.append((_TK_LP, "("))
        elif kind == "RP":
            tokens.append((_TK_RP, ")"))
        elif kind == "DOT":
            tokens.append((_TK_DOT, "."))
        elif kind == "INT":
            tokens.append((_TK_INT, value))
        elif kind == "STRING":
            # Strip surrounding single quotes; reject embedded quotes (already
            # blocked by regex '[^']*' but guard defensively).
            inner = value[1:-1]
            if "'" in inner:
                raise ConditionDSLParseError(
                    "Single quotes not allowed inside string literals"
                )
            tokens.append((_TK_STRING, inner))
        elif kind == "IDENT":
            tokens.append((_TK_IDENT, value))
        else:
            raise ConditionDSLParseError(
                f"Unrecognized token kind {kind!r} at position {pos}"
            )

    tokens.append((_TK_EOF, ""))
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------


class _Parser:
    """Recursive-descent parser for the condition DSL."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self._tokens = tokens
        self._pos = 0

    # -- Helpers --

    def _peek(self) -> tuple[str, str]:
        return self._tokens[self._pos]

    def _peek_type(self) -> str:
        return self._tokens[self._pos][0]

    def _consume(self) -> tuple[str, str]:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str) -> tuple[str, str]:
        tok = self._consume()
        if tok[0] != kind:
            raise ConditionDSLParseError(
                f"Expected {kind!r} but got {tok[0]!r} ({tok[1]!r})"
            )
        return tok

    def _at_end(self) -> bool:
        return self._peek_type() == _TK_EOF

    # -- Grammar rules --

    def parse_expr(self) -> _Expr:
        return self._parse_or()

    def _parse_or(self) -> _Expr:
        left = self._parse_and()
        while self._peek_type() == _TK_OR:
            self._consume()  # eat OR
            right = self._parse_and()
            left = _BinOp("OR", left, right)
        return left

    def _parse_and(self) -> _Expr:
        left = self._parse_not()
        while self._peek_type() == _TK_AND:
            self._consume()  # eat AND
            right = self._parse_not()
            left = _BinOp("AND", left, right)
        return left

    def _parse_not(self) -> _Expr:
        if self._peek_type() == _TK_NOT:
            self._consume()  # eat NOT
            inner = self._parse_not()
            return _Not(inner)
        return self._parse_atom()

    def _parse_atom(self) -> _Expr:
        kind, value = self._peek()

        if kind == _TK_LP:
            self._consume()  # eat (
            expr = self.parse_expr()
            self._expect(_TK_RP)
            return expr

        if kind == _TK_IDENT:
            # Could be: func_call  or  world_state.<key> comparison
            return self._parse_ident_led()

        if kind == _TK_INT:
            # bare INT as left operand of comparison
            return self._parse_comparison_with_left(self._parse_operand())

        raise ConditionDSLParseError(
            f"Unexpected token {kind!r} ({value!r}); expected func call, "
            f"world_state ref, integer, or '('"
        )

    def _parse_ident_led(self) -> _Expr:
        """Handle an IDENT token: either a func call or world_state.<key> comparison."""
        _, name = self._consume()  # eat IDENT

        # world_state.<key> — must be followed by DOT
        if name == "world_state":
            self._expect(_TK_DOT)
            _, key = self._expect(_TK_IDENT)
            # key must not start with dunder (security: block __class__ etc.)
            if key.startswith("__") or key.endswith("__"):
                raise ConditionDSLParseError(
                    f"Illegal field reference: world_state.{key!r} (dunder not allowed)"
                )
            # After a field ref we MUST see a comparison operator
            if self._peek_type() not in _CMP_OPS:
                raise ConditionDSLParseError(
                    f"Expected comparison operator after world_state.{key!r}, "
                    f"got {self._peek_type()!r}"
                )
            field_ref = _FieldRef(key)
            return self._parse_comparison_with_left(field_ref)

        # function call — name must be in whitelist
        if name not in _ALLOWED_FUNCTIONS:
            raise ConditionDSLParseError(
                f"Unknown function {name!r}; allowed functions: "
                f"{sorted(_ALLOWED_FUNCTIONS)}"
            )
        self._expect(_TK_LP)
        _, arg_str = self._expect(_TK_STRING)  # arg must be string literal
        self._expect(_TK_RP)
        func_node = _FuncCall(name, arg_str)

        # A func_call may be the left operand of a comparison (rare but legal per grammar)
        if self._peek_type() in _CMP_OPS:
            return self._parse_comparison_with_left(func_node)
        return func_node

    def _parse_operand(self) -> _Expr:
        """Parse operand: func_call | field_ref | INT | STRING."""
        kind, value = self._peek()

        if kind == _TK_INT:
            self._consume()
            return _IntLit(int(value))

        if kind == _TK_STRING:
            self._consume()
            return _StrLit(value)

        if kind == _TK_IDENT:
            _, name = self._consume()
            if name == "world_state":
                self._expect(_TK_DOT)
                _, key = self._expect(_TK_IDENT)
                if key.startswith("__") or key.endswith("__"):
                    raise ConditionDSLParseError(
                        f"Illegal field reference: world_state.{key!r}"
                    )
                return _FieldRef(key)
            if name not in _ALLOWED_FUNCTIONS:
                raise ConditionDSLParseError(
                    f"Unknown function {name!r} in operand position"
                )
            self._expect(_TK_LP)
            _, arg_str = self._expect(_TK_STRING)
            self._expect(_TK_RP)
            return _FuncCall(name, arg_str)

        raise ConditionDSLParseError(
            f"Expected operand (int, world_state ref, or func call), got {kind!r}"
        )

    def _parse_comparison_with_left(self, left: _Expr) -> _Compare:
        """Consume op + right operand to build a _Compare node."""
        op_kind, _ = self._peek()
        if op_kind not in _CMP_OPS:
            raise ConditionDSLParseError(
                f"Expected comparison operator, got {op_kind!r}"
            )
        self._consume()
        right = self._parse_operand()
        return _Compare(op_kind, left, right)


# ---------------------------------------------------------------------------
# Public parse() entry-point
# ---------------------------------------------------------------------------


# Phase 10 (2026-05) — the previous ``AND(x, y)`` → ``(x AND y)`` canonicalizer
# and ``world_state.x`` bare-flag normalizer have been deleted. Generators now
# emit a structured ``condition_tree`` (see engine/condition_tree.py) and
# serialize to canonical DSL at the events_data_builder boundary; the parser
# itself only ever sees well-formed input. Any drift from new generators
# fails fast at the publish schema gate (services/generation_schema.py) so
# the root cause is surfaced rather than silently rewritten.


def parse(source: str) -> _Expr:
    """Compile *source* DSL string into an Expr object.

    Raises ConditionDSLParseError on any lexical or syntactic error.
    """
    if not source or not source.strip():
        raise ConditionDSLParseError("Empty condition DSL string")

    tokens = _tokenize(source)
    parser = _Parser(tokens)
    expr = parser.parse_expr()

    # Ensure we consumed the entire token stream
    if not parser._at_end():
        leftover_type, leftover_val = parser._peek()
        raise ConditionDSLParseError(
            f"Unexpected token {leftover_type!r} ({leftover_val!r}) after end of expression"
        )

    return expr


# ---------------------------------------------------------------------------
# Evaluator helpers
# ---------------------------------------------------------------------------


def _get_attr(game_state: Any, name: str) -> Any:
    """Get attribute from dict or object."""
    if isinstance(game_state, dict):
        return game_state.get(name)
    return getattr(game_state, name, None)


def _parse_day_number(time_str: str) -> int | None:
    """Extract the integer day number from strings like 'day_3', 'day_5_morning',
    or the runtime-generated Chinese forms '第3天', '第3天·上午', 'night_3'.

    Returns None if no day number is found. BUGS #22 layer 2 — events_data is
    generated by an LLM that writes ``day_N`` but the runtime clock emits
    ``第N天`` (and occasionally ``night_N``); without a forgiving parser the
    condition `time_after('day_1')` was perpetually False, defeating every
    scripted event.
    """
    if not time_str:
        return None
    # English day_N / night_N
    m = re.search(r"(?i)(?:day|night)_(\d+)", time_str)
    if m:
        return int(m.group(1))
    # Chinese 第N天 / 第N日
    m = re.search(r"第\s*(\d+)\s*[天日]", time_str)
    if m:
        return int(m.group(1))
    return None


def _eval_func(name: str, arg: str, game_state: Any) -> bool:
    """Evaluate a whitelisted function call."""
    if name == "time_after":
        current_time = _get_attr(game_state, "current_time") or ""
        threshold_day = _parse_day_number(arg)
        current_day = _parse_day_number(str(current_time))
        if threshold_day is None or current_day is None:
            return False
        return current_day >= threshold_day

    if name == "location_is":
        current_location = _get_attr(game_state, "current_location") or ""
        return str(current_location) == arg

    if name == "player_did":
        player_actions = _get_attr(game_state, "player_actions") or []
        return arg in player_actions

    # Should never reach here since parse() enforces whitelist
    return False


def _resolve_operand(node: _Expr, game_state: Any) -> Any:
    """Resolve an operand node to a Python value for comparison."""
    if isinstance(node, _IntLit):
        return node.value
    if isinstance(node, _StrLit):
        return node.value
    if isinstance(node, _FieldRef):
        world_state = _get_attr(game_state, "world_state") or {}
        # BUGS #22 layer 2 — missing world_state keys default to 0, not None.
        # events_data DSL frequently uses `world_state.flag == 0` as the
        # "flag has not been set yet" precondition; with None we returned
        # False (because _compare short-circuits on None) and the event
        # could never fire. 0 matches the implicit init-time semantics of
        # boolean / counter flags that the generator writes.
        if isinstance(world_state, dict):
            return world_state.get(node.key, 0)
        return getattr(world_state, node.key, 0)
    if isinstance(node, _FuncCall):
        # func call in operand position → bool
        return _eval_func(node.name, node.arg, game_state)
    return None


def _compare(op: str, left_val: Any, right_val: Any) -> bool:
    """Perform a comparison; return False on type incompatibility instead of raising."""
    if left_val is None or right_val is None:
        return False
    try:
        if op == ">":
            return left_val > right_val
        if op == ">=":
            return left_val >= right_val
        if op == "<":
            return left_val < right_val
        if op == "<=":
            return left_val <= right_val
        if op == "==":
            return left_val == right_val
        if op == "!=":
            return left_val != right_val
    except (TypeError, ValueError):
        return False
    return False


# ---------------------------------------------------------------------------
# Public evaluate() entry-point
# ---------------------------------------------------------------------------


def evaluate(expr: _Expr, game_state: dict | object) -> bool:
    """Evaluate a parsed Expr against *game_state*.

    Returns False (not raises) on missing fields / type incompatibilities.
    """
    if isinstance(expr, _BinOp):
        if expr.op == "AND":
            # Short-circuit
            return evaluate(expr.left, game_state) and evaluate(expr.right, game_state)
        if expr.op == "OR":
            # Short-circuit
            return evaluate(expr.left, game_state) or evaluate(expr.right, game_state)
        return False

    if isinstance(expr, _Not):
        return not evaluate(expr.inner, game_state)

    if isinstance(expr, _FuncCall):
        return _eval_func(expr.name, expr.arg, game_state)

    if isinstance(expr, _Compare):
        left_val = _resolve_operand(expr.left, game_state)
        right_val = _resolve_operand(expr.right, game_state)
        return _compare(expr.op, left_val, right_val)

    # Unknown node type — safe fallback
    return False


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def parse_and_evaluate(source: str, game_state: dict | object) -> bool:
    """Parse DSL string and immediately evaluate it. Convenience wrapper."""
    return evaluate(parse(source), game_state)
