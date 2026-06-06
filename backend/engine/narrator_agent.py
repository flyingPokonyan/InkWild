from __future__ import annotations

from typing import AsyncIterator

from engine.imagery_extractor import extract_repeated_imagery
from engine.prompts import (
    build_narrator_system,
    build_narrator_weave_v2_system,
    render_npc_actions_for_narrator,
)
from llm.router import LLMRouter

# Main weave segment. 800 tokens ≈ 530 Chinese chars. Pre-2026-05-24 the
# main stream was unbounded (router default 2048) and the prompt encouraged
# sensory detail with no length budget, so output ran 1000-2300 chars per
# turn — the dominant contributor to 170-347s observed in the soak.
# 2026-05-26: bumped 600 → 800 — Tier2 评语 "多处文本截断"，长 dialogue + 环境
# 在 600 时撑不住（msg 727 等 round 末尾 NPC 话被切）。
# Prelude removed 2026-05-26 (BUGS #27 H3 / docs/plans/narrator-simplification-2026-05.md).
_MAIN_MAX_TOKENS = 800


class NarratorAgent:
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def stream(
        self,
        scene_direction: str,
        npc_dialogues: dict[str, str],
        recent_messages: list[dict],
        authors_note: str | None = None,
        prelude_text: str | None = None,
    ) -> AsyncIterator[dict]:
        system = build_narrator_system(authors_note=authors_note, prelude_text=prelude_text)
        dialogue_lines = "\n".join(f"- {name}：{dialogue}" for name, dialogue in npc_dialogues.items()) or "（无）"
        user_lines = [
            "【导演场景方向】",
            scene_direction or "（无）",
            "",
            "【NPC对白】",
            dialogue_lines,
            "",
        ]
        if prelude_text:
            user_lines.append("请承接上文（system 中给出的开场段），织入 NPC 对白和后续动作，不要重复开场。")
        else:
            user_lines.append("请将上述内容整合成自然流畅的叙事文本。")
        messages = [
            *recent_messages,
            {"role": "user", "content": "\n".join(user_lines)},
        ]

        async for event in self.llm_router.stream_with_tools(
            messages=messages, tools=[], system=system, max_tokens=_MAIN_MAX_TOKENS,
        ):
            yield event

    async def stream_v2(
        self,
        *,
        scene_direction: str,
        npc_actions: list,  # list[NPCAction] sorted by priority desc
        scene_role_map: dict[str, str] | None = None,
        recent_messages: list[dict],
        authors_note: str | None = None,
        prelude_text: str | None = None,
        narrative_pressure: str = "advance",
    ) -> AsyncIterator[dict]:
        """v2 weave — consumes a priority-sorted ``NPCAction`` list.

        Hidden state (hidden_note, intent_update, mood_shift) is not surfaced
        — orchestrator drops it before calling. The narrator only sees
        action_type / dialogue / physical / tone / target / priority.

        See docs/plans/narrator-simplification-2026-05.md — multi_step_input /
        weak_input 分支已撤回到 v1-style 简单形态。
        """
        system = build_narrator_weave_v2_system(
            authors_note=authors_note,
            prelude_text=prelude_text,
        )
        rendered_actions = render_npc_actions_for_narrator(npc_actions, scene_role_map)
        user_lines = [
            "【导演场景方向】",
            scene_direction or "（无）",
            "",
            f"【节奏提示】{narrative_pressure}",
            "",
            rendered_actions,
            "",
        ]

        # 反意象重复 anti-anchoring v2：把最近 2 段 narrator 输出明确注入 user message
        # 作为 "do-not-repeat" 参考。LLM 单次 call 默认看不到自己跨 round 的意象池，
        # 这一段给它 cross-round 视野。和 H3 anchoring fix 一脉相承（filter_recent_messages
        # 删 env-only 行；本块进一步标 "已写过，换"）。详见 BUGS #27 update 4。
        recent_narrator_outputs = [
            m.get("content", "") for m in recent_messages
            if m.get("role") == "assistant" and m.get("content")
        ][-2:]
        if recent_narrator_outputs:
            # 程序级抽取真正重复出现的双字意象，替代硬编码的唐风 fallback。
            # 跨世界泛用：唐 / 维多利亚 / 近未来都靠相同 bigram 频次信号。
            skip_names = {a.npc_name for a in npc_actions if getattr(a, "npc_name", None)}
            repeated = extract_repeated_imagery(
                recent_narrator_outputs, skip_names=skip_names
            )
            dedup_hint = (
                f"已重复意象：{' / '.join(repeated)}"
                if repeated
                else "请避免重复上文的双字意象"
            )
            user_lines.append(
                "【近期你已写过的段落 — 本回合务必换意象、换句式开头、换感官切入点。"
                f"{dedup_hint}】"
            )
            for idx, out in enumerate(recent_narrator_outputs, 1):
                trimmed = out[:200] + ("..." if len(out) > 200 else "")
                user_lines.append(f"段{idx}：{trimmed}")
            user_lines.append("")

        if prelude_text:
            user_lines.append("请承接上文（system 中的开场段），织入这些 NPC 行动，不要重复开场。")
        else:
            user_lines.append("请将上述内容整合成自然流畅的叙事文本。")

        messages = [
            *recent_messages,
            {"role": "user", "content": "\n".join(user_lines)},
        ]

        async for event in self.llm_router.stream_with_tools(
            messages=messages,
            tools=[],
            system=system,
            max_tokens=_MAIN_MAX_TOKENS,
        ):
            yield event
