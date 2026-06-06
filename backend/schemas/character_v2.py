"""Character v2 schema — character_roster_builder 使用的结构化人物模型。

CharacterRosterEntry: planner LLM 产出的简略条目（name + role_tag + faction + is_image_target）。
Character: 完整人物 schema（含 personality / secret / knowledge / schedule / relations 等）。
"""
from pydantic import BaseModel, Field


class CharacterRosterEntry(BaseModel):
    name: str
    role_tag: str            # 如 "主角" / "宿敌" / "心腹" / "市井小贩"
    faction: str = ""        # 派系归属，可空
    is_image_target: bool = False


class CharacterScheduleSlot(BaseModel):
    time: str                # 如 "morning" / "afternoon" / "evening" / "night"
    location: str


class CharacterPeerRelation(BaseModel):
    target: str              # 必须是同 roster 中的另一个 NPC name
    trust: int = Field(ge=-10, le=10)
    kind: str = ""           # 简短类别如 "盟友" / "宿敌"


class Character(BaseModel):
    name: str
    role_tag: str = ""
    faction: str = ""
    is_image_target: bool = False
    personality: str
    # 说话方式：称谓 / 句式 / 口头禅 / 1-2 句范例台词。IP 角色由 IPKnowledgePack
    # 的 voice_style+tone_lingo 种入，原创角色由生成 LLM 产出。运行时注入 NPC
    # system prompt 稳定前缀。见 spec 2026-06-01-npc-voice-style-ip-anchor。
    voice_style: str = ""
    secret: str = ""
    knowledge: list[str] = Field(default_factory=list)
    schedule: dict[str, str] = Field(default_factory=dict)  # {time_slot: location}
    initial_location: str = ""
    initial_peer_relations: list[CharacterPeerRelation] = Field(default_factory=list)
    # "男" / "女" / "" — seeds the cover_brief portrait pipeline. Empty means
    # unset; the helper LLM will then infer gender from personality/role_tag.
    gender: str = ""
    # Populated for every character (not just playable) so toggling playable in
    # the editor is a pure boolean flip with no extra data entry required.
    description: str = ""                            # 背景、动机、关键经历（2-3 句）
    abilities: list[str] = Field(default_factory=list)
    starting_inventory: list[str] = Field(default_factory=list)
