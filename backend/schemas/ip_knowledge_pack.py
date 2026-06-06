"""IP Knowledge Pack — 高复刻 IP 的结构化原作知识包。

下游 world_creator stage 接收此 pack 替代旧的 IPCanon，
通过硬约束 prompt 保证生成的世界忠于原作。
"""
from typing import Literal

from pydantic import BaseModel, Field

from schemas.research_pack import Passage

FidelityMode = Literal["strict", "loose", "none"]
IPType = Literal["tv", "movie", "novel", "anime", "game", "other"]


class IPCharacter(BaseModel):
    name: str
    role_in_story: str  # "女主" / "男主" / "反派" / "配角" 等
    relation_to_protagonist: str  # "本人" / "丈夫" / "师兄" / "母亲" 等
    traits: list[str] = Field(default_factory=list)
    must_have: bool  # required: every character must declare criticality (places default False)
    source_passage_ids: list[str] = Field(default_factory=list)
    voice_style: str | None = None  # typical speech style/quote, e.g. "温润书生口吻"
    story_arc: str | None = None    # growth arc in source IP, 30-80 chars


class IPPlace(BaseModel):
    name: str
    description: str = ""
    must_have: bool = False
    source_passage_ids: list[str] = Field(default_factory=list)
    faction_owner: str | None = None  # which faction controls this place


class IPNamedEntity(BaseModel):
    """Shared shape for IP entities that are just (name, description, sources).

    Subclassed by faction/object/event to keep types semantically distinct
    while avoiding field-level duplication.
    """

    name: str
    description: str = ""
    source_passage_ids: list[str] = Field(default_factory=list)


class IPFaction(IPNamedEntity):
    pass


class IPObject(IPNamedEntity):
    pass


class IPEvent(IPNamedEntity):
    pass


class IPTimelineEntry(BaseModel):
    when: str  # relative time anchor, e.g. "17 年前" / "序幕" / "中段" / "结局"
    event: str  # 30-60 char summary
    source_passage_ids: list[str] = Field(default_factory=list)


class IPKnowledgePack(BaseModel):
    ip_name: str
    ip_type: IPType
    fidelity_mode: FidelityMode
    summary: str
    characters: list[IPCharacter]
    places: list[IPPlace]
    factions: list[IPFaction]
    iconic_objects: list[IPObject]
    key_events: list[IPEvent]
    tone_lingo: list[str]
    passages: list[Passage]
    timeline: list[IPTimelineEntry] = Field(default_factory=list)

    def must_have_character_names(self) -> list[str]:
        return [c.name for c in self.characters if c.must_have]

    def must_have_place_names(self) -> list[str]:
        return [p.name for p in self.places if p.must_have]
