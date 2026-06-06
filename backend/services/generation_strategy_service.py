from __future__ import annotations

import json

from llm.router import LLMRouter
from schemas.generation_strategy import (
    PlayableBrief,
    ScriptBrief,
    SearchPlan,
    VisualBrief,
    WorldBrief,
    CharacterBrief,
    normalize_character_brief,
    normalize_playable_brief,
    normalize_script_brief,
    normalize_search_plan,
    normalize_visual_brief,
    normalize_world_brief,
)


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"):text.rfind("}") + 1])
    return candidates


async def _collect_tool_output(llm: LLMRouter, messages: list[dict], tools: list[dict], system: str, max_tokens: int = 2048) -> dict | None:
    text_parts: list[str] = []
    tool_output: dict | None = None
    async for event in llm.stream_with_tools(messages=messages, tools=tools, system=system, max_tokens=max_tokens):
        if event["type"] == "text_delta":
            text_parts.append(event.get("text", ""))
        elif event["type"] == "tool_use":
            tool_output = event.get("input") or {}
    if tool_output:
        return tool_output
    text = "".join(text_parts).strip()
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


SEARCH_PLAN_TOOL = {
    "name": "build_search_plan",
    "description": "为当前生成阶段制定联网研究计划",
    "input_schema": {
        "type": "object",
        "properties": {
            "needs_search": {"type": "boolean"},
            "reference_mode": {"type": "string"},
            "queries": {"type": "array", "items": {"type": "string"}},
            "focuses": {"type": "array", "items": {"type": "string"}},
            "must_have_terms": {"type": "array", "items": {"type": "string"}},
            "avoid_terms": {"type": "array", "items": {"type": "string"}},
            "freshness_sensitive": {"type": "boolean"},
            "source_bias": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["needs_search", "queries"],
    },
}

WORLD_BRIEF_TOOL = {
    "name": "build_world_brief",
    "description": "决定世界生成的规模、形态和风格策略",
    "input_schema": {
        "type": "object",
        "properties": {
            "world_shape": {"type": "string"},
            "tone": {"type": "string"},
            "realism_level": {"type": "string"},
            "lore_density": {"type": "string"},
            "conflict_axes": {"type": "array", "items": {"type": "string"}},
            "location_count_target": {"type": "integer"},
            "tension_count_target": {"type": "integer"},
            "npc_count_target": {"type": "integer"},
            "playtime_band": {"type": "string"},
            "reference_utilization_mode": {"type": "string"},
        },
        "required": ["location_count_target", "npc_count_target", "tension_count_target"],
    },
}

CHARACTER_BRIEF_TOOL = {
    "name": "build_character_brief",
    "description": "决定人物系统的规模、关系密度和秘密分布",
    "input_schema": {
        "type": "object",
        "properties": {
            "count_target": {"type": "integer"},
            "relationship_density": {"type": "string"},
            "faction_count": {"type": "integer"},
            "secret_density": {"type": "string"},
            "knowledge_distribution": {"type": "string"},
            "schedule_granularity": {"type": "string"},
            "archetype_mix": {"type": "array", "items": {"type": "string"}},
            "power_distribution": {"type": "string"},
            "playable_candidate_count": {"type": "integer"},
        },
        "required": ["count_target"],
    },
}

PLAYABLE_BRIEF_TOOL = {
    "name": "build_playable_brief",
    "description": "决定玩家视角和可玩角色选择策略",
    "input_schema": {
        "type": "object",
        "properties": {
            "playable_count_target": {"type": "integer"},
            "recommended_count_target": {"type": "integer"},
            "viewpoint_mix": {"type": "array", "items": {"type": "string"}},
            "ability_mix": {"type": "string"},
            "spoiler_exposure_cap": {"type": "string"},
            "inventory_richness": {"type": "string"},
            "role_diversity_axes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["playable_count_target", "recommended_count_target"],
    },
}

SCRIPT_BRIEF_TOOL = {
    "name": "build_script_brief",
    "description": "决定剧本结构、事件规模、线索密度和结局分布",
    "input_schema": {
        "type": "object",
        "properties": {
            "script_type": {"type": "string"},
            "event_count_target": {"type": "integer"},
            "clue_density": {"type": "string"},
            "reveal_cadence": {"type": "string"},
            "red_herring_level": {"type": "string"},
            "branchiness": {"type": "string"},
            "time_pressure": {"type": "string"},
            "ending_mix": {"type": "array", "items": {"type": "string"}},
            "ending_count_target": {"type": "integer"},
            "trigger_type_mix": {"type": "array", "items": {"type": "string"}},
            "player_agency_level": {"type": "string"},
        },
        "required": ["event_count_target", "ending_count_target"],
    },
}

VISUAL_BRIEF_TOOL = {
    "name": "build_visual_brief",
    "description": "决定以世界背景为优先的世界主视觉和角色头像策略",
    "input_schema": {
        "type": "object",
        "properties": {
            "cover_subject": {"type": "string"},
            "mood": {"type": "string"},
            "palette": {"type": "string"},
            "composition": {"type": "string"},
            "camera_language": {"type": "string"},
            "style_tags": {"type": "array", "items": {"type": "string"}},
            "negative_tags": {"type": "array", "items": {"type": "string"}},
            "consistency_notes": {"type": "string"},
            "character_visual_hooks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "appearance": {"type": "string"},
                        "costume": {"type": "string"},
                        "mood": {"type": "string"},
                        "motif": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["cover_subject", "style_tags", "negative_tags"],
    },
}


class GenerationStrategyService:
    def __init__(self, llm_router: LLMRouter, search_plan_llm: LLMRouter | None = None):
        self.llm = llm_router
        self.search_plan_llm = search_plan_llm or llm_router

    async def build_search_plan(self, stage: str, goal: str, context: str) -> SearchPlan:
        result = await _collect_tool_output(
            self.search_plan_llm,
            messages=[{
                "role": "user",
                "content": (
                    f"阶段：{stage}\n"
                    f"目标：{goal}\n"
                    f"上下文：\n{context}\n\n"
                    "请判断当前阶段是否需要联网搜索，并给出最有价值的查询词和研究重点。"
                ),
            }],
            tools=[SEARCH_PLAN_TOOL],
            system="你是一个互动叙事创作研究规划师，负责决定当前阶段是否需要联网补充资料。",
            max_tokens=1024,
        )
        return normalize_search_plan(result)

    async def build_world_brief(self, description: str, genre: str, era: str, reference_doc: str = "") -> WorldBrief:
        result = await _collect_tool_output(
            self.llm,
            messages=[{
                "role": "user",
                "content": (
                    f"描述：{description}\n类型：{genre or '不限'}\n时代：{era or '不限'}\n"
                    f"参考资料：{reference_doc[:1200] or '无'}\n\n"
                    "请为接下来的世界生成制定策略，决定规模、风格和复杂度。"
                ),
            }],
            tools=[WORLD_BRIEF_TOOL],
            system="你是互动叙事世界设计总监，负责先决定生成策略，再交给执行模型落地。",
            max_tokens=1024,
        )
        return normalize_world_brief(result)

    async def build_character_brief(self, world_base: dict, reference_doc: str = "") -> CharacterBrief:
        result = await _collect_tool_output(
            self.llm,
            messages=[{
                "role": "user",
                "content": (
                    f"世界名称：{world_base.get('name', '')}\n"
                    f"世界设定：{str(world_base.get('base_setting', ''))[:800]}\n"
                    f"参考资料：{reference_doc[:1200] or '无'}\n\n"
                    "请决定该世界的人物系统应该如何组织，包括数量、关系密度、秘密浓度和可玩候选规模。"
                ),
            }],
            tools=[CHARACTER_BRIEF_TOOL],
            system="你是互动叙事人物系统设计师，负责决定人物规模和关系结构。",
            max_tokens=1024,
        )
        return normalize_character_brief(result)

    async def build_playable_brief(
        self,
        world_or_script_name: str,
        summary: str,
        character_count: int,
        reference_doc: str = "",
    ) -> PlayableBrief:
        result = await _collect_tool_output(
            self.llm,
            messages=[{
                "role": "user",
                "content": (
                    f"名称：{world_or_script_name}\n"
                    f"摘要：{summary[:1000]}\n"
                    f"候选人物数：{character_count}\n\n"
                    f"参考资料：{reference_doc[:1200] or '无'}\n\n"
                    "请先决定这个题材应该推荐几个核心可玩角色，再决定整体可开放规模上限参考。"
                    "核心推荐数量应宁缺毋滥，通常是最值得扮演的一小组视角。"
                    "同时决定可玩角色应采用什么视角组合、能力分布和差异化方向。"
                ),
            }],
            tools=[PLAYABLE_BRIEF_TOOL],
            system="你是玩家视角设计师，负责决定这个题材适合开放哪些可玩角色视角。",
            max_tokens=1024,
        )
        return normalize_playable_brief(result)

    async def build_script_brief(self, world_name: str, outline: str, reference_doc: str = "") -> ScriptBrief:
        result = await _collect_tool_output(
            self.llm,
            messages=[{
                "role": "user",
                "content": (
                    f"世界名称：{world_name}\n"
                    f"大纲：{outline}\n"
                    f"参考资料：{reference_doc[:1200] or '无'}\n\n"
                    "请先决定该剧本的结构策略，包括事件规模、线索密度、揭示节奏、结局分布和玩家主动性。"
                ),
            }],
            tools=[SCRIPT_BRIEF_TOOL],
            system="你是互动叙事剧本结构师，负责先制定剧本结构策略。",
            max_tokens=1024,
        )
        return normalize_script_brief(result)

    async def build_visual_brief(self, world_base: dict, characters: list[dict], reference_doc: str = "") -> VisualBrief:
        char_summary = "\n".join(
            f"- {char.get('name', '')}：{str(char.get('personality', ''))[:80]}"
            for char in characters[:8]
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{
                "role": "user",
                "content": (
                    f"世界名称：{world_base.get('name', '')}\n"
                    f"类型：{world_base.get('genre', '')}\n"
                    f"时代：{world_base.get('era', '')}\n"
                    f"世界设定：{str(world_base.get('base_setting', ''))[:1000]}\n"
                    f"人物（仅供风格一致性参考）：\n{char_summary}\n"
                    f"参考资料：{reference_doc[:1000] or '无'}\n\n"
                    "请先决定世界主视觉和角色头像的视觉策略，不直接写最终成图提示词。\n"
                    "- 世界图的第一目标，是让玩家快速理解世界背景、时代、空间气质和核心氛围。\n"
                    "- 横版世界图将用于游戏内世界详情页的大图展示，通常接近 100% 屏幕占比。\n"
                    "- 竖版世界图将用于世界列表、发现页、后台卡片等缩略展示。\n"
                    "- 世界图不要求必须出现人物；没有人物也可以成立。\n"
                    "- 如果出现人物，只需要保证人物身份、服装、气质与世界背景一致，不要设计固定姿势、手势、动作或必须拿着某件道具。\n"
                    "- cover_subject 应优先概括世界场景、空间、标志性氛围或关键视觉母题，不要默认做成人物海报。\n"
                    "- composition 和 camera_language 要优先服务于世界背景展示，再兼顾缩略图可读性。\n"
                    "- character_visual_hooks 只用于保证角色头像和偶尔出现在世界图中的人物风格一致，不要写成摆拍说明。"
                ),
            }],
            tools=[VISUAL_BRIEF_TOOL],
            system=(
                "你是视觉概念设计师，负责为叙事世界制定统一的插画策略。优先确保世界主视觉准确传达"
                "世界背景和氛围，再考虑人物露出；人物只需自然属于这个世界，不做僵硬摆拍。"
            ),
            max_tokens=1536,
        )
        return normalize_visual_brief(result)
