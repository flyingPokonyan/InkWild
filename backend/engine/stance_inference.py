"""Initial NPC→player stance inference.

At session start the player picks a rich playable character, but NPCs carry no
authored relation toward them — the world generator excludes the player from
``initial_peer_relations`` by design (see character_roster_builder), so every NPC
would otherwise open at a flat ``trust=3 / 正常`` toward the player and warm up
generically.

This module makes one cheap LLM call at session start to infer each NPC's
*opening* attitude toward the player — derived from the player's PUBLIC identity
(name + description) × the NPC's own profile — so a rival starts guarded, an ally
starts warm, a subordinate starts deferential. The result seeds
``game_state.npc_relations`` and flows through the existing NPC prompt rendering
(``## 你与玩家的关系``) with no other changes.

Only public identity is used; the player's inner persona (personality/secret) is
never fed. Any failure degrades silently to the flat default — no regression.
"""
from __future__ import annotations

import json as _json

import structlog

logger = structlog.get_logger()

# Matches the in-game trust scale (state_manager clamps trust to [0, 10]; 3 is
# the neutral stranger default).
_TRUST_MIN, _TRUST_MAX, _TRUST_DEFAULT = 0, 10, 3

# Only infer stances for the most narratively-important NPCs. Big IP worlds carry
# 30+ characters; asking for all of them (a) blows past the token budget and
# truncates the JSON (→ 0 parsed) and (b) wastes tokens on bit-players the player
# won't meet. The rest fall back to the flat neutral default, which is fine for
# minor characters. Ranked by WorldCharacter.narrative_weight.
_STANCE_MAX_NPCS = 12

STANCE_SYSTEM = (
    "你在为一局互动叙事初始化每个 NPC 对玩家的【开局态度】。"
    "给你玩家扮演角色的公开身份，以及每个 NPC 的画像。"
    "请站在每个 NPC 的立场，判断在故事刚开始、ta 还没和玩家发生任何新互动时，"
    "本就对玩家抱有的态度。\n"
    "- trust：0-10 整数。3=萍水相逢的陌生人；熟识/盟友/恩人更高(6-9)；"
    "宿敌/利益冲突/心怀戒备更低(0-2)；点头之交 3-5。\n"
    "- mood：一个中文词，ta 见到玩家时的情绪基调（如 正常/亲近/戒备/敌意/敬畏/愧疚/暧昧/疏离）。\n"
    "- note：一句话（不超过 25 字），从该 NPC 视角说明 ta 为何这样看待玩家。\n"
    "只输出 JSON，不要任何解释：\n"
    '{"stances":[{"npc":"名字","trust":3,"mood":"正常","note":"……"}, ...]}\n'
    "只为给定名单里的 NPC 作答，npc 名字必须与名单完全一致照抄。"
)


def build_stance_messages(player_public: dict, npcs: list[dict]) -> list[dict]:
    name = str(player_public.get("name") or "玩家").strip()
    desc = str(player_public.get("description") or "").strip()
    lines = [
        f"【玩家扮演的角色】{name}",
        desc or "（无更多公开信息）",
        "",
        "【NPC 名单与画像】",
    ]
    for n in npcs:
        nm = str(n.get("name") or "").strip()
        if not nm:
            continue
        bits = "；".join(
            b for b in (str(n.get("personality") or "").strip(), str(n.get("description") or "").strip()) if b
        )
        lines.append(f"- {nm}：{bits}" if bits else f"- {nm}")
    return [{"role": "user", "content": "\n".join(lines)}]


def parse_stances(raw: str, valid_names: set[str]) -> dict[str, dict]:
    """Pure parse + validate. Returns ``{npc_name: {trust, mood, note}}`` for
    known names with sane values only. Never raises; garbage → ``{}``."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw[:-3] if raw.rstrip().endswith("```") else raw
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = _json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, dict] = {}
    for item in parsed.get("stances") or []:
        if not isinstance(item, dict):
            continue
        nm = str(item.get("npc") or "").strip()
        if nm not in valid_names:
            continue
        try:
            trust = int(item.get("trust", _TRUST_DEFAULT))
        except (TypeError, ValueError):
            trust = _TRUST_DEFAULT
        trust = max(_TRUST_MIN, min(_TRUST_MAX, trust))
        mood = (str(item.get("mood") or "").strip() or "正常")[:10]
        note = str(item.get("note") or "").strip()[:40]
        out[nm] = {"trust": trust, "mood": mood, "note": note}
    return out


async def infer_initial_stances(
    llm_router, player_public: dict | None, npcs: list[dict]
) -> dict[str, dict]:
    """One-shot opening-stance inference. ``npcs`` items: ``{name, personality,
    description}``. Returns ``{}`` on any failure (caller falls back to the flat
    default), so this is safe to call unconditionally behind a feature flag."""
    if not player_public or not npcs:
        return {}
    # Cap to the most important NPCs (by narrative_weight) so the JSON fits the
    # token budget and we don't pay for bit-players the player won't meet.
    ranked = sorted(npcs, key=lambda n: -(n.get("narrative_weight") or 0))[:_STANCE_MAX_NPCS]
    valid = {str(n.get("name") or "").strip() for n in ranked if n.get("name")}
    valid.discard("")
    if not valid:
        return {}
    text_parts: list[str] = []
    try:
        async for event in llm_router.stream_json(
            messages=build_stance_messages(player_public, ranked),
            system=STANCE_SYSTEM,
            max_tokens=2048,
        ):
            if event.get("type") == "text_delta":
                text_parts.append(event.get("text", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("stance_inference_failed", error=str(exc))
        return {}
    stances = parse_stances("".join(text_parts), valid)
    logger.info("stance_inference_done", npc_count=len(valid), stance_count=len(stances))
    return stances
