"""Per-model structured-output capability matrix.

Maps a model_id (as bound in the model slot management table) to the
structured-output mechanism that gives the most reliable JSON / tool_use
output for that model.

Heuristics:
- Reasoning / thinking models (DeepSeek V4 Pro, Qwen thinking variants,
  Grok multi-agent-console, etc.) often emit reasoning text before the
  tool call; tool_choice=auto is unreliable. Prefer JSON object mode.
- Claude and GPT mainline models handle tool_choice=forced cleanly and
  give the strictest schema adherence via forced tool_use.
- Anything else: tool_choice=auto with tool_use (legacy behavior).

Lookup is by lowercase prefix match against curated patterns. Unknown
models fall back to TOOL_USE_AUTO.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StructuredOutputMode(str, Enum):
    JSON_OBJECT = "json_object"      # response_format={"type":"json_object"}
    FORCED_TOOL = "forced_tool"      # tool_choice={"type":"function","function":{"name":...}}
    TOOL_USE_AUTO = "tool_use_auto"  # tool_choice="auto"


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    structured_output_mode: StructuredOutputMode


_REASONING_PREFIXES = (
    "deepseek-v4",
    "deepseek-r1",
    "deepseek-r2",
    "qwen3",
    "qwen-3",
    "grok-4.20-multi-agent",
    "o1",
    "o3",
)

_FORCED_TOOL_PREFIXES = (
    "claude-",
    "gpt-4",
    "gpt-5",
)


def capability_for(model_id: str) -> ModelCapability:
    """Look up capability for a model id. Always returns a value.

    Unknown models default to TOOL_USE_AUTO which is the historical
    behavior; this preserves compatibility for any model that hasn't
    been classified yet.
    """
    mid = (model_id or "").lower().strip()
    if any(mid.startswith(p) for p in _REASONING_PREFIXES):
        return ModelCapability(model_id, StructuredOutputMode.JSON_OBJECT)
    if any(mid.startswith(p) for p in _FORCED_TOOL_PREFIXES):
        return ModelCapability(model_id, StructuredOutputMode.FORCED_TOOL)
    return ModelCapability(model_id, StructuredOutputMode.TOOL_USE_AUTO)
