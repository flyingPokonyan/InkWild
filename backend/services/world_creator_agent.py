"""WorldCreator Agent — strategy-driven world/script generation orchestration."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable, Generic, TypeVar

import structlog

from llm.base import ImageGenerator, LLMProvider, WebSearcher
from llm.router import LLMRouter
from schemas.generation_strategy import (
    PlayableBrief,
    ResearchContext,
    ResearchRequest,
    ScriptBrief,
    VisualBrief,
    WorldBrief,
    CharacterBrief,
    normalize_playable_brief,
)
from services.generation_feedback import done_event, error_event, progress_event, result_event, warning_event
from services.generation_prompt_builder import GenerationPromptBuilder
from services.generation_strategy_service import GenerationStrategyService
from services.image_storage import ImageStorage, get_image_storage, make_image_key, save_generated_image_result
from services.research_broker import ResearchBroker
from services.tavily_search import TavilySearch
from services.world_image_fields import resolve_world_image_fields_from_mapping

logger = structlog.get_logger()
T = TypeVar("T")


PHASE_DISPLAY_NAMES = {
    "world_base": "世界框架",
    "characters": "人物系统",
    "playable": "可玩视角",
    "script_base": "剧本框架",
    "events": "事件链",
    "endings": "结局设计",
    "images": "视觉方案",
    "critic": "质检",
    "validating": "数据校验",
}


@dataclass
class _DeferredStageResult(Generic[T]):
    value: T


@dataclass
class _ScriptEventsBranchResult:
    events: list[dict] = field(default_factory=list)
    clues: dict = field(default_factory=dict)
    endings: list[dict] = field(default_factory=list)
    events_completed: bool = False
    endings_completed: bool = False
    fatal: bool = False


@dataclass
class _ScriptPlayableBranchResult:
    playable_data: list[dict] = field(default_factory=list)
    playable_brief: PlayableBrief | None = None
    completed: bool = False


@dataclass
class _WorldPlayableBranchResult:
    playable_data: list[dict] = field(default_factory=list)
    playable_brief: PlayableBrief | None = None
    completed: bool = False


@dataclass
class _WorldImagePrepBranchResult:
    visual_brief: VisualBrief | None = None
    completed: bool = False


@dataclass(frozen=True)
class _ResearchPolicyDecision:
    allow_external_search: bool
    reason: str = ""
    signals: tuple[str, ...] = ()


_STREAM_DONE = object()

_STYLE_REFERENCE_PATTERN = re.compile(r"(参考|致敬|类似|像|改编自)《[^》]{1,40}》")
_YEAR_REFERENCE_PATTERN = re.compile(r"\d{3,4}年")
_STYLE_REFERENCE_KEYWORDS = (
    "风格",
    "气质",
    "镜头语言",
    "导演",
    "电影",
    "电视剧",
    "剧集",
    "动漫",
    "动画",
    "小说",
    "游戏",
    "视觉参考",
)
_DOMAIN_REFERENCE_KEYWORDS = (
    "法医",
    "尸检",
    "警署",
    "警务",
    "刑侦",
    "审判",
    "法院",
    "律师",
    "检察",
    "监狱",
    "医院",
    "手术",
    "急诊",
    "药物",
    "精神科",
    "宗教",
    "祭祀",
    "军队",
    "舰队",
    "情报",
    "外交",
    "宫廷",
    "朝堂",
    "记者",
    "媒体",
    "电视台",
    "制片",
    "拍摄",
    "实验室",
    "黑客",
    "脑机",
    "公司治理",
    "金融",
    "证券",
)
_HISTORICAL_REFERENCE_KEYWORDS = (
    "维多利亚",
    "民国",
    "昭和",
    "大正",
    "平成",
    "工业革命",
    "冷战",
    "中世纪",
    "文艺复兴",
    "战国",
    "幕末",
    "明治",
    "清末",
)
_ENDING_CONSEQUENCE_KEYWORDS = (
    "判刑",
    "定罪",
    "无罪",
    "死刑",
    "坐牢",
    "逮捕",
    "通缉",
    "审判",
    "抢救",
    "感染",
    "处决",
    "继承",
    "破产",
    "停职",
)


WORLD_BASE_TOOL = {
    "name": "create_world_base",
    "description": "生成世界框架：名称、简介、设定、地点",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "世界名称"},
            "description": {"type": "string", "description": "世界简介（1-2句）"},
            "genre": {"type": "string", "description": "类型（悬疑/奇幻/科幻等）"},
            "era": {"type": "string", "description": "时代背景"},
            "difficulty": {"type": "integer", "description": "难度1-5"},
            "estimated_time": {"type": "string", "description": "预计游玩时长"},
            "base_setting": {"type": "string", "description": "详细世界观设定（300-600字），包含历史背景、社会结构、核心矛盾"},
            "free_setting": {"type": "string", "description": "自由模式世界张力，每行一条（3-5条）"},
            "locations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string", "description": "地点描述（1-2句）"},
                    },
                    "required": ["name", "description"],
                },
                "description": "5-10个地点",
            },
        },
        "required": ["name", "description", "genre", "era", "difficulty", "estimated_time", "base_setting", "free_setting", "locations"],
    },
}

CHARACTERS_TOOL = {
    "name": "create_characters",
    "description": "生成完整人物表",
    "input_schema": {
        "type": "object",
        "properties": {
            "world_characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "personality": {"type": "string", "description": "性格描写（2-3句）"},
                        "secret": {"type": "string", "description": "人物秘密，可为空"},
                        "knowledge": {"type": "array", "items": {"type": "string"}, "description": "人物掌握的信息"},
                        "schedule": {"type": "object", "description": "日程安排，key为时段，value为地点"},
                        "initial_location": {"type": "string", "description": "初始位置，必须是已有地点之一"},
                        "initial_peer_relations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "target": {"type": "string", "description": "另一位 NPC 的名字（必须是本人物表中存在的 NPC，不要指向玩家角色）"},
                                    "trust": {"type": "integer", "description": "对该 NPC 的信任度，范围 -10（极度敌对）到 10（生死相托）"},
                                    "label": {"type": "string", "description": "关系标签，如「邻居」「上司下属」「情敌」「兄弟」「暗恋」「曾经的恩人」"},
                                    "history_summary": {"type": "string", "description": "一句话概括两人之间的过去（怎么认识的，发生过什么）"},
                                },
                                "required": ["target", "trust"],
                            },
                            "description": (
                                "本人物跟其他 NPC 之间值得记的关系，0-3 条即可（不要每个 NPC 都写满）。"
                                "示例：王福对赵姐 trust=6 label=邻居 history=邻居 30 年常来借米。"
                                "重要：只列你这个角色心里真正在意的关系；trust 反映的是「你怎么看 TA」，不是 TA 怎么看你——"
                                "如果你跟某 NPC 关系单向（你暗恋 TA / 你恨 TA 但 TA 不知道），就只在你这里写一条，不要在 TA 那里写反向。"
                            ),
                        },
                    },
                    "required": ["name", "personality", "initial_location"],
                },
                "description": "6-15个人物（NPC），每个有鲜明性格、秘密和动机",
            },
        },
        "required": ["world_characters"],
    },
}

PLAYABLE_TOOL = {
    "name": "select_playable",
    "description": "从人物表中挑选可玩角色并补充角色信息",
    "input_schema": {
        "type": "object",
        "properties": {
            "playable_characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "角色名称，必须是人物表中已有的名字"},
                        "description": {"type": "string", "description": "角色简介（面向玩家）"},
                        "abilities": {"type": "array", "items": {"type": "string"}, "description": "2-3个特殊能力"},
                        "starting_inventory": {"type": "array", "items": {"type": "string"}, "description": "起始物品"},
                    },
                    "required": ["name", "description", "abilities", "starting_inventory"],
                },
                "description": "按推荐策略返回核心可玩角色；数量以提示词中的推荐数量为准，宁缺毋滥，不要凑数",
            },
        },
        "required": ["playable_characters"],
    },
}

SCRIPT_BASE_TOOL = {
    "name": "create_script_base",
    "description": "生成剧本框架",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "剧本名称"},
            "description": {"type": "string", "description": "剧本简介（1-2句）"},
            "script_setting": {"type": "string", "description": "剧本核心秘密和真相（200-400字，不展示给玩家）"},
            "difficulty": {"type": "integer", "description": "难度1-5"},
            "estimated_time": {"type": "string", "description": "预计游玩时长"},
            "script_type": {"type": "string", "description": "剧本类型：mystery(推理本)/emotional(情感本)/faction(阵营本)/mechanism(机制本)/horror(恐怖本)", "enum": ["mystery", "emotional", "faction", "mechanism", "horror"]},
        },
        "required": ["name", "description", "script_setting", "difficulty", "estimated_time", "script_type"],
    },
}

EVENTS_TOOL = {
    "name": "create_events",
    "description": "生成事件链与线索",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "trigger_type": {"type": "string", "enum": ["time", "clue", "location", "clue_count", "rounds_without_progress"]},
                        "trigger_condition": {"type": "object"},
                        "description": {"type": "string"},
                        "effects": {"type": "object"},
                        "priority": {"type": "integer"},
                    },
                    "required": ["name", "trigger_type", "trigger_condition", "description", "effects"],
                },
                "description": "6-10个事件",
            },
            "clues": {"type": "object", "description": "线索定义，key为线索ID，value为描述"},
        },
        "required": ["events", "clues"],
    },
}

ENDINGS_TOOL = {
    "name": "create_endings",
    "description": "生成结局条件",
    "input_schema": {
        "type": "object",
        "properties": {
            "endings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ending_type": {"type": "string", "enum": ["good", "normal", "bad", "hidden", "timeout"]},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "hard_conditions": {"type": ["object", "null"]},
                        "soft_conditions": {"type": ["string", "null"]},
                        "priority": {"type": "integer"},
                    },
                    "required": ["ending_type", "title", "description"],
                },
                "description": "3-5个结局",
            },
        },
        "required": ["endings"],
    },
}

SCRIPT_PLAYABLE_TOOL = {
    "name": "select_script_playable",
    "description": "为剧本挑选可玩角色",
    "input_schema": {
        "type": "object",
        "properties": {
            "playable_characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "角色名称，必须是世界人物表中已有的名字"},
                        "description": {"type": "string", "description": "该剧本下的角色简介"},
                        "abilities": {"type": "array", "items": {"type": "string"}, "description": "2-3个特殊能力"},
                        "starting_inventory": {"type": "array", "items": {"type": "string"}, "description": "起始物品"},
                    },
                    "required": ["name", "description", "abilities", "starting_inventory"],
                },
                "description": "按推荐策略返回核心可玩角色；数量以提示词中的推荐数量为准，宁缺毋滥，不要凑数",
            },
        },
        "required": ["playable_characters"],
    },
}

REVIEW_SCRIPT_PLAYABLE_TOOL = {
    "name": "review_script_playable",
    "description": "基于完整剧本收束复检并必要时微调可玩角色",
    "input_schema": {
        "type": "object",
        "properties": {
            "playable_characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "abilities": {"type": "array", "items": {"type": "string"}},
                        "starting_inventory": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "description", "abilities", "starting_inventory"],
                },
            },
            "adjusted": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["playable_characters", "adjusted", "reason"],
    },
}

REVIEW_WORLD_TOOL = {
    "name": "review_world_generation",
    "description": "审稿并判断世界生成结果是否需要局部修正",
    "input_schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "overall_score": {"type": "integer"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "repair_targets": {
                "type": "array",
                "items": {"type": "string", "enum": ["world_base", "characters", "playable"]},
            },
            "repair_brief": {"type": "string"},
        },
        "required": ["passed", "issues", "repair_targets", "repair_brief"],
    },
}

REVIEW_SCRIPT_TOOL = {
    "name": "review_script_generation",
    "description": "审稿并判断剧本生成结果是否需要局部修正",
    "input_schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "overall_score": {"type": "integer"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "repair_targets": {
                "type": "array",
                "items": {"type": "string", "enum": ["script_base", "events", "endings", "playable"]},
            },
            "repair_brief": {"type": "string"},
        },
        "required": ["passed", "issues", "repair_targets", "repair_brief"],
    },
}

IMAGE_PROMPTS_TOOL = {
    "name": "create_image_prompts",
    "description": "为世界封面和角色头像生成专业的AI绘图提示词",
    "input_schema": {
        "type": "object",
        "properties": {
            "cover_prompt": {"type": "string"},
            "character_prompts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["name", "prompt"],
                },
            },
        },
        "required": ["cover_prompt", "character_prompts"],
    },
}


async def _collect_tool_output(llm: LLMRouter, messages: list[dict], tools: list[dict], system: str, max_tokens: int = 4096) -> dict | None:
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
    if text:
        for candidate in _json_candidates(text):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    else:
        logger.warning("llm_returned_empty", tools=[tool["name"] for tool in tools])

    fallback = await _collect_json_retry_output(llm, messages, tools, system, max_tokens=max_tokens)
    if fallback is not None:
        return fallback

    logger.warning("llm_no_tool_or_json", tools=[tool["name"] for tool in tools], text_preview=text[:200])
    return None


async def _collect_text(provider: LLMProvider, messages: list[dict], system: str, max_tokens: int = 2048) -> str:
    parts: list[str] = []
    async for event in provider.stream_with_tools(messages=messages, tools=[], system=system, max_tokens=max_tokens):
        if event["type"] == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"):text.rfind("}") + 1])
    return candidates


async def _collect_json_retry_output(
    llm: LLMRouter,
    messages: list[dict],
    tools: list[dict],
    system: str,
    max_tokens: int = 4096,
) -> dict | None:
    if not tools:
        return None

    tool = tools[0]
    schema_text = json.dumps(tool.get("input_schema", {}), ensure_ascii=False, indent=2)
    retry_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                "你刚才没有返回有效的工具结果。现在不要调用工具，不要解释，不要输出 Markdown。"
                f"请直接输出一个 JSON 对象，结构必须符合下面这个 schema。\n"
                f"目标工具：{tool['name']}\n"
                f"JSON Schema:\n{schema_text}"
            ),
        },
    ]
    retry_system = (
        f"{system}\n"
        "如果工具调用失败，你必须直接输出合法 JSON 对象，且字段完整。"
    )
    text = await _collect_text(llm, messages=retry_messages, system=retry_system, max_tokens=max_tokens)
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            logger.info("llm_json_retry_succeeded", tool=tool["name"])
            return parsed
    if text.strip():
        logger.warning("llm_json_retry_failed", tool=tool["name"], text_preview=text[:200])
    return None


def _ensure_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _limit_playable_recommendations(value: object, playable_brief: PlayableBrief) -> list[dict]:
    playable_characters = [item for item in _ensure_list(value) if isinstance(item, dict)]
    limit = max(1, playable_brief.recommended_count_target)
    if len(playable_characters) > limit:
        logger.info(
            "playable_recommendations_trimmed",
            returned_count=len(playable_characters),
            recommended_count=limit,
        )
    return playable_characters[:limit]


def _str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_peer_relations(value: object) -> list[dict]:
    """NPC-2 — sanitize LLM-emitted initial_peer_relations.

    Drops malformed entries and clamps trust to [-10, 10] so a hallucinated
    "trust=100" can't poison the seed. Returns [] when the LLM omitted the
    field — relations are optional per WorldCharacter.
    """
    items = _ensure_list(value)
    cleaned: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = _str(item.get("target"))
        if not target:
            continue
        try:
            trust = int(item.get("trust", 0))
        except (TypeError, ValueError):
            trust = 0
        trust = max(-10, min(10, trust))
        entry = {"target": target, "trust": trust}
        label = _str(item.get("label"))
        if label:
            entry["label"] = label
        history = _str(item.get("history_summary"))
        if history:
            entry["history_summary"] = history
        cleaned.append(entry)
    return cleaned


def _merge_reference_text(*parts: str) -> str:
    merged: list[str] = []
    for part in parts:
        text = _str(part)
        if text and text not in merged:
            merged.append(text)
    return "\n\n".join(merged)


def _script_outline_seed(outline: str) -> str:
    normalized = _str(outline)
    if normalized:
        return normalized
    return (
        "未提供用户故事大纲。请基于世界设定、地点、人物关系和潜在冲突，"
        "自行构思一个适合作为首个剧本的核心案件、秘密或事件。"
    )


def _build_character_summary(characters: list[dict], limit: int = 12) -> str:
    return "\n".join(
        f"- {char.get('name', '')}：{_str(char.get('personality', ''))[:60]}"
        for char in characters[:limit]
        if isinstance(char, dict)
    )


def _build_existing_script_summary(existing_scripts: list[dict], limit: int = 4) -> str:
    lines: list[str] = []
    for script in existing_scripts[:limit]:
        if not isinstance(script, dict):
            continue
        name = _str(script.get("name"))
        if not name:
            continue
        lines.append(f"- 《{name}》：{_str(script.get('description')) or '无简介'}")
        secret = _str(script.get("script_setting"))
        if secret:
            lines.append(f"  - 核心秘密：{secret[:120]}")
        event_names = "、".join(_str(item) for item in _ensure_list(script.get("event_names"))[:4] if _str(item))
        if event_names:
            lines.append(f"  - 已用事件：{event_names}")
        ending_types = "、".join(_str(item) for item in _ensure_list(script.get("ending_types"))[:4] if _str(item))
        if ending_types:
            lines.append(f"  - 结局类型：{ending_types}")
    return "\n".join(lines)


def _collect_research_signals(context: str) -> tuple[str, ...]:
    text = _str(context)
    signals: list[str] = []
    if not text:
        return ()

    if _STYLE_REFERENCE_PATTERN.search(text) or any(keyword in text for keyword in _STYLE_REFERENCE_KEYWORDS):
        signals.append("style")
    if _YEAR_REFERENCE_PATTERN.search(text) or any(keyword in text for keyword in _HISTORICAL_REFERENCE_KEYWORDS):
        signals.append("historical")
    if any(keyword in text for keyword in _DOMAIN_REFERENCE_KEYWORDS):
        signals.append("domain")
    if any(keyword in text for keyword in _ENDING_CONSEQUENCE_KEYWORDS):
        signals.append("ending_consequence")
    return tuple(dict.fromkeys(signals))


def _decide_research_policy(stage: str, context: str) -> _ResearchPolicyDecision:
    signals = _collect_research_signals(context)
    signal_set = set(signals)

    if stage == "playable":
        return _ResearchPolicyDecision(
            allow_external_search=False,
            reason="可玩视角主要依赖当前世界/剧本内部信息",
            signals=signals,
        )

    if stage == "endings":
        if "ending_consequence" in signal_set:
            return _ResearchPolicyDecision(True, signals=signals)
        return _ResearchPolicyDecision(
            allow_external_search=False,
            reason="结局设计优先依赖现有事件链和真相闭环",
            signals=signals,
        )

    if stage == "images":
        allow = bool(signal_set & {"style", "historical", "domain"})
        return _ResearchPolicyDecision(
            allow_external_search=allow,
            reason="" if allow else "视觉阶段已有世界设定和角色信息可直接成图",
            signals=signals,
        )

    allow = bool(signal_set & {"style", "historical", "domain"})
    return _ResearchPolicyDecision(
        allow_external_search=allow,
        reason="" if allow else "当前阶段没有命中额外外部资料信号",
        signals=signals,
    )


def _normalize_playable_review_result(
    value: object,
    fallback: list[dict],
    playable_brief: PlayableBrief,
) -> tuple[list[dict], bool, str]:
    if isinstance(value, tuple):
        if len(value) == 3:
            reviewed, adjusted, reason = value
            reviewed_list = _limit_playable_recommendations(reviewed, playable_brief)
            return reviewed_list or fallback, bool(adjusted), _str(reason)
        if len(value) == 2:
            reviewed, adjusted = value
            reviewed_list = _limit_playable_recommendations(reviewed, playable_brief)
            return reviewed_list or fallback, bool(adjusted), ""

    if isinstance(value, dict):
        reviewed_list = _limit_playable_recommendations(value.get("playable_characters", []), playable_brief)
        return reviewed_list or fallback, bool(value.get("adjusted")), _str(value.get("reason"))

    reviewed_list = _limit_playable_recommendations(value, playable_brief)
    return reviewed_list or fallback, False, ""


def _normalize_generation_review_result(value: object, allowed_targets: set[str]) -> dict:
    if not isinstance(value, dict):
        return {
            "passed": True,
            "overall_score": 100,
            "issues": [],
            "repair_targets": [],
            "repair_brief": "",
        }

    issues = [_str(item) for item in _ensure_list(value.get("issues")) if _str(item)]
    repair_targets = [
        target
        for target in (_str(item) for item in _ensure_list(value.get("repair_targets")))
        if target in allowed_targets
    ]
    try:
        overall_score = int(value.get("overall_score", 100))
    except (TypeError, ValueError):
        overall_score = 100
    overall_score = max(0, min(overall_score, 100))
    passed = bool(value.get("passed", not issues and not repair_targets))
    repair_brief = _str(value.get("repair_brief"))
    if not passed and not issues:
        issues = ["生成结果存在需要修正的质量问题"]
    return {
        "passed": passed,
        "overall_score": overall_score,
        "issues": issues,
        "repair_targets": repair_targets,
        "repair_brief": repair_brief,
    }


def _build_repair_note(review: dict) -> str:
    issues = "；".join(_str(item) for item in review.get("issues", []) if _str(item))
    repair_brief = _str(review.get("repair_brief"))
    parts = [
        "请根据以下审稿意见修正，不要推翻已有可用部分，只改确实有问题的内容。",
    ]
    if issues:
        parts.append(f"问题：{issues}")
    if repair_brief:
        parts.append(f"修正要求：{repair_brief}")
    return "\n".join(parts)


def _phase_display_name(phase: str) -> str:
    normalized = _str(phase)
    return PHASE_DISPLAY_NAMES.get(normalized, normalized or "当前阶段")


def _validate_world(world_base: dict, characters: list[dict], playable_names: list[str]) -> list[str]:
    warnings: list[str] = []
    location_names = {loc["name"] for loc in world_base.get("locations", [])}
    char_names = {c["name"] for c in characters}

    for char in characters:
        loc = char.get("initial_location", "")
        if loc and loc not in location_names:
            warnings.append(f"人物「{char['name']}」的初始位置「{loc}」不在地点列表中")

    for pname in playable_names:
        if pname not in char_names:
            warnings.append(f"可选角色「{pname}」不在人物表中")

    return warnings


def _validate_script(
    events: list[dict],
    endings: list[dict],
    location_names: set[str],
    playable_names: list[str],
    all_char_names: set[str],
) -> list[str]:
    warnings: list[str] = []

    for event in events:
        cond = event.get("trigger_condition", {})
        if isinstance(cond, dict):
            loc = cond.get("location", "")
            if loc and loc not in location_names:
                warnings.append(f"事件「{event.get('name', '?')}」引用了不存在的地点「{loc}」")

    for ending in endings:
        etype = ending.get("ending_type", "")
        if etype not in {"good", "normal", "bad", "hidden", "timeout"}:
            warnings.append(f"结局「{ending.get('title', '?')}」的类型「{etype}」不合法")

    for pname in playable_names:
        if pname not in all_char_names:
            warnings.append(f"剧本可选角色「{pname}」不在世界人物表中")

    return warnings


class WorldCreatorAgent:
    """Multi-step agent for world and script creation."""

    def __init__(
        self,
        llm_router: LLMRouter,
        search_plan_llm: LLMRouter | None = None,
        tavily: TavilySearch | None = None,
        research_summarizer: LLMProvider | None = None,
        web_searcher: WebSearcher | None = None,
        image_generator: ImageGenerator | None = None,
        image_storage: ImageStorage | None = None,
    ):
        self.llm = llm_router
        self.search_plan_llm = search_plan_llm or llm_router
        self.tavily = tavily
        self.research_summarizer = research_summarizer
        self.web_searcher = web_searcher
        self.image_gen = image_generator
        self.image_storage = image_storage or get_image_storage()
        self.strategy_service = GenerationStrategyService(llm_router, search_plan_llm=self.search_plan_llm)
        self.prompt_builder = GenerationPromptBuilder()
        self.research_broker = ResearchBroker(
            tavily=tavily,
            web_searcher=web_searcher,
            synthesizer=research_summarizer,
        )
        self.progress_pulse_delay = 1.6

    async def create_world(self, description: str, genre: str = "", era: str = "") -> AsyncIterator[dict]:
        completed_phases: list[str] = []
        world_base: dict | None = None
        characters: list[dict] = []
        playable_data: list[dict] = []
        quality_warnings: list[str] = []

        research_events, research_result = self._stream_research_stage(
            stage="world_base",
            goal="为世界框架生成补充必要资料",
            context=f"描述：{description}\n类型：{genre or '不限'}\n时代：{era or '不限'}",
        )
        async for event in research_events:
            yield event
        initial_research = research_result.value
        reference_doc = initial_research["text"]
        completed_phases.append("research")

        yield progress_event("world_base", "brief_started")
        brief_events, brief_result = self._stream_pending_step(
            phase="world_base",
            code="brief_pulse",
            awaitable=self.strategy_service.build_world_brief(description, genre, era, reference_doc),
        )
        async for event in brief_events:
            yield event
        world_brief = brief_result.value
        yield progress_event("world_base", "brief_ready")

        yield progress_event("world_base", "started")
        try:
            world_base_events, world_base_result = self._stream_pending_step(
                phase="world_base",
                code="drafting_pulse",
                awaitable=self._generate_world_base(description, genre, era, reference_doc, world_brief),
            )
            async for event in world_base_events:
                yield event
            world_base = world_base_result.value
            if not world_base:
                raise RuntimeError("AI 未返回有效的世界框架数据")
            yield progress_event(
                "world_base",
                "completed",
                world_name=world_base.get("name", ""),
                location_count=len(world_base.get("locations", [])),
            )
            completed_phases.append("world_base")
        except Exception as exc:
            logger.error("world_base_generation_failed", error=str(exc))
            yield error_event(f"世界框架生成失败：{exc}", phase="world_base")
            yield done_event()
            return

        research_events, research_result = self._stream_research_stage(
            stage="characters",
            goal="为人物关系和职业细节补充资料",
            context=_merge_reference_text(
                reference_doc,
                f"世界名称：{world_base.get('name', '')}\n世界设定：{_str(world_base.get('base_setting', ''))[:1200]}",
            ),
        )
        async for event in research_events:
            yield event
        character_research = research_result.value
        character_reference = _merge_reference_text(reference_doc, character_research["text"])
        yield progress_event("characters", "brief_started")
        character_brief_events, character_brief_result = self._stream_pending_step(
            phase="characters",
            code="brief_pulse",
            awaitable=self.strategy_service.build_character_brief(world_base, character_reference),
        )
        async for event in character_brief_events:
            yield event
        character_brief = character_brief_result.value
        yield progress_event("characters", "brief_ready")

        yield progress_event("characters", "started")
        try:
            characters_events, characters_result = self._stream_pending_step(
                phase="characters",
                code="drafting_pulse",
                awaitable=self._generate_characters(world_base, character_brief, character_reference),
            )
            async for event in characters_events:
                yield event
            characters = characters_result.value
            if not characters:
                raise RuntimeError("AI 未返回有效的人物数据")
            yield progress_event("characters", "completed", character_count=len(characters))
            completed_phases.append("characters")
        except Exception as exc:
            logger.error("characters_generation_failed", error=str(exc))
            yield warning_event("characters", "generation_failed", message=f"人物生成遇到问题：{exc}")
            yield result_event(self._build_world_result(world_base, [], []), partial=True, completed_phases=completed_phases)
            yield done_event()
            return

        playable_branch_events, playable_branch_result = self._stream_world_playable_branch(
            world_base=world_base,
            characters=characters,
            character_reference=character_reference,
        )
        image_prep_result: _DeferredStageResult[_WorldImagePrepBranchResult] | None = None
        if self.image_gen:
            image_prep_events, image_prep_result = self._stream_world_image_prep_branch(
                world_base=world_base,
                characters=characters,
                character_reference=character_reference,
            )
            async for event in self._merge_event_streams(playable_branch_events, image_prep_events):
                yield event
        else:
            async for event in playable_branch_events:
                yield event

        playable_branch = playable_branch_result.value
        playable_data = playable_branch.playable_data
        if playable_branch.completed:
            completed_phases.append("playable")

        yield progress_event("critic", "started")
        critic_events, critic_result = self._stream_pending_step(
            phase="critic",
            code="review_pulse",
            awaitable=self._review_world_generation(
                description=description,
                genre=genre,
                era=era,
                world_base=world_base,
                characters=characters,
                playable_data=playable_data,
            ),
        )
        async for event in critic_events:
            yield event
        critic_review = _normalize_generation_review_result(
            critic_result.value,
            {"world_base", "characters", "playable"},
        )
        image_prep_needs_refresh = False
        if critic_review["passed"]:
            yield progress_event("critic", "completed")
        elif critic_review["repair_targets"]:
            yield progress_event(
                "critic",
                "repair_started",
                target_count=len(critic_review["repair_targets"]),
                targets="、".join(critic_review["repair_targets"]),
            )
            repair_note = _build_repair_note(critic_review)
            repair_targets = set(critic_review["repair_targets"])
            try:
                if "world_base" in repair_targets:
                    repaired_world_base = await self._generate_world_base(
                        description,
                        genre,
                        era,
                        reference_doc,
                        world_brief,
                        repair_note=repair_note,
                    )
                    if repaired_world_base:
                        world_base = repaired_world_base
                        image_prep_needs_refresh = True

                if "world_base" in repair_targets or "characters" in repair_targets:
                    refreshed_character_reference = _merge_reference_text(
                        reference_doc,
                        character_research["text"],
                        f"世界名称：{world_base.get('name', '')}\n世界设定：{_str(world_base.get('base_setting', ''))[:1200]}",
                    )
                    repaired_characters = await self._generate_characters(
                        world_base,
                        character_brief,
                        refreshed_character_reference,
                        repair_note=repair_note,
                    )
                    if repaired_characters:
                        characters = repaired_characters
                        character_reference = refreshed_character_reference
                        image_prep_needs_refresh = True

                if (
                    "world_base" in repair_targets
                    or "characters" in repair_targets
                    or "playable" in repair_targets
                ):
                    playable_brief = playable_branch.playable_brief
                    if playable_brief is None:
                        playable_brief = normalize_playable_brief(
                            await self.strategy_service.build_playable_brief(
                                world_or_script_name=_str(world_base.get("name")),
                                summary=_merge_reference_text(
                                    _str(world_base.get("description")),
                                    _str(world_base.get("base_setting"))[:600],
                                ),
                                character_count=len(characters),
                                reference_doc=character_reference,
                            )
                        )
                    playable_data = await self._select_playable(
                        world_base,
                        characters,
                        playable_brief,
                        repair_note=repair_note,
                    )
                    playable_branch.playable_brief = playable_brief

                repaired_review = _normalize_generation_review_result(
                    await self._review_world_generation(
                        description=description,
                        genre=genre,
                        era=era,
                        world_base=world_base,
                        characters=characters,
                        playable_data=playable_data,
                    ),
                    {"world_base", "characters", "playable"},
                )
                if repaired_review["passed"]:
                    yield progress_event("critic", "repair_completed")
                else:
                    quality_warnings.extend(repaired_review["issues"])
                    yield warning_event(
                        "critic",
                        "repair_failed",
                        message="世界质检修正后仍有遗留问题，已保留当前最佳版本继续。",
                        issues=repaired_review["issues"],
                    )
            except Exception as exc:
                logger.warning("world_critic_repair_failed", error=str(exc))
                quality_warnings.extend(critic_review["issues"])
                yield warning_event(
                    "critic",
                    "repair_failed",
                    message=f"世界质检修正失败，已保留当前最佳版本继续：{exc}",
                    issues=critic_review["issues"],
                )
        else:
            quality_warnings.extend(critic_review["issues"])
            yield warning_event(
                "critic",
                "repair_failed",
                message="世界质检发现问题，但没有可执行的局部修正目标，已保留当前版本继续。",
                issues=critic_review["issues"],
            )
        completed_phases.append("critic")

        if self.image_gen:
            if image_prep_needs_refresh:
                image_prep_events, image_prep_result = self._stream_world_image_prep_branch(
                    world_base=world_base,
                    characters=characters,
                    character_reference=character_reference,
                )
                async for event in image_prep_events:
                    yield event
            visual_brief = image_prep_result.value.visual_brief if image_prep_result else None
            if visual_brief:
                yield progress_event("images", "started")
                try:
                    image_events, image_result = self._stream_pending_step(
                        phase="images",
                        code="rendering_pulse",
                        awaitable=self._generate_world_images(world_base, characters, playable_data, visual_brief),
                    )
                    async for event in image_events:
                        yield event
                    image_results = image_result.value
                    if image_results.get("hero") or image_results.get("cover"):
                        world_base.update(
                            resolve_world_image_fields_from_mapping(
                                {
                                    "cover_image": image_results.get("cover", ""),
                                    "hero_image": image_results.get("hero", ""),
                                }
                            )
                        )
                        yield progress_event("images", "cover_completed")
                    for char in characters:
                        avatar = image_results.get("avatars", {}).get(char["name"])
                        if avatar:
                            char["avatar"] = avatar
                    image_count = (
                        sum(1 for value in image_results.get("avatars", {}).values() if value)
                        + sum(1 for key in ("hero",) if image_results.get(key))
                    )
                    if image_count > 0:
                        yield progress_event("images", "completed", image_count=image_count)
                    else:
                        yield warning_event("images", "generation_failed", message="插画生成未返回有效结果")
                    completed_phases.append("images")
                except Exception as exc:
                    logger.warning("image_generation_failed", error=str(exc))
                    yield warning_event("images", "generation_failed", message=f"插画生成遇到问题，不影响世界数据：{exc}")
        else:
            yield progress_event("images", "skipped")

        yield progress_event("validating", "started")
        playable_names = [_str(item.get("name")) for item in playable_data]
        validation_warnings = _validate_world(world_base, characters, playable_names)
        for warning in validation_warnings:
            logger.warning("world_validation", warning=warning)
        completed_phases.append("validating")
        if validation_warnings:
            yield progress_event("validating", "warnings", warning_count=len(validation_warnings))
        else:
            yield progress_event("validating", "completed")

        result = self._build_world_result(world_base, characters, playable_data)
        if quality_warnings:
            result["quality_warnings"] = quality_warnings
        if validation_warnings:
            result["validation_warnings"] = validation_warnings
        yield result_event(result)
        yield done_event()

    async def create_script(self, world_data: dict, outline: str = "") -> AsyncIterator[dict]:
        completed_phases: list[str] = []
        script_base: dict | None = None
        events_data: list[dict] = []
        clues_data: dict = {}
        endings_data: list[dict] = []
        playable_data: list[dict] = []
        quality_warnings: list[str] = []

        world_name = _str(world_data.get("name", ""))
        world_description = _str(world_data.get("description", ""))
        world_genre = _str(world_data.get("genre", ""))
        world_era = _str(world_data.get("era", ""))
        world_setting = _str(world_data.get("base_setting", ""))
        locations = _ensure_list(world_data.get("locations", []))
        location_names = {_str(loc.get("name")) for loc in locations if isinstance(loc, dict)}
        all_chars = _ensure_list(world_data.get("world_characters", []))
        all_char_names = {_str(char.get("name")) for char in all_chars if isinstance(char, dict)}
        # 剧本可玩角色必须 ⊆ 世界可玩角色：选角/复检只看世界里 playable 的人，AI 不会把
        # 纯 NPC 选成可玩主角。回退到全量仅为防御（已发布世界不该 0 可玩角色）。
        playable_chars = [
            char for char in all_chars if isinstance(char, dict) and char.get("playable")
        ] or all_chars
        existing_scripts = [item for item in _ensure_list(world_data.get("existing_scripts", [])) if isinstance(item, dict)]
        existing_script_summary = _build_existing_script_summary(existing_scripts)
        npc_summary = _build_character_summary(all_chars)
        outline_seed = _script_outline_seed(outline)

        research_events, research_result = self._stream_research_stage(
            stage="script_base",
            goal="为剧本大纲补充必要资料",
            context=_merge_reference_text(
                f"世界名称：{world_name}\n世界简介：{world_description[:200]}\n类型：{world_genre or '不限'}\n时代：{world_era or '不限'}\n世界设定：{world_setting[:800]}\n大纲：{outline_seed}",
                f"同世界已有剧本：\n{existing_script_summary}" if existing_script_summary else "",
            ),
        )
        async for event in research_events:
            yield event
        initial_research = research_result.value
        reference_doc = _merge_reference_text(initial_research["text"], existing_script_summary)
        completed_phases.append("research")

        yield progress_event("script_base", "brief_started")
        script_brief_events, script_brief_result = self._stream_pending_step(
            phase="script_base",
            code="brief_pulse",
            awaitable=self.strategy_service.build_script_brief(world_name, outline_seed, reference_doc),
        )
        async for event in script_brief_events:
            yield event
        script_brief = script_brief_result.value
        yield progress_event("script_base", "brief_ready")

        yield progress_event("script_base", "started")
        try:
            script_base_events, script_base_result = self._stream_pending_step(
                phase="script_base",
                code="drafting_pulse",
                awaitable=self._generate_script_base(
                    world_name,
                    world_description,
                    world_genre,
                    world_era,
                    world_setting,
                    npc_summary,
                    outline_seed,
                    reference_doc,
                    script_brief,
                    existing_scripts,
                ),
            )
            async for event in script_base_events:
                yield event
            script_base = script_base_result.value
            if not script_base:
                raise RuntimeError("AI 未返回有效的剧本框架数据")
            yield progress_event("script_base", "completed", script_name=script_base.get("name", ""))
            completed_phases.append("script_base")
        except Exception as exc:
            logger.error("script_base_generation_failed", error=str(exc))
            yield error_event(f"剧本框架生成失败：{exc}", phase="script_base")
            yield done_event()
            return

        events_branch_events, events_branch_result = self._stream_script_events_branch(
            world_name=world_name,
            world_description=world_description,
            world_genre=world_genre,
            world_era=world_era,
            world_setting=world_setting,
            npc_summary=npc_summary,
            script_base=script_base,
            script_brief=script_brief,
            reference_doc=reference_doc,
            existing_scripts=existing_scripts,
        )
        playable_branch_events, playable_branch_result = self._stream_script_playable_branch(
            world_name=world_name,
            npc_summary=npc_summary,
            script_base=script_base,
            all_chars=playable_chars,
            reference_doc=reference_doc,
        )
        async for event in self._merge_event_streams(
            events_branch_events,
            playable_branch_events,
            stop_when=lambda: events_branch_result.value.fatal,
        ):
            yield event

        events_branch = events_branch_result.value
        playable_branch = playable_branch_result.value
        events_data = events_branch.events
        clues_data = events_branch.clues
        endings_data = events_branch.endings
        playable_data = playable_branch.playable_data

        if events_branch.events_completed:
            completed_phases.append("events")
        if events_branch.endings_completed:
            completed_phases.append("endings")
        if playable_branch.completed:
            completed_phases.append("playable")

        if events_branch.fatal:
            yield result_event(self._build_script_result(script_base, [], {}, [], []), partial=True, completed_phases=completed_phases)
            yield done_event()
            return

        if playable_branch.playable_data and playable_branch.playable_brief:
            yield progress_event("playable", "review_started")
            playable_review_events, playable_review_result = self._stream_pending_step(
                phase="playable",
                code="review_pulse",
                awaitable=self._review_script_playable(
                    world_name=world_name,
                    script_base=script_base,
                    endings=endings_data,
                    all_chars=playable_chars,
                    playable_data=playable_branch.playable_data,
                    playable_brief=playable_branch.playable_brief,
                ),
            )
            async for event in playable_review_events:
                yield event
            playable_data, adjusted, reason = _normalize_playable_review_result(
                playable_review_result.value,
                playable_branch.playable_data,
                playable_branch.playable_brief,
            )
            names = "、".join(_str(item.get("name")) for item in playable_data[:6]) or "无"
            if adjusted:
                yield progress_event("playable", "review_adjusted", playable_count=len(playable_data), names=names, reason=reason)
            else:
                yield progress_event("playable", "review_completed", playable_count=len(playable_data), names=names)

        yield progress_event("critic", "started")
        critic_events, critic_result = self._stream_pending_step(
            phase="critic",
            code="review_pulse",
            awaitable=self._review_script_generation(
                world_name=world_name,
                world_description=world_description,
                script_base=script_base,
                events=events_data,
                endings=endings_data,
                playable_data=playable_data,
                existing_scripts=existing_scripts,
            ),
        )
        async for event in critic_events:
            yield event
        critic_review = _normalize_generation_review_result(
            critic_result.value,
            {"script_base", "events", "endings", "playable"},
        )
        if critic_review["passed"]:
            yield progress_event("critic", "completed")
        elif critic_review["repair_targets"]:
            yield progress_event(
                "critic",
                "repair_started",
                target_count=len(critic_review["repair_targets"]),
                targets="、".join(critic_review["repair_targets"]),
            )
            repair_note = _build_repair_note(critic_review)
            repair_targets = set(critic_review["repair_targets"])
            try:
                if "script_base" in repair_targets:
                    repaired_script_base = await self._generate_script_base(
                        world_name,
                        world_description,
                        world_genre,
                        world_era,
                        world_setting,
                        npc_summary,
                        outline_seed,
                        reference_doc,
                        script_brief,
                        existing_scripts,
                        repair_note=repair_note,
                    )
                    if repaired_script_base:
                        script_base = repaired_script_base

                if "script_base" in repair_targets or "events" in repair_targets:
                    repaired_events_result = await self._generate_events(
                        world_name,
                        world_description,
                        world_genre,
                        world_era,
                        world_setting,
                        npc_summary,
                        script_base,
                        reference_doc,
                        script_brief,
                        existing_scripts,
                        repair_note=repair_note,
                    )
                    repaired_events = _ensure_list(repaired_events_result.get("events", []))
                    if repaired_events:
                        events_data = repaired_events
                        clues_candidate = repaired_events_result.get("clues")
                        clues_data = clues_candidate if isinstance(clues_candidate, dict) else {}

                if (
                    "script_base" in repair_targets
                    or "events" in repair_targets
                    or "endings" in repair_targets
                ):
                    endings_reference = _merge_reference_text(
                        reference_doc,
                        f"世界名称：{world_name}\n剧本名称：{_str(script_base.get('name'))}\n事件概览：{', '.join(_str(event.get('name')) for event in events_data[:8])}",
                    )
                    repaired_endings_result = await self._generate_endings(
                        world_name,
                        script_base,
                        events_data,
                        endings_reference,
                        script_brief,
                        existing_scripts,
                        repair_note=repair_note,
                    )
                    repaired_endings = _ensure_list(repaired_endings_result.get("endings", []))
                    if repaired_endings:
                        endings_data = repaired_endings

                if (
                    "script_base" in repair_targets
                    or "events" in repair_targets
                    or "playable" in repair_targets
                ):
                    playable_brief = playable_branch.playable_brief
                    if playable_brief is None:
                        playable_brief = normalize_playable_brief(
                            await self.strategy_service.build_playable_brief(
                                world_or_script_name=_str(script_base.get("name")) or world_name,
                                summary=_merge_reference_text(
                                    _str(script_base.get("description")),
                                    _str(script_base.get("script_setting"))[:500],
                                ),
                                character_count=len(all_chars),
                                reference_doc=reference_doc,
                            )
                        )
                    playable_data = await self._select_script_playable(
                        world_name,
                        script_base,
                        all_chars,
                        playable_brief,
                        repair_note=repair_note,
                    )
                    playable_branch.playable_brief = playable_brief

                if playable_data and playable_branch.playable_brief:
                    playable_review_value = await self._review_script_playable(
                        world_name=world_name,
                        script_base=script_base,
                        endings=endings_data,
                        all_chars=all_chars,
                        playable_data=playable_data,
                        playable_brief=playable_branch.playable_brief,
                    )
                    playable_data, _, _ = _normalize_playable_review_result(
                        playable_review_value,
                        playable_data,
                        playable_branch.playable_brief,
                    )

                repaired_review = _normalize_generation_review_result(
                    await self._review_script_generation(
                        world_name=world_name,
                        world_description=world_description,
                        script_base=script_base,
                        events=events_data,
                        endings=endings_data,
                        playable_data=playable_data,
                        existing_scripts=existing_scripts,
                    ),
                    {"script_base", "events", "endings", "playable"},
                )
                if repaired_review["passed"]:
                    yield progress_event("critic", "repair_completed")
                else:
                    quality_warnings.extend(repaired_review["issues"])
                    yield warning_event(
                        "critic",
                        "repair_failed",
                        message="剧本质检修正后仍有遗留问题，已保留当前最佳版本继续。",
                        issues=repaired_review["issues"],
                    )
            except Exception as exc:
                logger.warning("script_critic_repair_failed", error=str(exc))
                quality_warnings.extend(critic_review["issues"])
                yield warning_event(
                    "critic",
                    "repair_failed",
                    message=f"剧本质检修正失败，已保留当前最佳版本继续：{exc}",
                    issues=critic_review["issues"],
                )
        else:
            quality_warnings.extend(critic_review["issues"])
            yield warning_event(
                "critic",
                "repair_failed",
                message="剧本质检发现问题，但没有可执行的局部修正目标，已保留当前版本继续。",
                issues=critic_review["issues"],
            )
        completed_phases.append("critic")

        yield progress_event("validating", "started")
        playable_names = [_str(item.get("name")) for item in playable_data]
        validation_warnings = _validate_script(events_data, endings_data, location_names, playable_names, all_char_names)
        for warning in validation_warnings:
            logger.warning("script_validation", warning=warning)
        completed_phases.append("validating")
        if validation_warnings:
            yield progress_event("validating", "warnings", warning_count=len(validation_warnings))
        else:
            yield progress_event("validating", "completed")

        # 把 AI 选出的可玩角色名解析成 WorldCharacter UUID（落库口径）。只认世界里
        # 仍 playable 的角色；幻觉名/非可玩名一律丢弃并记 quality_warning。世界角色
        # 需带 id（generation_task_service 注入）；缺 id 时无法解析 → 安全降级为空名单。
        playable_name_to_id = {
            _str(char.get("name")).strip(): _str(char.get("id"))
            for char in playable_chars
            if isinstance(char, dict) and char.get("playable") and char.get("id")
        }
        resolved_playable_ids: list[str] = []
        for item in playable_data:
            name = _str(item.get("name")).strip()
            cid = playable_name_to_id.get(name)
            if not cid:
                quality_warnings.append(
                    f"剧本可玩角色「{_str(item.get('name'))}」不在世界可玩人物表中，已忽略"
                )
                continue
            if cid not in resolved_playable_ids:
                resolved_playable_ids.append(cid)

        result = self._build_script_result(
            script_base, events_data, clues_data, endings_data, playable_data,
            playable_character_ids=resolved_playable_ids,
        )
        if quality_warnings:
            result["quality_warnings"] = quality_warnings
        if validation_warnings:
            result["validation_warnings"] = validation_warnings
        yield result_event(result)
        yield done_event()

    async def _merge_event_streams(
        self,
        *streams: AsyncIterator[dict],
        stop_when: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict]:
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def _pump(stream: AsyncIterator[dict]) -> None:
            try:
                async for event in stream:
                    await queue.put(("event", event))
            except Exception as exc:  # noqa: BLE001
                await queue.put(("error", exc))
            finally:
                await queue.put(("done", _STREAM_DONE))

        tasks = [asyncio.create_task(_pump(stream)) for stream in streams]
        finished = 0
        try:
            while finished < len(tasks):
                kind, payload = await queue.get()
                if kind == "event":
                    yield payload  # type: ignore[misc]
                    if stop_when and stop_when():
                        break
                elif kind == "error":
                    raise payload  # type: ignore[misc]
                else:
                    finished += 1
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    def _stream_world_playable_branch(
        self,
        *,
        world_base: dict,
        characters: list[dict],
        character_reference: str,
    ) -> tuple[AsyncIterator[dict], _DeferredStageResult[_WorldPlayableBranchResult]]:
        result = _DeferredStageResult(_WorldPlayableBranchResult())

        async def _events() -> AsyncIterator[dict]:
            research_events, research_result = self._stream_research_stage(
                stage="playable",
                goal="判断哪些玩家视角最有趣",
                context=_merge_reference_text(
                    character_reference,
                    f"世界名称：{world_base.get('name', '')}\n人物概览：\n{_build_character_summary(characters)}",
                ),
            )
            async for event in research_events:
                yield event
            playable_research = research_result.value
            yield progress_event("playable", "brief_started")
            playable_brief_events, playable_brief_result = self._stream_pending_step(
                phase="playable",
                code="brief_pulse",
                awaitable=self.strategy_service.build_playable_brief(
                    world_or_script_name=_str(world_base.get("name")),
                    summary=_merge_reference_text(_str(world_base.get("description")), _str(world_base.get("base_setting"))[:600]),
                    character_count=len(characters),
                    reference_doc=playable_research["text"],
                ),
            )
            async for event in playable_brief_events:
                yield event
            playable_brief = normalize_playable_brief(playable_brief_result.value)
            result.value.playable_brief = playable_brief
            yield progress_event("playable", "brief_ready")

            yield progress_event("playable", "started")
            try:
                playable_events, playable_result = self._stream_pending_step(
                    phase="playable",
                    code="drafting_pulse",
                    awaitable=self._select_playable(world_base, characters, playable_brief),
                )
                async for event in playable_events:
                    yield event
                result.value.playable_data = playable_result.value or []
                result.value.completed = True
                names = "、".join(_str(item.get("name")) for item in result.value.playable_data[:6]) or "无"
                yield progress_event("playable", "completed", playable_count=len(result.value.playable_data), names=names)
            except Exception as exc:
                logger.warning("playable_selection_failed", error=str(exc))
                yield warning_event("playable", "selection_failed", message=f"角色选择遇到问题：{exc}")

        return _events(), result

    def _stream_world_image_prep_branch(
        self,
        *,
        world_base: dict,
        characters: list[dict],
        character_reference: str,
    ) -> tuple[AsyncIterator[dict], _DeferredStageResult[_WorldImagePrepBranchResult]]:
        result = _DeferredStageResult(_WorldImagePrepBranchResult())

        async def _events() -> AsyncIterator[dict]:
            research_events, research_result = self._stream_research_stage(
                stage="images",
                goal="为封面和角色形象补充视觉参考",
                context=_merge_reference_text(
                    character_reference,
                    (
                        f"世界名称：{world_base.get('name', '')}\n"
                        f"世界简介：{_str(world_base.get('description'))[:200]}\n"
                        f"类型：{_str(world_base.get('genre')) or '不限'}\n"
                        f"时代：{_str(world_base.get('era')) or '不限'}\n"
                        f"主要人物：\n{_build_character_summary(characters)}"
                    ),
                ),
            )
            async for event in research_events:
                yield event
            image_research = research_result.value
            yield progress_event("images", "brief_started")
            try:
                visual_brief_events, visual_brief_result = self._stream_pending_step(
                    phase="images",
                    code="brief_pulse",
                    awaitable=self.strategy_service.build_visual_brief(
                        world_base,
                        characters,
                        _merge_reference_text(character_reference, image_research["text"]),
                    ),
                )
                async for event in visual_brief_events:
                    yield event
                result.value.visual_brief = visual_brief_result.value
                if not result.value.visual_brief:
                    raise RuntimeError("AI 未返回有效的视觉策略")
                result.value.completed = True
                yield progress_event("images", "brief_ready")
            except Exception as exc:
                logger.warning("visual_brief_generation_failed", error=str(exc))
                yield warning_event("images", "generation_failed", message=f"视觉策略生成遇到问题，不影响世界数据：{exc}")

        return _events(), result

    def _stream_script_events_branch(
        self,
        *,
        world_name: str,
        world_description: str,
        world_genre: str,
        world_era: str,
        world_setting: str,
        npc_summary: str,
        script_base: dict,
        script_brief: ScriptBrief,
        reference_doc: str,
        existing_scripts: list[dict],
    ) -> tuple[AsyncIterator[dict], _DeferredStageResult[_ScriptEventsBranchResult]]:
        result = _DeferredStageResult(_ScriptEventsBranchResult())

        async def _events() -> AsyncIterator[dict]:
            research_events, research_result = self._stream_research_stage(
                stage="events",
                goal="为事件链和线索补充专业细节",
                context=_merge_reference_text(
                    reference_doc,
                    f"世界名称：{world_name}\n世界简介：{world_description[:200]}\n剧本框架：{_str(script_base.get('description'))}\n核心秘密：{_str(script_base.get('script_setting'))[:800]}",
                ),
            )
            async for event in research_events:
                yield event
            events_research = research_result.value
            events_reference = _merge_reference_text(reference_doc, events_research["text"])

            yield progress_event("events", "started")
            try:
                event_generation_events, event_generation_result = self._stream_pending_step(
                    phase="events",
                    code="drafting_pulse",
                    awaitable=self._generate_events(
                        world_name,
                        world_description,
                        world_genre,
                        world_era,
                        world_setting,
                        npc_summary,
                        script_base,
                        events_reference,
                        script_brief,
                        existing_scripts,
                    ),
                )
                async for event in event_generation_events:
                    yield event
                events_result = event_generation_result.value or {}
                result.value.events = _ensure_list(events_result.get("events", []))
                result.value.clues = events_result.get("clues", {}) if isinstance(events_result.get("clues"), dict) else {}
                if not result.value.events:
                    raise RuntimeError("AI 未返回有效的事件数据")
                result.value.events_completed = True
                yield progress_event("events", "completed", event_count=len(result.value.events), clue_count=len(result.value.clues))
            except Exception as exc:
                logger.error("events_generation_failed", error=str(exc))
                result.value.fatal = True
                yield warning_event("events", "generation_failed", message=f"事件链生成遇到问题：{exc}")
                return

            research_events, research_result = self._stream_research_stage(
                stage="endings",
                goal="为结局设计补充逻辑和判定灵感",
                context=_merge_reference_text(
                    events_reference,
                    f"世界名称：{world_name}\n剧本名称：{_str(script_base.get('name'))}\n事件概览：{', '.join(_str(event.get('name')) for event in result.value.events[:8])}",
                ),
            )
            async for event in research_events:
                yield event
            endings_research = research_result.value
            endings_reference = _merge_reference_text(events_reference, endings_research["text"])

            yield progress_event("endings", "started")
            try:
                endings_events, endings_result_holder = self._stream_pending_step(
                    phase="endings",
                    code="drafting_pulse",
                    awaitable=self._generate_endings(
                        world_name,
                        script_base,
                        result.value.events,
                        endings_reference,
                        script_brief,
                        existing_scripts,
                    ),
                )
                async for event in endings_events:
                    yield event
                endings_result = endings_result_holder.value or {}
                result.value.endings = _ensure_list(endings_result.get("endings", []))
                if not result.value.endings:
                    raise RuntimeError("AI 未返回有效的结局数据")
                result.value.endings_completed = True
                ending_types = "、".join(sorted({_str(item.get("ending_type", "?")) for item in result.value.endings}))
                yield progress_event("endings", "completed", ending_count=len(result.value.endings), ending_types=ending_types)
            except Exception as exc:
                logger.warning("endings_generation_failed", error=str(exc))
                yield warning_event("endings", "generation_failed", message=f"结局生成遇到问题：{exc}")

        return _events(), result

    def _stream_script_playable_branch(
        self,
        *,
        world_name: str,
        npc_summary: str,
        script_base: dict,
        all_chars: list[dict],
        reference_doc: str,
    ) -> tuple[AsyncIterator[dict], _DeferredStageResult[_ScriptPlayableBranchResult]]:
        result = _DeferredStageResult(_ScriptPlayableBranchResult())

        async def _events() -> AsyncIterator[dict]:
            research_events, research_result = self._stream_research_stage(
                stage="playable",
                goal="判断该剧本适合开放哪些玩家视角",
                context=_merge_reference_text(
                    reference_doc,
                    f"剧本名称：{_str(script_base.get('name'))}\n剧本简介：{_str(script_base.get('description'))}\n世界人物：\n{npc_summary}",
                ),
            )
            async for event in research_events:
                yield event
            playable_research = research_result.value

            yield progress_event("playable", "brief_started")
            playable_brief_events, playable_brief_result = self._stream_pending_step(
                phase="playable",
                code="brief_pulse",
                awaitable=self.strategy_service.build_playable_brief(
                    world_or_script_name=_str(script_base.get("name")) or world_name,
                    summary=_merge_reference_text(_str(script_base.get("description")), _str(script_base.get("script_setting"))[:500]),
                    character_count=len(all_chars),
                    reference_doc=playable_research["text"],
                ),
            )
            async for event in playable_brief_events:
                yield event
            result.value.playable_brief = normalize_playable_brief(playable_brief_result.value)
            yield progress_event("playable", "brief_ready")

            yield progress_event("playable", "started")
            try:
                playable_events, playable_result = self._stream_pending_step(
                    phase="playable",
                    code="drafting_pulse",
                    awaitable=self._select_script_playable(world_name, script_base, all_chars, result.value.playable_brief),
                )
                async for event in playable_events:
                    yield event
                result.value.playable_data = playable_result.value or []
                result.value.completed = True
                names = "、".join(_str(item.get("name")) for item in result.value.playable_data[:6]) or "无"
                yield progress_event("playable", "completed", playable_count=len(result.value.playable_data), names=names)
            except Exception as exc:
                logger.warning("script_playable_selection_failed", error=str(exc))
                yield warning_event("playable", "selection_failed", message=f"角色选择遇到问题：{exc}")

        return _events(), result

    async def _review_script_playable(
        self,
        *,
        world_name: str,
        script_base: dict,
        endings: list[dict],
        all_chars: list[dict],
        playable_data: list[dict],
        playable_brief: PlayableBrief,
    ) -> tuple[list[dict], bool, str]:
        prompt = self.prompt_builder.build_playable_review_prompt(
            title=_str(script_base.get("name")) or world_name,
            summary=_str(script_base.get("description")),
            script_setting=_str(script_base.get("script_setting")),
            endings=endings,
            characters=all_chars,
            provisional_playable=playable_data,
            playable_brief=playable_brief,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[REVIEW_SCRIPT_PLAYABLE_TOOL],
            system="你是一个互动叙事体验设计师。请复检并必要时微调剧本可玩视角。",
            max_tokens=2048,
        )
        reviewed, adjusted, reason = _normalize_playable_review_result(result, playable_data, playable_brief)
        return reviewed, adjusted, reason

    async def _review_world_generation(
        self,
        *,
        description: str,
        genre: str,
        era: str,
        world_base: dict,
        characters: list[dict],
        playable_data: list[dict],
    ) -> dict:
        prompt = self.prompt_builder.build_world_review_prompt(
            description=description,
            genre=genre,
            era=era,
            world_base=world_base,
            characters=characters,
            playable_data=playable_data,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[REVIEW_WORLD_TOOL],
            system="你是互动叙事内容审稿负责人。请只返回结构化审稿结论，不要重写正文。",
            max_tokens=2048,
        )
        return _normalize_generation_review_result(result, {"world_base", "characters", "playable"})

    async def _review_script_generation(
        self,
        *,
        world_name: str,
        world_description: str,
        script_base: dict,
        events: list[dict],
        endings: list[dict],
        playable_data: list[dict],
        existing_scripts: list[dict],
    ) -> dict:
        prompt = self.prompt_builder.build_script_review_prompt(
            world_name=world_name,
            world_description=world_description,
            script_base=script_base,
            events=events,
            endings=endings,
            playable_data=playable_data,
            existing_scripts=existing_scripts,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[REVIEW_SCRIPT_TOOL],
            system="你是互动叙事剧本的高级审稿编辑。请只返回结构化审稿结论，不要重写正文。",
            max_tokens=2048,
        )
        return _normalize_generation_review_result(result, {"script_base", "events", "endings", "playable"})

    def _stream_research_stage(self, stage: str, goal: str, context: str) -> tuple[AsyncIterator[dict], _DeferredStageResult]:
        result = _DeferredStageResult({"text": "", "context": ResearchContext(stage=stage)})
        stage_label = _phase_display_name(stage)

        async def _events() -> AsyncIterator[dict]:
            yield progress_event("research", "analysis_started", stage=stage, stage_label=stage_label)
            policy = _decide_research_policy(stage, context)
            if not policy.allow_external_search:
                logger.info(
                    "research_skipped_by_policy",
                    stage=stage,
                    signals=list(policy.signals),
                    reason=policy.reason,
                )
                yield progress_event("research", "not_needed", stage=stage, stage_label=stage_label, reason=policy.reason)
                return
            try:
                plan_events, plan_result = self._stream_pending_step(
                    phase="research",
                    code="analysis_pulse",
                    meta={"stage": stage, "stage_label": stage_label},
                    awaitable=self.strategy_service.build_search_plan(stage=stage, goal=goal, context=context),
                )
                async for event in plan_events:
                    yield event
                plan = plan_result.value
            except Exception:
                logger.warning("research_plan_failed", stage=stage, exc_info=True)
                yield warning_event("research", "search_unavailable", stage=stage, stage_label=stage_label)
                return

            if not plan.needs_search or not plan.queries:
                yield progress_event("research", "not_needed", stage=stage, stage_label=stage_label)
                return

            request = ResearchRequest(
                stage=stage,
                goal=goal,
                query_candidates=plan.queries,
                focuses=plan.focuses,
                source_preference=plan.source_bias or plan.reference_mode,
                freshness_sensitive=plan.freshness_sensitive,
            )
            yield progress_event(
                "research",
                "request_ready",
                stage=stage,
                stage_label=stage_label,
                query_count=len(plan.queries),
            )
            yield progress_event(
                "research",
                "searching",
                stage=stage,
                stage_label=stage_label,
                query_count=len(plan.queries),
            )
            try:
                artifact_events, artifact_result = self._stream_pending_step(
                    phase="research",
                    code="searching_pulse",
                    meta={"stage": stage, "stage_label": stage_label, "query_count": len(plan.queries)},
                    awaitable=self.research_broker.collect_artifacts(request),
                )
                async for event in artifact_events:
                    yield event
                artifacts = artifact_result.value
            except Exception:
                logger.warning("research_stage_failed", stage=stage, exc_info=True)
                yield warning_event("research", "search_unavailable", stage=stage, stage_label=stage_label)
                return

            if artifacts:
                yield progress_event(
                    "research",
                    "search_completed",
                    stage=stage,
                    stage_label=stage_label,
                    artifact_count=len(artifacts),
                )
                yield progress_event("research", "summarizing", stage=stage, stage_label=stage_label)

            try:
                summary_events, summary_result = self._stream_pending_step(
                    phase="research",
                    code="summarizing_pulse",
                    meta={"stage": stage, "stage_label": stage_label},
                    awaitable=self.research_broker.summarize(request, artifacts),
                )
                async for event in summary_events:
                    yield event
                summary = summary_result.value
            except Exception:
                logger.warning("research_summary_failed", stage=stage, exc_info=True)
                summary = ""
            research_context = self.research_broker.build_context(request, artifacts, summary)
            result.value = {"text": research_context.text, "context": research_context}

            if research_context.text:
                yield progress_event(
                    "research",
                    "reference_doc_ready",
                    stage=stage,
                    stage_label=stage_label,
                    char_count=len(research_context.text),
                )
            else:
                yield progress_event("research", "not_needed", stage=stage, stage_label=stage_label)

        return _events(), result

    def _stream_pending_step(
        self,
        *,
        phase: str,
        code: str,
        awaitable: Awaitable[T],
        meta: dict[str, object] | None = None,
    ) -> tuple[AsyncIterator[dict], _DeferredStageResult[T | None]]:
        result: _DeferredStageResult[T | None] = _DeferredStageResult(None)

        async def _events() -> AsyncIterator[dict]:
            task = asyncio.create_task(awaitable)
            try:
                result.value = await asyncio.wait_for(asyncio.shield(task), timeout=self.progress_pulse_delay)
                return
            except asyncio.TimeoutError:
                yield progress_event(phase, code, **(meta or {}))
            result.value = await task

        return _events(), result

    async def _generate_world_base(
        self,
        description: str,
        genre: str,
        era: str,
        reference_doc: str,
        world_brief: WorldBrief,
        repair_note: str = "",
    ) -> dict | None:
        prompt = self.prompt_builder.build_world_base_prompt(description, genre, era, world_brief, reference_doc, repair_note)
        system = "你是一个专业的互动叙事世界设计师。你必须调用提供的工具返回结构化数据，不要输出纯文本。"
        for attempt in range(2):
            result = await _collect_tool_output(self.llm, messages=[{"role": "user", "content": prompt}], tools=[WORLD_BASE_TOOL], system=system, max_tokens=4096)
            if result:
                return result
            if attempt == 0:
                prompt += "\n\n重要：你上一次没有调用工具。这次必须调用 create_world_base 工具，不要输出任何其他内容。"
        return None

    async def _generate_characters(
        self,
        world_base: dict,
        character_brief: CharacterBrief,
        reference_doc: str,
        repair_note: str = "",
    ) -> list[dict]:
        prompt = self.prompt_builder.build_character_prompt(world_base, character_brief, reference_doc, repair_note)
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[CHARACTERS_TOOL],
            system="你是一个专业的互动叙事人物设计师。请调用工具返回结构化数据。",
            max_tokens=8192,
        )
        if not result:
            return []
        return _ensure_list(result.get("world_characters", []))

    async def _select_playable(
        self,
        world_base: dict,
        characters: list[dict],
        playable_brief: PlayableBrief,
        repair_note: str = "",
    ) -> list[dict]:
        prompt = self.prompt_builder.build_playable_prompt(
            title=_str(world_base.get("name")),
            summary=_str(world_base.get("description")),
            characters=characters,
            playable_brief=playable_brief,
            script_mode=False,
            repair_note=repair_note,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[PLAYABLE_TOOL],
            system="你是一个游戏角色设计师。请调用工具返回结构化数据。",
            max_tokens=4096,
        )
        if not result:
            return []
        return _limit_playable_recommendations(result.get("playable_characters", []), playable_brief)

    async def _generate_script_base(
        self,
        world_name: str,
        world_description: str,
        world_genre: str,
        world_era: str,
        world_setting: str,
        npc_summary: str,
        outline: str,
        reference_doc: str,
        script_brief: ScriptBrief,
        existing_scripts: list[dict],
        repair_note: str = "",
    ) -> dict | None:
        prompt = self.prompt_builder.build_script_base_prompt(
            world_name,
            world_description,
            world_genre,
            world_era,
            world_setting,
            npc_summary,
            outline,
            script_brief,
            reference_doc,
            existing_scripts,
            repair_note,
        )
        return await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[SCRIPT_BASE_TOOL],
            system="你是一个专业的互动叙事剧本设计师。请调用工具返回结构化数据。",
            max_tokens=4096,
        )

    async def _generate_events(
        self,
        world_name: str,
        world_description: str,
        world_genre: str,
        world_era: str,
        world_setting: str,
        npc_summary: str,
        script_base: dict,
        reference_doc: str,
        script_brief: ScriptBrief,
        existing_scripts: list[dict],
        repair_note: str = "",
    ) -> dict:
        prompt = self.prompt_builder.build_events_prompt(
            world_name,
            world_description,
            world_genre,
            world_era,
            world_setting,
            npc_summary,
            script_base,
            script_brief,
            reference_doc,
            existing_scripts,
            repair_note,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[EVENTS_TOOL],
            system="你是一个专业的互动叙事剧本设计师。请调用工具返回结构化数据。",
            max_tokens=4096,
        )
        return result or {"events": [], "clues": {}}

    async def _generate_endings(
        self,
        world_name: str,
        script_base: dict,
        events: list[dict],
        reference_doc: str,
        script_brief: ScriptBrief,
        existing_scripts: list[dict],
        repair_note: str = "",
    ) -> dict:
        prompt = self.prompt_builder.build_endings_prompt(
            world_name,
            script_base,
            events,
            script_brief,
            reference_doc,
            existing_scripts,
            repair_note,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[ENDINGS_TOOL],
            system="你是一个专业的互动叙事剧本设计师。请调用工具返回结构化数据。",
            max_tokens=2048,
        )
        return result or {"endings": []}

    async def _select_script_playable(
        self,
        world_name: str,
        script_base: dict,
        all_chars: list[dict],
        playable_brief: PlayableBrief,
        repair_note: str = "",
    ) -> list[dict]:
        prompt = self.prompt_builder.build_playable_prompt(
            title=_str(script_base.get("name")) or world_name,
            summary=_str(script_base.get("description")),
            characters=all_chars,
            playable_brief=playable_brief,
            script_mode=True,
            repair_note=repair_note,
        )
        result = await _collect_tool_output(
            self.llm,
            messages=[{"role": "user", "content": prompt}],
            tools=[SCRIPT_PLAYABLE_TOOL],
            system="你是一个游戏角色设计师。请调用工具返回结构化数据。",
            max_tokens=4096,
        )
        if not result:
            return []
        return _limit_playable_recommendations(result.get("playable_characters", []), playable_brief)

    async def _generate_world_images(
        self,
        world_base: dict,
        characters: list[dict],
        playable_data: list[dict],
        visual_brief: VisualBrief,
    ) -> dict:
        # TODO: remove legacy agent
        if not self.image_gen:
            return {"cover": "", "hero": "", "avatars": {}}

        world_name = _str(world_base.get("name"))
        avatar_names = [_str(item.get("name")) for item in playable_data]
        hook_map = {hook.name: hook.model_dump() for hook in visual_brief.character_visual_hooks}
        hero_prompt = self.prompt_builder.build_hero_prompt(world_base, visual_brief)

        async def _gen_hero() -> str:
            if not hero_prompt:
                return ""
            try:
                result = await self.image_gen.generate_image(hero_prompt, aspect_ratio="16:9")
                key = make_image_key("worlds/hero", world_name)
                return await save_generated_image_result(self.image_storage, result, key)
            except Exception:
                logger.warning("hero_image_failed", world=world_name, exc_info=True)
            return ""

        async def _gen_avatar(character: dict) -> tuple[str, str]:
            name = _str(character.get("name"))
            prompt = self.prompt_builder.build_avatar_prompt(character, hook_map, visual_brief)
            if not prompt:
                return name, ""
            try:
                result = await self.image_gen.generate_image(prompt, aspect_ratio="1:1")
                key = make_image_key("characters", name)
                url = await save_generated_image_result(self.image_storage, result, key)
                return name, url
            except Exception:
                logger.warning("avatar_image_failed", character=name, exc_info=True)
            return name, ""

        tasks: list[asyncio.Task] = [
            asyncio.create_task(_gen_hero()),
        ]
        for character in characters:
            if _str(character.get("name")) in avatar_names:
                tasks.append(asyncio.create_task(_gen_avatar(character)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        hero_url = results[0] if isinstance(results[0], str) else ""
        cover_url = hero_url
        avatars: dict[str, str] = {}
        for result in results[1:]:
            if isinstance(result, tuple):
                avatars[result[0]] = result[1]
        return {"cover": cover_url, "hero": hero_url, "avatars": avatars}

    def _build_script_result(
        self,
        script_base: dict,
        events: list[dict],
        clues: dict,
        endings: list[dict],
        playable_data: list[dict],
        playable_character_ids: list[str] | None = None,
    ) -> dict:
        return {
            "name": _str(script_base.get("name")),
            "description": _str(script_base.get("description")),
            "difficulty": script_base.get("difficulty", 3),
            "estimated_time": _str(script_base.get("estimated_time")) or "30-60分钟",
            "script_setting": _str(script_base.get("script_setting")),
            "script_type": _str(script_base.get("script_type")) or "mystery",
            "events": [
                {
                    "name": _str(item.get("name")),
                    "trigger_type": _str(item.get("trigger_type")) or "clue",
                    "trigger_condition": item.get("trigger_condition") if isinstance(item.get("trigger_condition"), dict) else {},
                    "description": _str(item.get("description")),
                    "effects": item.get("effects") if isinstance(item.get("effects"), dict) else {},
                    "priority": int(item.get("priority", 0) or 0),
                }
                for item in events
                if isinstance(item, dict)
            ],
            "clues": clues if isinstance(clues, dict) else {},
            "endings": [
                {
                    "ending_type": _str(item.get("ending_type")) or "normal",
                    "title": _str(item.get("title")),
                    "description": _str(item.get("description")),
                    "hard_conditions": item.get("hard_conditions"),
                    "soft_conditions": item.get("soft_conditions"),
                    "priority": int(item.get("priority", 0) or 0),
                }
                for item in endings
                if isinstance(item, dict)
            ],
            # 已解析为 WorldCharacter UUID（见 create_script 的解析块）；旧调用方
            # （如 fatal partial）不传则为空名单 = 运行时放行全部可玩角色。
            "playable_character_ids": list(playable_character_ids or []),
        }

    def _build_world_result(self, world_base: dict, characters: list[dict], playable_data: list[dict]) -> dict:
        playable_lookup = {_str(item.get("name")): item for item in playable_data}
        free_setting = world_base.get("free_setting", "")
        if isinstance(free_setting, list):
            free_setting = "\n".join(_str(item) for item in free_setting if _str(item))

        world_characters: list[dict] = []
        for char in characters:
            name = _str(char.get("name"))
            is_playable = name in playable_lookup
            playable_info = playable_lookup.get(name, {})
            world_characters.append(
                {
                    "name": name,
                    "personality": _str(char.get("personality")),
                    "secret": _str(char.get("secret")) or None,
                    "knowledge": _ensure_list(char.get("knowledge")),
                    "schedule": char.get("schedule") if isinstance(char.get("schedule"), dict) else {},
                    "initial_location": _str(char.get("initial_location")),
                    "playable": is_playable,
                    "description": _str(playable_info.get("description")) if is_playable else None,
                    "abilities": _ensure_list(playable_info.get("abilities")) if is_playable else [],
                    "starting_inventory": _ensure_list(playable_info.get("starting_inventory")) if is_playable else [],
                    "avatar": _str(char.get("avatar")) or None,
                    "initial_peer_relations": _normalize_peer_relations(
                        char.get("initial_peer_relations")
                    ),
                }
            )

        images = resolve_world_image_fields_from_mapping(world_base)
        return {
            "name": _str(world_base.get("name")),
            "description": _str(world_base.get("description")),
            "genre": _str(world_base.get("genre")),
            "era": _str(world_base.get("era")),
            "difficulty": world_base.get("difficulty", 3),
            "estimated_time": _str(world_base.get("estimated_time")) or "30-60分钟",
            "base_setting": _str(world_base.get("base_setting")),
            "free_setting": _str(free_setting),
            "cover_image": images["cover_image"] or None,
            "hero_image": images["hero_image"] or None,
            "locations": [
                {"name": _str(loc.get("name")), "description": _str(loc.get("description"))}
                for loc in _ensure_list(world_base.get("locations"))
                if isinstance(loc, dict) and loc.get("name")
            ],
            "world_characters": world_characters,
        }
