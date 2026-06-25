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
    # 导演裁决（P1）：跨时代 / 跨版本糅合进来的角色被降级为 in_continuity=False —— 不删除
    # （留在 pack 里可见可恢复），但所有生成阶段都跳过它，避免"关公战秦琼"。默认 True。
    in_continuity: bool = True
    arbitration_note: str | None = None  # 降级原因（可见），如"西汉人物，与汉末主线跨时代"


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
    # 导演裁决（P1）：选定的版本/主线锚定说明 + 可玩视角生态位建议（注入 roster 规划）。
    canon_note: str | None = None
    playable_archetypes: list[str] = Field(default_factory=list)

    def canon_characters(self) -> list[IPCharacter]:
        """续作内（in_continuity）角色 —— 所有生成阶段应只消费这批；跨时代/跨版本降级的不进。

        被降级的角色仍留在 self.characters（可见可恢复），但不参与 roster / 详情 / 事件 /
        剧本生成。导演裁决（_arbitrate_canon）失败时无人被降级 → 等价于全量。
        """
        return [c for c in self.characters if c.in_continuity]

    def canon_character_names(self) -> list[str]:
        return [c.name for c in self.canon_characters()]

    def must_have_character_names(self) -> list[str]:
        # must_have 且在续作内才算必含 —— 跨时代角色即便原标 must_have 也不再强制注入。
        return [c.name for c in self.characters if c.must_have and c.in_continuity]

    def must_have_place_names(self) -> list[str]:
        return [p.name for p in self.places if p.must_have]
