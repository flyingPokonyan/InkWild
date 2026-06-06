"""Player input strength assessment — runtime v2 §12.

BUG #19 root-cause analysis showed weak inputs ("环顾"/"再看看") let NPC
suggestions silently become enforced. The runner side already pushes the
auto-player to push back on NPC suggestions, but at the engine level we
also clamp director intensity / active_npcs and narrator length when the
input itself is too thin to carry a turn.

Pure functions, no LLM. Cheap to run every turn.
"""

from __future__ import annotations

from dataclasses import dataclass

# Below this raw character count the input is considered "weak" enough that
# the engine should clamp director and narrator behaviour. 12 chars sits
# above "环顾"/"再看看"/"继续" but below any meaningful directed action.
WEAK_INPUT_CHAR_THRESHOLD = 12

# Pure-observation keywords. When the entire input is dominated by these
# verbs we treat the turn as observational regardless of length.
PURE_OBSERVATION_KEYWORDS: tuple[str, ...] = (
    "环顾",
    "再看看",
    "看看",
    "观察",
    "查看周围",
    "瞄一眼",
    "扫视",
    "打量",
    "继续",
    "等等",
    "再等等",
    "等一下",
)

# Keywords that imply the player named a concrete target (NPC, location,
# object, topic). Presence of any of these signals "directed" intent and
# lifts the input out of the weak bucket even if it's short.
TARGETED_KEYWORDS: tuple[str, ...] = (
    "问",
    "告诉",
    "给",
    "拿",
    "取",
    "打",
    "攻击",
    "走向",
    "前往",
    "去找",
    "进入",
    "搜",
    "翻",
    "审",
    "对峙",
    "质问",
    "威胁",
    "说服",
    "贿赂",
    "拔",
    "拥抱",
    "亲",
    "杀",
)


@dataclass
class InputAssessment:
    """Result of assess_input_strength.

    ``is_weak`` is the headline flag: when True, orchestrator will pass
    a ``player_input_weak=True`` hint to director and clamp narrator length.
    """

    char_count: int
    is_weak: bool
    has_explicit_target: bool
    is_pure_observation: bool

    def to_hint(self) -> str:
        """Build the directive that gets folded into Director's memory_context.

        Returned as plain prompt text — orchestrator concatenates it into
        ``effective_memory_context``. Empty string when the input is normal.
        """
        if not self.is_weak:
            return ""
        lines = [
            "## 玩家本轮输入信号弱（player_input_weak=true）",
            f"- 字数 {self.char_count}，"
            f"{'仅含观察类动词' if self.is_pure_observation else '无明确目标'}",
            "- dramatic_intensity 不要给 high/climax；active_npcs 不要超过 1 人",
            "- per_npc_focus 禁止暗示「NPC 主动行动」；让叙事以环境/玩家 POV 感官为主",
            "- narrator 段落应短（≤250 字），可以反问玩家「想看什么 / 想问谁」",
            "- 严禁让 NPC 替玩家完成未声明的动作（移动、取物、揭露线索等）",
            # 中间档：抑制「替玩家行动」≠ 冻结世界。世界仍要往前走一点。
            "- **但世界不能停摆**：可以推进一条环境线索 / 后台正在发生的事 / 时间流逝的"
            "细节，只要不替玩家完成他没声明的动作即可。",
        ]
        if self.is_pure_observation:
            lines.append(
                "- 玩家在观察 → **至少回报一条感官层面的新观察**（看到/听到/闻到的具体"
                "细节），看了就该有所得；可写进 state_updates.new_clues 或场景描述。"
            )
        return "\n".join(lines)


def assess_input_strength(text: str | None) -> InputAssessment:
    """Cheap, deterministic check of how directive the player's input is.

    "Weak" means: too short to carry a turn, OR purely observational with
    no explicit target. Either condition triggers the engine-level clamp.
    """
    raw = (text or "").strip()
    char_count = len(raw)

    has_explicit_target = any(kw in raw for kw in TARGETED_KEYWORDS)
    is_pure_observation = (
        not has_explicit_target
        and bool(raw)
        and any(kw in raw for kw in PURE_OBSERVATION_KEYWORDS)
    )

    # An input is weak if it's short, OR if it's purely observational
    # regardless of length (long observational prose still doesn't give
    # NPCs a hook to react to).
    is_weak = char_count < WEAK_INPUT_CHAR_THRESHOLD or (
        is_pure_observation and not has_explicit_target
    )

    return InputAssessment(
        char_count=char_count,
        is_weak=is_weak,
        has_explicit_target=has_explicit_target,
        is_pure_observation=is_pure_observation,
    )


__all__ = [
    "WEAK_INPUT_CHAR_THRESHOLD",
    "PURE_OBSERVATION_KEYWORDS",
    "TARGETED_KEYWORDS",
    "InputAssessment",
    "assess_input_strength",
]
