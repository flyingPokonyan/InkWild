"""Phase 6 tests: per-model structured-output capability matrix."""
from llm.model_capabilities import StructuredOutputMode, capability_for


def test_deepseek_v4_pro_uses_json_object():
    cap = capability_for("deepseek-v4-pro")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_deepseek_r1_uses_json_object():
    cap = capability_for("deepseek-r1")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_claude_sonnet_uses_forced_tool():
    cap = capability_for("claude-sonnet-4-6")
    assert cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL


def test_claude_opus_uses_forced_tool():
    cap = capability_for("claude-opus-4-7")
    assert cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL


def test_gpt4_uses_forced_tool():
    cap = capability_for("gpt-4o")
    assert cap.structured_output_mode == StructuredOutputMode.FORCED_TOOL


def test_unknown_model_defaults_to_tool_use_auto():
    cap = capability_for("totally-new-model-xyz")
    assert cap.structured_output_mode == StructuredOutputMode.TOOL_USE_AUTO


def test_grok_multi_agent_console_uses_json_object():
    cap = capability_for("grok-4.20-multi-agent-console")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_qwen_thinking_uses_json_object():
    cap = capability_for("qwen3.7-max-preview-thinking")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT


def test_grok_fast_uses_default_tool_use_auto():
    """grok-4.20-fast doesn't match a reasoning prefix; it's a vanilla model."""
    cap = capability_for("grok-4.20-fast")
    assert cap.structured_output_mode == StructuredOutputMode.TOOL_USE_AUTO


def test_empty_model_id_returns_default():
    cap = capability_for("")
    assert cap.structured_output_mode == StructuredOutputMode.TOOL_USE_AUTO


def test_case_insensitive_lookup():
    cap = capability_for("DeepSeek-V4-Pro")
    assert cap.structured_output_mode == StructuredOutputMode.JSON_OBJECT
