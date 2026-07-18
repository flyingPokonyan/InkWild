"""Single constrained Director for world generation planning."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from schemas.lore_pack import LoreDimension
from schemas.world_generation import WorldScaleClass, WorldSpec, derive_scale_plan
from services.research_pack_builder import _collect_stream_text, _extract_json_from_text

logger = structlog.get_logger()

_COUNT_RE = re.compile(r"(\d+)\s*个\s*(?:角色|NPC|npc|人物|人)")

_DIRECTOR_SYSTEM = """你是互动叙事世界生成的总导演。你的权限严格受限：
只能在给定证据与安全规模下，选择世界规模档、最多 3 个主视角候选、创作重点和 lore 维度。
不能删除 must_have，不能把 active_roles_target 调低于安全基线，不能新增原作角色名，
不能执行工具或自由循环。

输出严格 JSON：
{"scale_class":"compact|standard|epic","active_roles_target":整数,
 "protagonist_candidates":["给定角色原名"],"creative_focus":["短语"],
 "lore_dimensions":[{"key":"英文机器标识","name":"中文名","why_relevant":"一句理由"}]}
只输出 JSON。"""


def _fallback_lore_dimensions(ip_pack: Any | None, scale_class: WorldScaleClass) -> list[LoreDimension]:
    candidates = [
        LoreDimension(key="society_rules", name="社会秩序", why_relevant="约束角色行动与身份"),
        LoreDimension(key="history_conflicts", name="历史冲突", why_relevant="提供当前矛盾的因果背景"),
        LoreDimension(key="geography", name="地理与空间", why_relevant="连接地点、势力与事件"),
        LoreDimension(key="power_system", name="能力与资源规则", why_relevant="界定角色能做什么及代价"),
        LoreDimension(key="culture_lingo", name="文化与语言", why_relevant="保持时代质感和表达一致"),
    ]
    if getattr(ip_pack, "factions", None):
        candidates.insert(
            0,
            LoreDimension(key="faction_politics", name="势力格局", why_relevant="原作存在明确势力关系"),
        )
    if getattr(ip_pack, "iconic_objects", None):
        candidates.append(
            LoreDimension(key="iconic_objects", name="标志性器物", why_relevant="承载原作识别度与规则"),
        )
    target = {
        WorldScaleClass.COMPACT: 3,
        WorldScaleClass.STANDARD: 4,
        WorldScaleClass.EPIC: 5,
    }[scale_class]
    return candidates[:target]


class WorldGenerationDirector:
    def __init__(self, llm: Any | None) -> None:
        self.llm = llm

    async def plan(
        self,
        *,
        generation_run_id: str,
        description: str,
        genre: str,
        era: str,
        fidelity_mode: str,
        recognized_ip_name: str | None,
        ip_pack: Any | None,
    ) -> WorldSpec:
        ip_name = (getattr(ip_pack, "ip_name", None) or recognized_ip_name or "").strip() or None
        explicit = None
        match = _COUNT_RE.search(description or "")
        if match:
            explicit = max(3, min(60, int(match.group(1))))

        canon = list(ip_pack.canon_character_names()) if ip_pack is not None else []
        must_have = list(ip_pack.must_have_character_names()) if ip_pack is not None else []
        places = len(getattr(ip_pack, "places", []) or []) if ip_pack is not None else 0
        scale = derive_scale_plan(
            canon_character_count=len(canon),
            must_have_count=len(must_have),
            explicit_character_count=explicit,
            place_count=places,
        )
        protagonists: list[str] = []
        creative_focus: list[str] = []
        lore_dimensions = _fallback_lore_dimensions(ip_pack, scale.scale_class)

        # One bounded planning call.  A bad/slow answer fails open to the
        # deterministic scale plan; it never starts an autonomous loop.
        if self.llm is not None:
            user = json.dumps(
                {
                    "description": description[:1800],
                    "genre": genre,
                    "era": era,
                    "fidelity_mode": fidelity_mode,
                    "ip_name": ip_name,
                    "canon_note": getattr(ip_pack, "canon_note", None),
                    "safe_baseline": scale.model_dump(mode="json"),
                    "must_have": must_have,
                    "canon_characters": canon,
                    "playable_archetypes": getattr(ip_pack, "playable_archetypes", []),
                },
                ensure_ascii=False,
            )
            try:
                text = await _collect_stream_text(
                    self.llm,
                    system=_DIRECTOR_SYSTEM,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=1024,
                )
                data = _extract_json_from_text(text) or {}
                requested_target = int(data.get("active_roles_target") or scale.active_roles_target)
                requested_class = str(data.get("scale_class") or "")
                order = {
                    WorldScaleClass.COMPACT: 0,
                    WorldScaleClass.STANDARD: 1,
                    WorldScaleClass.EPIC: 2,
                }
                try:
                    candidate_class = WorldScaleClass(requested_class)
                    if order[candidate_class] >= order[scale.scale_class]:
                        expanded = derive_scale_plan(
                            canon_character_count=len(canon),
                            must_have_count=len(must_have),
                            explicit_character_count=max(requested_target, scale.active_roles_target),
                            place_count=places,
                        )
                        if order[expanded.scale_class] >= order[scale.scale_class]:
                            scale = expanded
                except ValueError:
                    pass
                # Director may expand within the selected band, never shrink.
                scale.active_roles_target = min(
                    max(scale.active_roles_target, requested_target), scale.active_roles_max
                )

                allowed = set(canon)
                for name in data.get("protagonist_candidates") or []:
                    if isinstance(name, str) and name and (not allowed or name in allowed):
                        if name not in protagonists:
                            protagonists.append(name)
                creative_focus = [
                    str(item).strip()[:80]
                    for item in (data.get("creative_focus") or [])
                    if str(item).strip()
                ][:6]
                parsed_dimensions: list[LoreDimension] = []
                for item in data.get("lore_dimensions") or []:
                    if not isinstance(item, dict):
                        continue
                    try:
                        parsed_dimensions.append(LoreDimension.model_validate(item))
                    except Exception:  # noqa: BLE001
                        continue
                if parsed_dimensions:
                    target = {
                        WorldScaleClass.COMPACT: 3,
                        WorldScaleClass.STANDARD: 4,
                        WorldScaleClass.EPIC: 5,
                    }[scale.scale_class]
                    lore_dimensions = parsed_dimensions[:target]
            except Exception as exc:  # noqa: BLE001
                logger.warning("world_director_plan_failed", error=str(exc))

        return WorldSpec(
            generation_run_id=generation_run_id,
            description=description,
            genre=genre,
            era=era,
            fidelity_mode=fidelity_mode,
            ip_name=ip_name,
            canon_note=getattr(ip_pack, "canon_note", None),
            must_have_characters=must_have,
            canon_characters=canon,
            protagonist_candidates=protagonists,
            creative_focus=creative_focus,
            lore_dimensions=lore_dimensions,
            scale=scale,
            # Budget carries headroom for the inline quality gate: one semantic
            # judge call every run + one bounded events revise when the judge
            # flags beat-duplication / timeline gaps. Quality is the goal here,
            # so the convergence budget deliberately buys that headroom.
            text_call_budget={
                WorldScaleClass.COMPACT: 20,
                WorldScaleClass.STANDARD: 24,
                WorldScaleClass.EPIC: 28,
            }[scale.scale_class],
        )
