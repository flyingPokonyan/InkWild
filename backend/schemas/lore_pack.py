"""LorePack schema — 世界观深度内容包，由 lore_pack_builder 产出。

LoreDimension 描述规划阶段识别出的关键 lore 维度；
LorePack 是所有维度内容的聚合容器。
"""
from pydantic import BaseModel, Field


class LoreDimension(BaseModel):
    key: str          # 机器可读 key，如 "tech_levels"
    name: str         # 人类可读名，如 "技术等级"
    why_relevant: str # 简述为什么这个维度对该世界有意义


class LoreContentBlock(BaseModel):
    heading: str
    body: str


class LoreDimensionContent(BaseModel):
    key: str
    name: str
    content_blocks: list[LoreContentBlock] = Field(default_factory=list)


class LorePack(BaseModel):
    dimensions: list[LoreDimensionContent] = Field(default_factory=list)
    generated_at: str = ""  # ISO 时间戳，由 builder 填
