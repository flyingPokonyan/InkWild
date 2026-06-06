"""Structural evolution ledger (spec §4): overlay committed structural facts
onto the seed spine, and commit new facts with a bounded one-order cascade.

Genre-neutral: behavior is keyed only by `kind` (a mechanical-consequence
enum), never by narrative category.
"""
from __future__ import annotations

import structlog

from engine.state_manager import GameState

logger = structlog.get_logger()

# Mechanical-consequence kinds (spec §2.2). Open/extensible: a new kind is
# defined by the one-order cascade it needs, not by plot category.
STRUCTURAL_KINDS = {
    "entity_removed",       # death / permanent exit: drop from presence, mark gone
    "entity_role_changed",  # title / role / status change
    "relation_redefined",   # allegiance / alliance / relationship reframing
    "world_fact_changed",   # base_setting / location / world-truth flip
}

# Facts that describe an entity (rendered into npc_descriptions); the rest
# render into base_setting.
_ENTITY_KINDS = {"entity_removed", "entity_role_changed", "relation_redefined"}


def apply_structural_overlay(world_data: dict, structural_facts: list[dict]) -> dict:
    """Return a shallow copy of *world_data* with the ledger folded onto the
    seed spine. Entity facts append to ``npc_descriptions``; world facts append
    to ``base_setting``. Pure: never mutates the input. No-op (returns the same
    object) when no facts so the prefix-cache snapshot stays byte-identical to
    the seed.
    """
    if not structural_facts:
        return world_data
    overlaid = dict(world_data)
    entity_lines: list[str] = []
    world_lines: list[str] = []
    for fact in structural_facts:
        text = str(fact.get("fact_text") or "").strip()
        if not text:
            continue
        if str(fact.get("kind")) in _ENTITY_KINDS:
            entity_lines.append(f"- {text}")
        else:
            world_lines.append(f"- {text}")
    if world_lines:
        overlaid["base_setting"] = (
            str(world_data.get("base_setting") or "")
            + "\n\n## 已发生的结构性变化（视为既成事实）\n"
            + "\n".join(world_lines)
        )
    if entity_lines:
        overlaid["npc_descriptions"] = (
            str(world_data.get("npc_descriptions") or "")
            + "\n\n## 人物状态的结构性变化（视为既成事实，优先于上文人设）\n"
            + "\n".join(entity_lines)
        )
    return overlaid


def commit_structural_fact(state: GameState, fact: dict) -> bool:
    """Append a committed structural fact to the ledger and apply its bounded
    one-order cascade. Returns False (no-op) if a fact with the same fact_key
    and identical fact_text is already committed (idempotent). Unknown kinds
    are logged and still recorded (overlay renders fact_text), but apply no
    mechanical cascade.

    One-order only (spec §3.3, non-goal §7): no N-order ripple. NPCs improvise
    from the updated spine on subsequent turns.
    """
    fact_key = str(fact.get("fact_key") or "").strip()
    fact_text = str(fact.get("fact_text") or "").strip()
    if not fact_text:
        return False
    kind = str(fact.get("kind") or "").strip()
    target_ref = (str(fact.get("target_ref") or "").strip() or None)

    for existing in state.structural_facts:
        if existing.get("fact_key") == fact_key and existing.get("fact_text") == fact_text:
            return False

    if kind not in STRUCTURAL_KINDS:
        logger.warning("structural_commit_unknown_kind", kind=kind, fact_key=fact_key)

    entry = {
        "fact_key": fact_key,
        "fact_text": fact_text,
        "kind": kind,
        "target_ref": target_ref,
        "effective_round": int(getattr(state, "round_number", 0) or 0),
        "provenance": str(fact.get("provenance") or "authored_milestone"),
    }
    state.structural_facts.append(entry)

    # --- one-order cascade by kind ---
    if kind == "entity_removed" and target_ref:
        state.npc_locations.pop(target_ref, None)
        # Freeze the relation record (kept for history; overlay marks them gone).
        if target_ref in state.npc_relations:
            state.npc_relations[target_ref]["frozen"] = True
    # entity_role_changed / relation_redefined / world_fact_changed: rendered by
    # the overlay (and relation note); no further deterministic state mutation.

    logger.info(
        "structural.committed",
        fact_key=fact_key, kind=kind, target_ref=target_ref,
        round_number=entry["effective_round"], provenance=entry["provenance"],
    )
    return True
