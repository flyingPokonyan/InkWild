"""Script roster augmentation (反哺).

When a script is generated against an existing world, its events can only
reference characters already in the world roster (events_data_builder disables
``npc_intent_driven`` events whose ``npc_name`` is unknown, and silently filters
rumor knowers / mood changes). For a large IP world whose roster only
instantiated a subset of the canonical cast, the script LLM naturally reaches
for canonical characters that were never generated into the world — and those
references get gutted.

This module closes that gap **without mutating the world**: it back-fills the
missing canonical characters as *script-owned* NPCs (persisted on
``Script.local_characters``, unioned into the runtime roster by name at session
start). The world is never touched — no re-publish, no ownership crossing, no
moderation bypass.

Scope (v2, single path):
  - canonical-only: candidates come exclusively from the parent world's IP
    knowledge pack. No IP pack (original worlds / fidelity "none") → no
    augmentation (fabricating world-class characters is out of scope here).
  - capped per script (``max_additions``) and fail-soft: any failure returns
    [] and the script falls back to the old "locked to world roster" behaviour.

``is_world_scoped_addition`` is kept as a standalone policy so the future
"promote characters shared across scripts into the world" feature can reuse the
same judgement.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from schemas.character_v2 import Character, CharacterRosterEntry
from schemas.ip_knowledge_pack import IPKnowledgePack
from schemas.research_pack import IPCanon, Passage
from services.character_roster_builder import (
    _collect_stream_text,
    _extract_json_from_text,
    build_characters_in_batches,
)

logger = structlog.get_logger()

# Cap how many candidate names we feed the selector LLM, so a huge IP pack
# (hundreds of canonical names) doesn't blow up the prompt. Ranked by must_have
# first — the characters most likely to anchor a script.
_MAX_CANDIDATE_POOL = 60

_SELECT_SYSTEM = (
    "你在为一个【剧本】筛选它真正需要、但所属世界角色名册里【还没有】的原作角色。"
    "只能从候选清单里挑，禁止发明新名字。宁缺勿滥：只挑这个剧本剧情确实要用到的人，"
    "不确定就不挑。输出严格 JSON：{\"needed\":[\"角色名\",...]}（无则空数组）。"
)


def is_world_scoped_addition(name: str, ip_pack: IPKnowledgePack | None) -> bool:
    """是否允许把名为 *name* 的角色作为「世界级」角色补进剧本（反哺门槛）。

    当前策略：只放行原作 canonical 角色（命中 IP pack 角色清单）。一次性龙套 /
    杜撰角色不放行 —— 它们应留作旁白氛围，不进结构化名册。

    抽成独立策略，供将来「多剧本共用角色一键并入世界」复用同一判定。
    """
    if ip_pack is None:
        return False
    return name in {c.name for c in ip_pack.characters}


async def augment_script_roster(
    *,
    world_characters: list[Character],
    script_base: dict,
    outline: str,
    ip_pack: IPKnowledgePack | None,
    fidelity_mode: str,
    ip_canon: IPCanon,
    research_passages: list[Passage],
    locations: list[str],
    llm_router: Any,
    max_additions: int,
) -> list[Character]:
    """Return script-owned NPCs to back-fill (deduped vs world, never includes
    existing world characters). Empty on any failure or when not applicable."""
    if max_additions <= 0 or ip_pack is None or fidelity_mode not in ("strict", "loose"):
        return []
    if llm_router is None:
        return []

    existing_names = {c.name for c in world_characters if c.name}

    # Candidate pool = canonical characters the world roster lacks. must_have
    # first so the most load-bearing names survive the pool cap.
    pool = [
        c for c in ip_pack.characters
        if c.name and c.name not in existing_names
    ]
    pool.sort(key=lambda c: (not c.must_have, c.name))
    pool = pool[:_MAX_CANDIDATE_POOL]
    if not pool:
        return []

    try:
        needed = await _select_needed_canonical(
            pool=pool,
            script_base=script_base,
            outline=outline,
            llm_router=llm_router,
            max_additions=max_additions,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft, never block script gen.
        logger.warning("script_roster_augment_select_failed", error=str(exc))
        return []

    # Gate + intersect with pool (the LLM must not invent names) + dedup vs world.
    pool_names = {c.name for c in pool}
    selected = [
        n for n in needed
        if n in pool_names
        and n not in existing_names
        and is_world_scoped_addition(n, ip_pack)
    ]
    # preserve order, dedup, cap
    seen: set[str] = set()
    ordered: list[str] = []
    for n in selected:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    ordered = ordered[:max_additions]
    if not ordered:
        return []

    role_tag_by_name = {
        c.name: (getattr(c, "role_in_story", "") or "原作角色") for c in pool
    }
    roster_entries = [
        CharacterRosterEntry(
            name=n,
            role_tag=role_tag_by_name.get(n, "原作角色"),
            faction="",
            is_image_target=False,  # 外挂角色一律 NPC，不进可玩视角
        )
        for n in ordered
    ]

    try:
        new_chars = await build_characters_in_batches(
            roster_entries,
            description=outline or str(script_base.get("script_setting", "")),
            ip_canon=ip_canon,
            locations=locations,
            passages=research_passages,
            llm_router=llm_router,
            ip_pack=ip_pack,
            fidelity_mode=fidelity_mode,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft.
        logger.warning("script_roster_augment_detail_failed", error=str(exc))
        return []

    # Belt-and-suspenders: never let a back-filled character be playable, and
    # drop any that collided with an existing world name after detailing.
    out: list[Character] = []
    seen_out: set[str] = set()
    for c in new_chars:
        if not c.name or c.name in existing_names or c.name in seen_out:
            continue
        c.is_image_target = False
        out.append(c)
        seen_out.add(c.name)

    logger.info(
        "script_roster_augmented",
        requested=len(ordered),
        produced=len(out),
        names=[c.name for c in out],
    )
    return out[:max_additions]


async def _select_needed_canonical(
    *,
    pool: list[Any],
    script_base: dict,
    outline: str,
    llm_router: Any,
    max_additions: int,
) -> list[str]:
    """One cheap LLM call: from *pool*, pick the canonical characters THIS
    script needs. Returns a list of names (subset of pool, ≤ max_additions)."""
    def _brief(c: Any) -> str:
        # IPCharacter has no free-text description; compose a short hint from
        # role + relation + traits/arc so the selector knows who each name is.
        bits = [
            getattr(c, "role_in_story", "") or "",
            getattr(c, "relation_to_protagonist", "") or "",
            "、".join(getattr(c, "traits", []) or [])[:30],
            (getattr(c, "story_arc", "") or "")[:40],
        ]
        return "；".join(b for b in bits if b)[:80]

    candidate_lines = "\n".join(f"- {c.name}：{_brief(c)}" for c in pool)
    user_content = (
        f"剧本名称：{script_base.get('name', '')}\n"
        f"剧本简介：{script_base.get('description', '')}\n"
        f"剧情切入 / 大纲：{(outline or '')[:400]}\n"
        f"核心真相：{str(script_base.get('script_setting', ''))[:400]}\n\n"
        f"候选原作角色（世界名册里还没有的）：\n{candidate_lines}\n\n"
        f"最多挑 {max_additions} 个这个剧本真正要用到的角色。"
    )
    text = await _collect_stream_text(
        llm_router,
        system=_SELECT_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=512,
    )
    data = _extract_json_from_text(text)
    if not isinstance(data, dict):
        return []
    raw = data.get("needed") or []
    if not isinstance(raw, list):
        return []
    # No truncation here: the caller applies the hard cap AFTER filtering out
    # non-canonical / already-present names, so capping pre-filter would starve
    # the result. ``max_additions`` is communicated to the LLM via the prompt.
    return [str(n).strip() for n in raw if isinstance(n, str) and str(n).strip()]
