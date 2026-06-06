# Checkpoint: condition_dsl — Task 3.1

**Date:** 2026-05-10
**Status:** DONE

---

## Files Modified

| File | Action |
|------|--------|
| `backend/engine/condition_dsl.py` | Created — tokenizer + recursive-descent parser + evaluator |
| `backend/tests/test_condition_dsl.py` | Created — 45 tests including fuzzer |

---

## Parser Approach

**Architecture:** Tokenizer → AST → Recursive-descent parser → AST evaluator (no eval/exec)

**AST node count:** 7 node types
- `_Expr` (base)
- `_BinOp` (AND / OR)
- `_Not`
- `_Compare`
- `_FuncCall`
- `_FieldRef`
- `_IntLit`

**Tokenizer:** Regex-based (`re.compile` with named groups). Rejects any unmatched character immediately. Keywords (AND/OR/NOT) use negative lookahead to avoid matching prefixes of identifiers (e.g. `ANDT` stays as IDENT).

**Parser class `_Parser`:** Recursive-descent with methods:
- `parse_expr` → `_parse_or` → `_parse_and` → `_parse_not` → `_parse_atom`
- `_parse_atom`: handles `(expr)`, `world_state.<key>`, func calls, bare INT operands
- `_parse_comparison_with_left`: consumes op + right operand after any valid left operand
- `_parse_operand`: resolves INT / field_ref / func_call in operand position

**Total LOC:** 518 lines (340 non-blank/non-comment)

---

## Security Constraints Enforced

1. **Tokenizer:** Unrecognized characters → `ConditionDSLParseError` immediately (no partial match)
2. **Function whitelist:** Only `time_after`, `location_is`, `player_did` accepted; any other IDENT in call position raises
3. **Dunder protection:** `world_state.__class__`, `world_state.x.__init__` etc. rejected at parse time
4. **String args only:** Function args must be string literals (not variables/expressions)
5. **Single quotes in strings:** Blocked by regex `'[^']*'` (cannot contain `'`)
6. **No eval/exec:** AST is interpreted by hand in `evaluate()`
7. **Trailing token check:** Parser verifies entire token stream consumed (`; print(...)` etc. rejected)
8. **Keywords in identifier context:** `true`, `false`, `AND`, etc. not valid atoms — rejected as parse errors

---

## Tests

**45 passed** (0 failed, 0 errors)

| Category | Count |
|----------|-------|
| Valid syntax parse | 10 |
| Invalid syntax parse | 12 |
| Security / injection rejection | 9 |
| String quote rejection | 1 |
| Evaluate correctness | 10 |
| time_after edge cases | 2 |
| Fuzzer (2000 iterations, seed=0) | 1 |

**Fuzzer result:** 2000 random garbage strings — 0 crashes in parser or evaluator. Many trigger `ConditionDSLParseError` (expected); none trigger any other exception.

---

## Notes

- `time_after('day_N')` compares day numbers numerically, extracted via `re.match(r"day_(\d+)", ...)`. Non-day-format times return `False`.
- `game_state` accepts both `dict` and attribute-bearing objects (via `_get_attr` helper).
- AND/OR short-circuit evaluation implemented.
- Missing `world_state` fields return `None` → comparison returns `False` (no raise).
