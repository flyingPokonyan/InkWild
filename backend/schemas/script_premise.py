from __future__ import annotations

from pydantic import BaseModel, Field


class ScriptPremise(BaseModel):
    """一个「下一个剧本」候选提案。

    由 grok 联网研究 + 世界 canon + 已有剧本去重后产出，用户挑选或空 outline
    时自动取 Top1，序列化成 outline 喂进 DeepSeek 创作管线。
    """

    title: str = ""              # canon 锚定的标签（最终剧本名仍由 script_base 重生成）
    theme: str = ""              # 一句话主题
    entry_event: str = ""        # 切入的 canon 事件
    povs: list[str] = Field(default_factory=list)   # 主要可玩视角（取自世界可玩角色）
    core_conflict: str = ""      # 核心冲突
    ending_directions: str = ""  # 结局走向方向

    def to_outline(self) -> str:
        """序列化成喂给 script_base / events 阶段的 outline 文本。"""
        lines: list[str] = []
        if self.theme:
            lines.append(f"主题：{self.theme}")
        if self.entry_event:
            lines.append(f"切入事件：{self.entry_event}")
        if self.povs:
            lines.append(f"主要可玩视角：{'、'.join(self.povs)}")
        if self.core_conflict:
            lines.append(f"核心冲突：{self.core_conflict}")
        if self.ending_directions:
            lines.append(f"结局走向：{self.ending_directions}")
        return "\n".join(lines).strip()
