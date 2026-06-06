from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.game import GameSession

logger = structlog.get_logger()

TIME_SLOTS = ["上午", "下午", "傍晚", "夜晚", "深夜"]

# Rejected by append_discovered_clue: Director sometimes outputs `clue_NNN`
# id placeholder strings as new_clue text (e.g. observed on HP playthrough
# 2026-05-27: clue_004..008 leaked into discovered_clues with content="clue_004").
# Server assigns ids; Director provides narrative content only.
_CLUE_ID_PLACEHOLDER_RE = re.compile(r"^clue[_\-]\d+$", re.IGNORECASE)
_MIN_CLUE_CONTENT_LEN = 5


def append_discovered_clue(
    discovered_clues: list[dict],
    content: object,
    *,
    found_at: str,
    source: str,
) -> bool:
    """Validate and append a clue to ``discovered_clues``. Returns True if added.

    Single chokepoint for every write site (Director new_clues, events_data
    spawn_clues, Director intent-triggered events). Rejects non-strings,
    too-short text, and ``clue_NNN`` id placeholders — these have been
    observed to poison the player-facing clue list and case_board.
    """
    if not isinstance(content, str):
        logger.debug("clue_rejected_non_string", source=source, value=repr(content)[:80])
        return False
    text = content.strip()
    if len(text) < _MIN_CLUE_CONTENT_LEN:
        logger.debug("clue_rejected_too_short", source=source, text=text)
        return False
    if _CLUE_ID_PLACEHOLDER_RE.match(text):
        logger.debug("clue_rejected_id_placeholder", source=source, text=text)
        return False
    clue_id = f"clue_{len(discovered_clues) + 1:03d}"
    discovered_clues.append({"id": clue_id, "content": text, "found_at": found_at})
    return True

# Phase 1.B.5 — cap how many recent typed player actions we keep in game_state.
# 20 covers cross-turn NPC awareness (last 5-8 are rendered in NPC prompts;
# the rest are kept for analytics / future NPC reflection inputs) without
# letting state grow unbounded over very long sessions.
PLAYER_ACTIONS_HISTORY_LIMIT = 20


class StaleVersionError(Exception):
    """Raised when a session save races with a newer committed version."""


@dataclass
class GameState:
    current_time: str
    current_location: str
    player_inventory: list[str] = field(default_factory=list)
    discovered_clues: list[dict] = field(default_factory=list)
    npc_relations: dict[str, dict] = field(default_factory=dict)
    triggered_events: list[str] = field(default_factory=list)
    visited_locations: list[str] = field(default_factory=list)
    time_index: int = 0
    round_number: int = 0
    rounds_since_last_clue: int = 0
    last_stage_summary_round: int = 0
    # Phase 2.A.4 — consecutive rounds the arc has been labelled `climax`.
    # Drives the script-mode resolution controller (soft pressure → explicit
    # final choice → forced ending). Always 0 / unused in free mode.
    rounds_in_climax: int = 0

    # World engine enhancement fields
    npc_intents: dict[str, dict] = field(default_factory=dict)
    info_items: list[dict] = field(default_factory=list)
    npc_locations: dict[str, str] = field(default_factory=dict)
    narrative_arc: dict = field(default_factory=dict)
    world_conflicts: list[dict] = field(default_factory=list)
    flags: dict[str, object] = field(default_factory=dict)
    last_compressed_round: int = 0
    case_board: dict = field(default_factory=dict)
    # Phase 1.B.5 — typed structured player actions for cross-turn NPC
    # awareness. Each entry: {round, action_type, target_npc, target, summary}.
    # Director emits one structured action per turn (in DirectorResult); the
    # orchestrator appends it here, capped to the most recent
    # PLAYER_ACTIONS_HISTORY_LIMIT entries to keep state size bounded.
    player_actions: list[dict] = field(default_factory=list)

    # events_data trigger deduplication: set of event ids already triggered.
    triggered_event_ids: set[str] = field(default_factory=set)

    # world_state: free-form key/value pairs updated by events_data effects.
    world_state: dict = field(default_factory=dict)

    # Structural evolution ledger (spec §4). Each entry is a committed
    # structural fact overlaid onto the seed spine at prompt-build time:
    # {fact_key, fact_text, kind, target_ref, effective_round, provenance}.
    # Persisted (JSON-safe). Empty for worlds/sessions with no structural change.
    structural_facts: list[dict] = field(default_factory=list)

    # Structural CLAIM ledger (spec 2026-06-03 grounded evolution). Claims are
    # asserted/in-play structural changes that drive drama but NEVER overlay the
    # spine — only a grounded claim PROMOTES into structural_facts. Each entry:
    # {claim_key, claim_text, kind, target_ref, premise, status, round_made,
    #  last_seen_round}. status ∈ in_play|grounded|exposed|abandoned. (INV-3:
    # apply_structural_overlay never reads this list.)
    structural_claims: list[dict] = field(default_factory=list)

    # Runtime v2 — last round each NPC was in active_npcs. Used to decide if
    # a catch-up call is needed when an NPC re-enters the scene. Absent NPCs
    # default to round_number - 1 (treated as "just active", skip catch-up).
    last_active_round: dict[str, int] = field(default_factory=dict)

    # Runtime v2 — leftover player action segments from a multi-step input.
    # Orchestrator pops segments[0] each round until empty. New non-empty
    # player input clears this list.
    pending_player_segments: list[str] = field(default_factory=list)

    # Runtime v2 — per-NPC offstage event log accumulated since last catch-up.
    # Entries: {"round": int, "content": str, "source": str}.
    offstage_event_log: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "current_time": self.current_time,
            "current_location": self.current_location,
            "player_inventory": self.player_inventory,
            "discovered_clues": self.discovered_clues,
            "npc_relations": self.npc_relations,
            "triggered_events": self.triggered_events,
            "visited_locations": self.visited_locations,
            "time_index": self.time_index,
            "round_number": self.round_number,
            "rounds_since_last_clue": self.rounds_since_last_clue,
            "last_stage_summary_round": self.last_stage_summary_round,
            "rounds_in_climax": self.rounds_in_climax,
            "npc_intents": self.npc_intents,
            "info_items": self.info_items,
            "npc_locations": self.npc_locations,
            "narrative_arc": self.narrative_arc,
            "world_conflicts": self.world_conflicts,
            "flags": self.flags,
            "last_compressed_round": self.last_compressed_round,
            "case_board": self.case_board,
            "player_actions": self.player_actions,
            "triggered_event_ids": list(self.triggered_event_ids),
            "world_state": self.world_state,
            "structural_facts": self.structural_facts,
            "structural_claims": self.structural_claims,
            "last_active_round": self.last_active_round,
            "pending_player_segments": self.pending_player_segments,
            "offstage_event_log": self.offstage_event_log,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        kwargs = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        # triggered_event_ids is persisted as a list (JSON-safe); convert back to set
        if "triggered_event_ids" in kwargs and isinstance(kwargs["triggered_event_ids"], list):
            kwargs["triggered_event_ids"] = set(kwargs["triggered_event_ids"])
        return cls(**kwargs)


