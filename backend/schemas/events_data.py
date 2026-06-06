"""EventDataEntry schema — events_data LLM 产出结构。

每条 event 含 id / kind / summary / trigger / effects / rumors / disabled 标志。
trigger 的形态因 kind 不同：
  - npc_intent_driven: {npc_name, condition_dsl, intent_payload}
  - conditional:       {condition_dsl, probability}
"""
from typing import Literal

from pydantic import BaseModel, Field

EventKind = Literal["npc_intent_driven", "conditional"]


class TriggerNPCIntent(BaseModel):
    npc_name: str
    condition_dsl: str
    intent_payload: dict = Field(default_factory=dict)


class TriggerConditional(BaseModel):
    condition_dsl: str
    probability: float = 1.0  # 0-1


class EventEffects(BaseModel):
    world_state_changes: dict = Field(default_factory=dict)
    spawn_clues: list[str] = Field(default_factory=list)
    npc_mood_changes: dict = Field(default_factory=dict)  # {npc_name: mood}


class EventRumor(BaseModel):
    text: str
    knower_npcs: list[str] = Field(default_factory=list)


class EventDataEntry(BaseModel):
    id: str
    kind: EventKind
    summary: str
    trigger: dict  # 形态因 kind 不同；运行时按 kind 解析
    effects: EventEffects = Field(default_factory=EventEffects)
    rumors: list[EventRumor] = Field(default_factory=list)
    disabled: bool = False  # 校验失败 → true
    disabled_reason: str = ""  # 简短原因
