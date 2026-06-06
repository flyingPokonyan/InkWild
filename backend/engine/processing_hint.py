from __future__ import annotations


_PHASE_FLAVORS: dict[str, str] = {
    "directing": "幕后传来一阵低语，剧本正在被重新翻动",
    "thinking": "周围一时安静下来，像是在等你下一步动作",
    "narrating": "幕布缓缓拉开",
}


def _clean_names(involved_npcs: list[str]) -> list[str]:
    names: list[str] = []
    for npc_name in involved_npcs:
        cleaned = str(npc_name).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if "director" in lowered or "npc agent" in lowered:
            continue
        if cleaned not in names:
            names.append(cleaned)
    return names


def build_processing_hint(
    involved_npcs: list[str],
    current_location: str | None = None,
) -> dict[str, object]:
    focus_npcs = _clean_names(involved_npcs)

    if len(focus_npcs) == 1:
        flavor = f"{focus_npcs[0]}像是想起了什么"
    elif len(focus_npcs) == 2:
        flavor = f"{focus_npcs[0]}和{focus_npcs[1]}似乎在交换眼神"
    elif current_location:
        flavor = f"{current_location}里一时安静下来，像是在等你看清局势"
    else:
        flavor = "周围一时安静下来，像是在等你下一步动作"

    return {
        "type": "processing",
        "phase": "thinking",
        "focus_npcs": focus_npcs,
        "flavor": flavor,
        "kind": "phase",
    }


def build_phase_hint(
    phase: str,
    current_location: str | None = None,
) -> dict[str, object]:
    """Build a generic processing hint for a non-NPC pipeline phase.

    Used for early progress indicators (e.g. "directing" before the Director call)
    so the UI does not stay silent while the slowest agents run.
    """
    flavor = _PHASE_FLAVORS.get(phase, "世界正在酝酿新的动静")
    if phase == "directing" and current_location:
        flavor = f"{current_location}里气氛微微一变，幕后正在做出选择"

    return {
        "type": "processing",
        "phase": phase,
        "focus_npcs": [],
        "flavor": flavor,
        "kind": "phase",
    }


def build_per_npc_focus_hint(npc_name: str, focus: str) -> dict[str, object]:
    """Build a processing hint that surfaces Director's per-NPC focus verbatim.

    跟 build_processing_hint 不同：flavor 直接用 Director 返回的 focus 文本，
    不走固定模板。Director 已经为每个 active NPC 生成了带情境的 focus
    描述（"思考如何回应明远的质疑" / "准备陈述守夜人时辰"），这本身就是
    有信息量的非套路文案。

    See docs/plans/narrator-simplification-2026-05.md T5.
    """
    name = str(npc_name).strip()
    cleaned_focus = str(focus).strip()
    if not name or not cleaned_focus:
        flavor = cleaned_focus or "正在斟酌"
    else:
        flavor = f"{name}{cleaned_focus}"
    return {
        "type": "processing",
        "phase": "thinking",
        "focus_npcs": [name] if name else [],
        "flavor": flavor,
        "kind": "per_npc",
    }