def _advance_time(time_index: int) -> tuple[str, int]:
    new_index = time_index + 1
    day = new_index // len(TIME_SLOTS) + 1
    slot = TIME_SLOTS[new_index % len(TIME_SLOTS)]
    return f"第{day}天·{slot}", new_index


def apply_state_updates(state: GameState, updates: dict) -> GameState:
    new_state = copy.deepcopy(state)

    if location := updates.get("location"):
        new_state.current_location = location
        if location not in new_state.visited_locations:
            new_state.visited_locations.append(location)

    if updates.get("time_advance"):
        new_state.current_time, new_state.time_index = _advance_time(new_state.time_index)

    # new_clues contract: Director gives content text, server assigns id.
    # Validation centralised in ``append_discovered_clue``.
    new_clues_raw = updates.get("new_clues", []) or []
    accepted_count = 0
    for entry in new_clues_raw:
        if append_discovered_clue(
            new_state.discovered_clues,
            entry,
            found_at=new_state.current_time,
            source="director_new_clues",
        ):
            accepted_count += 1

    for npc_name, npc_update in updates.get("npc_updates", {}).items():
        if npc_name not in new_state.npc_relations:
            new_state.npc_relations[npc_name] = {"trust": 3, "mood": "正常", "last_interaction": ""}
        relation = new_state.npc_relations[npc_name]
        if "trust_change" in npc_update:
            relation["trust"] = max(0, min(10, relation["trust"] + npc_update["trust_change"]))
        if "mood" in npc_update:
            relation["mood"] = npc_update["mood"]

    inventory_changes = updates.get("inventory_changes", {})
    for item in inventory_changes.get("add", []):
        if item not in new_state.player_inventory:
            new_state.player_inventory.append(item)
    for item in inventory_changes.get("remove", []):
        if item in new_state.player_inventory:
            new_state.player_inventory.remove(item)

    # Track rounds and clue freshness
    new_state.round_number += 1
    if accepted_count > 0:
        new_state.rounds_since_last_clue = 0
    else:
        new_state.rounds_since_last_clue += 1

    return new_state


async def save_session_state(
    db: AsyncSession,
    session_id: str,
    new_state: dict,
    *,
    expected_version: int,
    extra_values: dict | None = None,
) -> int:
    """Atomically persist game_state if the caller still owns the version."""
    values = {
        "game_state": new_state,
        "version": GameSession.version + 1,
    }
    if extra_values:
        values.update(extra_values)

    result = await db.execute(
        update(GameSession)
        .where(GameSession.id == session_id, GameSession.version == expected_version)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise StaleVersionError(
            f"session {session_id}: expected version {expected_version}, but it has changed"
        )

    version_result = await db.execute(select(GameSession.version).where(GameSession.id == session_id))
    new_version = version_result.scalar_one()
    return int(new_version)
