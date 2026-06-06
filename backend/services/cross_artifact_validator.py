"""Cross-artifact referential integrity check, run before publish commits.

Schema-level validation (services/generation_schema.py) catches structural
issues within a single artifact, but cannot tell that an event references
an NPC absent from the character roster, or that an ending demands a clue
no event ever spawns. Those are the integrity holes that cost the most
when they slip through — every downstream stage (cover/hero/endings image
generation, Tier1 judge) wastes budget on content that cannot ship.

Call this from publish_world_draft / publish_script_draft, after schema
validation, before any commit. Drift detected here is the publisher's
fault, not the runtime's; surfacing it loudly forces the generator to
fix root causes instead of letting half-broken content land.
"""
from __future__ import annotations


class CrossArtifactError(ValueError):
    """Raised when artifacts (world / script / characters / events / endings)
    reference each other inconsistently. Distinct from SchemaValidationError
    so callers can render a clearer error per failure class.
    """


def validate_cross_artifact(world: dict, script: dict) -> None:
    """Raise CrossArtifactError if referential integrity fails.

    Checks:
      - Every (world|script) event's present_npcs ⊆ world characters
      - Every script ending's required_clues ⊆ world events' spawn_clues
    """
    character_names = {
        c.get("name")
        for c in (world.get("characters") or [])
        if isinstance(c, dict) and c.get("name")
    }
    world_clue_ids = _collect_clue_ids(world.get("events_data") or [])

    errors: list[str] = []
    errors.extend(_event_npc_errors(world.get("events_data") or [], character_names, "world"))
    errors.extend(_event_npc_errors(script.get("events_data") or [], character_names, "script"))
    errors.extend(_ending_clue_errors(script.get("endings_data") or [], world_clue_ids))

    if errors:
        raise CrossArtifactError("; ".join(errors))


def _collect_clue_ids(events: list) -> set[str]:
    ids: set[str] = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        effects = ev.get("effects") or {}
        for clue in effects.get("spawn_clues") or []:
            cid = clue.get("id") if isinstance(clue, dict) else None
            if isinstance(cid, str):
                ids.add(cid)
    return ids


def _event_npc_errors(events: list, character_names: set[str], source: str) -> list[str]:
    out: list[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ev_id = ev.get("id", "<no-id>")
        missing = [
            name
            for name in (ev.get("present_npcs") or [])
            if name and name not in character_names
        ]
        if missing:
            out.append(f"{source} event {ev_id!r} references unknown NPC(s): {missing}")
    return out


def _ending_clue_errors(endings: list, known_clue_ids: set[str]) -> list[str]:
    out: list[str] = []
    for idx, ending in enumerate(endings):
        if not isinstance(ending, dict):
            continue
        ending_id = ending.get("id") or ending.get("title") or f"endings[{idx}]"
        hard = ending.get("hard_conditions") or {}
        required = hard.get("required_clues") or []
        missing = [c for c in required if c not in known_clue_ids]
        if missing:
            out.append(f"ending {ending_id!r} requires unspawned clue(s): {missing}")
    return out
