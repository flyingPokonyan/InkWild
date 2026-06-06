"""ResearchPack schema — 结构化研究产物，跨阶段保真容器。

由三路输入合并产出（admin_note 切片 / Tavily 检索 / IP probing），
后续阶段（lore / characters / shared_events / events）按需引用 passages 和 ip_canon。
"""
from typing import Literal

from pydantic import BaseModel, Field

PassageSource = Literal[
    "tavily", "ip_probe", "admin_note", "wikipedia", "tavily_site",
    "grok_search", "baidu_baike",
]


class Passage(BaseModel):
    """单个研究原文片段。"""

    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    source: PassageSource


class IPCanon(BaseModel):
    """LLM 自查 + Tavily 抽出的 IP 结构化知识。题材不需要时全字段为空数组。"""

    title_guesses: list[str] = Field(default_factory=list)
    canonical_names: list[str] = Field(default_factory=list)
    canonical_places: list[str] = Field(default_factory=list)
    iconic_objects: list[str] = Field(default_factory=list)
    lingo: list[str] = Field(default_factory=list)
    notable_events: list[str] = Field(default_factory=list)


class ResearchPack(BaseModel):
    """结构化研究产物容器，包含摘要、原文段、IP结构化知识。"""

    summary: str
    passages: list[Passage] = Field(default_factory=list)
    ip_canon: IPCanon = Field(default_factory=IPCanon)
