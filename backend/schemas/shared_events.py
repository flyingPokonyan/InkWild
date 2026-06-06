"""SharedEvents schema — 共享事件容器，用于世界构建流水线中的 shared_events 阶段。

SharedEvent: 单个共享历史事件（含 source_passage_ids 追溯依据）。
SharedEventsPack: 共享事件列表容器。
ImportantRelation: 单个 NPC 对另一个 NPC 的重要关系。
RelationsPack: 所有 NPC 的关系容器。
"""
from pydantic import BaseModel, Field


class SharedEventPerception(BaseModel):
    knows: str = ""       # 对该事件的客观所知
    believes: str = ""    # 主观相信但不一定真
    feels: str = ""       # 情感色彩


class SharedEvent(BaseModel):
    id: str
    title: str
    summary: str
    era: str = ""
    involved_npcs: list[str] = Field(default_factory=list)
    perceptions: dict[str, SharedEventPerception] = Field(default_factory=dict)
    source_passage_ids: list[str] = Field(default_factory=list)  # AC4 关键


class SharedEventsPack(BaseModel):
    events: list[SharedEvent] = Field(default_factory=list)


class ImportantRelation(BaseModel):
    target: str
    trust: int = Field(ge=-10, le=10)
    kind: str = ""
    why: str = ""    # 引用 shared_event_id 或 "faction:X"


class RelationsPack(BaseModel):
    relations_by_npc: dict[str, list[ImportantRelation]] = Field(default_factory=dict)
