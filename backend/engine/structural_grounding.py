"""Grounding predicate for structural claims (spec 2026-06-03 grounded
structural evolution).

A structural claim PROMOTES to a world fact only if its premise is grounded in
**structured world state** — never the player's words, never ambient narration,
never bystander compliance. The discriminator (spec §3.4): the enabling action
must come from the entity whose authority/consent the change actually requires,
present and acting via its *own* agent.

INV-1 is enforced by the signature: this module only ever receives committed
facts + this turn's per-NPC structured actions. There is no player_input or
narration parameter, so prose can never be a grounding source.
"""
from __future__ import annotations

import json as _json

import structlog

logger = structlog.get_logger()

_VALID_KINDS = {"entity_removed", "entity_role_changed", "relation_redefined", "world_fact_changed"}
_VALID_PREMISE_TYPES = {"authority_decree", "mutual_consent", "prerequisite", "physical_act"}

CLAIM_SYSTEM = (
    "你是结构主张解析器。玩家本回合的输入里**断言了一项『世界底色（结构事实）』的改变**"
    "（身份/地位、存在/在场、权力/归属/关系定性、重大世界真相）。\n"
    "你只做**解析**，绝不判断它真不真、合不合法——那由后续世界状态决定。\n"
    "解析出：这是什么结构变更 + 它**赖以成立的前提依赖哪个实体**（premise.required_entity"
    "=要让这个变更真成立，必须由谁的权威/同意/行动促成；台外被搬出的权威也照实填）。\n"
    "premise.type：authority_decree(搬出某权威的旨意/任命) | mutual_consent(需对方当事人同意，如结盟) | "
    "prerequisite(靠既成事实链) | physical_act(强行动作，无台外权威)。\n"
    "只输出 JSON，不要解释：\n"
    '{"is_claim": true/false, "claim_key": "稳定键如 char.role.x", "claim_text": "用人话陈述被声称的既成事实",'
    ' "kind": "entity_removed|entity_role_changed|relation_redefined|world_fact_changed",'
    ' "target_ref": "涉及实体名", "premise": {"type": "...", "required_entity": "促成它所需的实体或null",'
    ' "requires": ["可选:所依赖的已有事实key"], "detail": "一句话"}}'
)

ASSENT_SYSTEM = (
    "你是单实体动作判读器。只看**这一个角色本人**这回合的真实动作/台词，判断："
    "ta 是否**以自身意志真的促成/认可了**所描述的那项结构变更？\n"
    "铁律：只算 ta 本人主动促成/明确认可才 true；旁观、敷衍、被胁迫的表面顺从、沉默、回避、"
    "或只是别人替 ta 说话 → false。拿不准 → false。\n"
    '只输出 JSON：{"assents": true/false}'
)


