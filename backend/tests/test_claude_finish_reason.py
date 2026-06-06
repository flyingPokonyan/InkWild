"""Anthropic reports truncation via ``stop_reason='max_tokens'``; the director's
detector speaks OpenAI's ``finish_reason='length'``. Pin the mapping."""
from llm.claude import _finish_reason_from_stop


def test_max_tokens_maps_to_length():
    assert _finish_reason_from_stop("max_tokens") == "length"


def test_end_turn_maps_to_stop():
    assert _finish_reason_from_stop("end_turn") == "stop"


def test_stop_sequence_maps_to_stop():
    assert _finish_reason_from_stop("stop_sequence") == "stop"


def test_tool_use_passthrough():
    assert _finish_reason_from_stop("tool_use") == "tool_use"


def test_none_stays_none():
    assert _finish_reason_from_stop(None) is None