def interpret_assent(raw: object) -> bool:
    """Pure parse of the narrow assent read. Conservative: anything unparseable
    or not an explicit true → False (no assent → ungrounded, the safe default)."""
    text = (str(raw) if raw is not None else "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text[:-3] if text.rstrip().endswith("```") else text
    try:
        start, end = text.find("{"), text.rfind("}")
        parsed = _json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:  # noqa: BLE001
        return False
    return isinstance(parsed, dict) and parsed.get("assents") is True


async def _collect(llm_router, system: str, messages: list[dict], max_tokens: int) -> str:
    parts: list[str] = []
    async for event in llm_router.stream_json(messages=messages, system=system, max_tokens=max_tokens):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts)


async def extract_claim(llm_router, player_input: str, scene_context: str = "") -> dict | None:
    """Cheap-LLM parse of the player's structural assertion → claim+premise.
    Any failure → None (no claim recorded; safe under-commit)."""
    msg = [{"role": "user", "content": "\n".join([
        "【场景背景（仅供理解，可空）】", (scene_context or "（无）").strip(),
        "【玩家本回合输入】", (player_input or "（无）").strip(),
    ])}]
    try:
        out = await _collect(llm_router, CLAIM_SYSTEM, msg, max_tokens=512)
    except Exception as exc:  # noqa: BLE001
        logger.warning("structural_claim_parse_failed", error=str(exc))
        return None
    return parse_claim(out)


async def check_entity_assent(
    llm_router, entity_name: str, entity_action_text: str, claim_text: str
) -> bool:
    """Narrow LLM read of ONLY the required entity's own action (INV-1: never the
    player's words / narration / bystanders). Any failure → False."""
    msg = [{"role": "user", "content": "\n".join([
        f"【被声称的结构变更】{claim_text}",
        f"【角色】{entity_name}",
        f"【{entity_name} 本人这回合的动作/台词】", (entity_action_text or "（无）").strip(),
    ])}]
    try:
        out = await _collect(llm_router, ASSENT_SYSTEM, msg, max_tokens=128)
    except Exception as exc:  # noqa: BLE001
        logger.warning("structural_assent_check_failed", error=str(exc))
        return False
    return interpret_assent(out)


def parse_claim(raw: object) -> dict | None:
    """Pure parse of the LLM's reading of the player's structural assertion into
    a claim + premise. Never raises. Returns None when there is no structural
    claim (unparseable / is_claim=false / no claim_text) — the safe under-commit
    default (nothing recorded, nothing grounded).
    """
    text = (str(raw) if raw is not None else "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text[:-3] if text.rstrip().endswith("```") else text
    try:
        start, end = text.find("{"), text.rfind("}")
        parsed = _json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(parsed, dict) or parsed.get("is_claim") is False:
        return None
    return normalize_claim(parsed)


def normalize_claim(parsed: object) -> dict | None:
    """Validate/normalize an already-parsed claim dict (from parse_claim's JSON
    tail, or from the Director's emitted structural_claim object) into the
    canonical shape. Returns None when there is no usable claim (no claim_text)."""
    if not isinstance(parsed, dict):
        return None
    claim_text = str(parsed.get("claim_text") or "").strip()
    if not claim_text:
        return None
    kind = str(parsed.get("kind") or "").strip()
    if kind not in _VALID_KINDS:
        kind = "world_fact_changed"
    raw_premise = parsed.get("premise") if isinstance(parsed.get("premise"), dict) else {}
    ptype = str(raw_premise.get("type") or "").strip()
    if ptype not in _VALID_PREMISE_TYPES:
        ptype = "authority_decree"  # safe: routes to required-entity check → ungrounded if absent
    premise = {
        "type": ptype,
        "required_entity": (str(raw_premise.get("required_entity") or "").strip() or None),
        "requires": [str(k).strip() for k in (raw_premise.get("requires") or []) if str(k).strip()],
        "detail": str(raw_premise.get("detail") or "").strip(),
    }
    return {
        "claim_key": str(parsed.get("claim_key") or "").strip(),
        "claim_text": claim_text,
        "kind": kind,
        "target_ref": (str(parsed.get("target_ref") or "").strip() or None),
        "premise": premise,
    }


def record_or_refresh_claim(state, claim: dict) -> dict:
    """Record an in-play structural claim, or refresh it if already tracked.

    Dedupe is by ``claim_key`` (INV-2): re-asserting the same structural change —
    however the player rephrases or escalates it — only bumps ``last_seen_round``
    and never appends a duplicate, so repetition can never accumulate toward
    grounding. Returns the stored entry.
    """
    rnd = int(getattr(state, "round_number", 0) or 0)
    kind = str(claim.get("kind") or "").strip()
    target_ref = (str(claim.get("target_ref") or "").strip() or None)
    # Derive a stable key when none given, so keyless claims don't all collapse
    # into one entry (#3).
    key = str(claim.get("claim_key") or "").strip() or f"{kind}:{target_ref}"

    for existing in state.structural_claims:
        if existing.get("claim_key") == key:
            existing["last_seen_round"] = rnd
            # latest phrasing/text is kept for drama continuity; status untouched
            if claim.get("claim_text"):
                existing["claim_text"] = str(claim["claim_text"])
            return existing

    entry = {
        "claim_key": key,
        "claim_text": str(claim.get("claim_text") or "").strip(),
        "kind": kind,
        "target_ref": target_ref,
        "premise": claim.get("premise") or {},
        "status": "in_play",
        "round_made": rnd,
        "last_seen_round": rnd,
    }
    state.structural_claims.append(entry)
    return entry


def build_structural_claims_context(
    structural_claims: list[dict], current_round: int, window: int = 3
) -> str:
    """Reckoning context (H5 consumption) fed to the Director as per-turn user
    context — NOT the spine. Lists the player's still-unresolved structural
    assertions (in_play / exposed, seen within *window* rounds) so the world
    keeps visibly NOT honoring baseless claims and can escalate (probe / ignore
    / report / expose). Grounded claims are facts now → excluded. Returns "" when
    nothing is outstanding.
    """
    lines: list[str] = []
    for c in structural_claims or []:
        status = c.get("status")
        if status not in ("in_play", "exposed"):
            continue
        if int(c.get("last_seen_round") or 0) < current_round - window:
            continue
        text = str(c.get("claim_text") or "").strip()
        if not text:
            continue
        if status == "exposed":
            lines.append(f"- [已当面揭穿] 「{text}」——此事并无其实，世界与相关人等不予承认。")
        else:
            lines.append(f"- [悬而未决] 「{text}」——玩家如此声称，但至今无实据支撑，世界并未照此改变。")
    if not lines:
        return ""
    return (
        "【未了结的越界声称（世界并未认可）】\n"
        "以下是玩家此前声称、但世界并未据其改变的结构事实。继续按『世界未予承认』处理；"
        "相关在场 NPC 可据此自然反应——追问实据、不予理会、暗中上报、或在场权威当面拆穿，按各自性格与立场来：\n"
        + "\n".join(lines)
    )


def is_grounded(
    claim: dict, structural_facts: list[dict], turn_actions: list[dict]
) -> dict:
    """Deterministic skeleton of the grounding verdict.

    Returns ``{grounded, basis, reason, needs_assent_check, entity_action}``.
    When the required entity IS present and acting, the deterministic layer
    cannot tell assent from refusal — it flags ``needs_assent_check`` and hands
    that single entity's own action to the narrow LLM read (separate function).
    """
    premise = claim.get("premise") or {}
    required = premise.get("required_entity")

    # Compositional grounding: prerequisites already committed as facts. Gated to
    # premise.type=="prerequisite" so a (possibly mis-filled) requires list can
    # never bypass an authority/consent requirement (#1).
    requires = premise.get("requires") or []
    if premise.get("type") == "prerequisite" and requires:
        committed = {f.get("fact_key") for f in (structural_facts or [])}
        if all(key in committed for key in requires):
            return {
                "grounded": True,
                "basis": "prerequisite",
                "reason": None,
                "needs_assent_check": False,
                "entity_action": None,
            }
        return {
            "grounded": False,
            "basis": None,
            "reason": "prerequisite_unmet",
            "needs_assent_check": False,
            "entity_action": None,
        }

    if not required:
        return {
            "grounded": False,
            "basis": None,
            "reason": "no_required_entity",
            "needs_assent_check": False,
            "entity_action": None,
        }

    acting = {a.get("npc_name"): a for a in (turn_actions or [])}
    if required not in acting:
        return {
            "grounded": False,
            "basis": None,
            "reason": "required_entity_absent",
            "needs_assent_check": False,
            "entity_action": None,
        }

    return {
        "grounded": False,
        "basis": None,
        "reason": None,
        "needs_assent_check": True,
        "entity_action": acting[required],
    }
