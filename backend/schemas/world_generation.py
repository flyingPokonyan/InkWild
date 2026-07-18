"""Contracts for the world-generation workflow.

The workflow is deterministic at the shell and lets a single constrained
Director choose only the ambiguous parts: scale, protagonist viewpoints and
creative focus.  Builders consume the frozen ``WorldSpec``; they do not invent
their own target counts independently.
"""
from __future__ import annotations

from enum import StrEnum
import math

from pydantic import BaseModel, Field

from schemas.lore_pack import LoreDimension


class WorldScaleClass(StrEnum):
    COMPACT = "compact"
    STANDARD = "standard"
    EPIC = "epic"


class ViolationSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class DirectorActionType(StrEnum):
    REPAIR = "repair"
    STOP = "stop"


class WorldScalePlan(BaseModel):
    scale_class: WorldScaleClass
    active_roles_min: int = Field(ge=3, le=60)
    active_roles_target: int = Field(ge=3, le=60)
    active_roles_max: int = Field(ge=3, le=60)
    playable_min: int = Field(ge=1, le=30)
    playable_target: int = Field(ge=1, le=30)
    playable_max: int = Field(ge=1, le=30)
    portrait_target: int = Field(ge=1, le=30)
    locations_target: int = Field(ge=3, le=30)
    shared_events_target: int = Field(ge=3, le=20)
    events_target: int = Field(ge=3, le=20)
    rationale: str = ""


class WorldSpec(BaseModel):
    """Versioned, persistable execution contract for one generation run."""

    schema_version: int = 1
    version: int = 1
    generation_run_id: str
    description: str
    genre: str = ""
    era: str = ""
    fidelity_mode: str = "none"
    ip_name: str | None = None
    canon_note: str | None = None
    must_have_characters: list[str] = Field(default_factory=list)
    canon_characters: list[str] = Field(default_factory=list)
    protagonist_candidates: list[str] = Field(default_factory=list)
    creative_focus: list[str] = Field(default_factory=list)
    lore_dimensions: list[LoreDimension] = Field(default_factory=list)
    scale: WorldScalePlan
    node_budget: int = Field(default=24, ge=8, le=64)
    text_call_budget: int = Field(default=24, ge=8, le=80)


class ContractViolation(BaseModel):
    code: str
    severity: ViolationSeverity
    path: str = ""
    message: str
    repairable: bool = False


class DirectorAction(BaseModel):
    action_type: DirectorActionType
    target_node: str | None = None
    reason: str
    payload: dict = Field(default_factory=dict)


def derive_scale_plan(
    *,
    canon_character_count: int = 0,
    must_have_count: int = 0,
    explicit_character_count: int | None = None,
    place_count: int = 0,
) -> WorldScalePlan:
    """Derive safe lower bounds before the Director is allowed to adjust them.

    Bands describe a healthy active cast, not hard caps.  Canon and must-have
    closure may expand the target up to 30 without truncating source characters.
    """
    evidence_count = max(canon_character_count, must_have_count, explicit_character_count or 0)
    if evidence_count >= 21:
        band = WorldScaleClass.EPIC
        active = (20, min(30, max(24, evidence_count)), 30)
        playable = (8, min(15, max(10, evidence_count // 2)), 15)
        portrait = min(15, max(10, playable[1]))
        locations = min(20, max(12, place_count, evidence_count // 2))
        shared_events, events = 12, 12
    elif evidence_count >= 13:
        band = WorldScaleClass.STANDARD
        active = (12, min(20, max(16, evidence_count)), 20)
        playable = (4, min(8, max(6, evidence_count // 3)), 8)
        portrait = min(10, max(7, playable[1]))
        locations = min(16, max(8, place_count, evidence_count // 2))
        shared_events, events = 8, 8
    else:
        band = WorldScaleClass.COMPACT
        active_target = min(12, max(8, evidence_count or 8))
        active = (8, active_target, 12)
        playable = (3, min(5, max(3, active_target // 3)), 5)
        portrait = min(6, max(4, playable[1]))
        locations = min(10, max(5, place_count, active_target // 2))
        shared_events, events = 5, 6

    # A strict source may legitimately contain more than the normal band.  The
    # upper value is an operating target, not permission to prune canon.
    target = max(
        active[1],
        min(30, canon_character_count),
        min(30, must_have_count),
    )
    upper = max(active[2], target)
    return WorldScalePlan(
        scale_class=band,
        active_roles_min=max(active[0], min(must_have_count, 30)),
        active_roles_target=target,
        active_roles_max=upper,
        playable_min=playable[0],
        playable_target=playable[1],
        playable_max=playable[2],
        portrait_target=portrait,
        locations_target=locations,
        shared_events_target=shared_events,
        events_target=events,
        rationale=(
            f"evidence roles={evidence_count}, canon={canon_character_count}, "
            f"must_have={must_have_count}, places={place_count}"
        ),
    )


def estimate_normal_phase_b_calls(
    scale: WorldScalePlan,
    *,
    dedicated_ip_research: bool,
) -> int:
    """Keep the documented happy-path budget executable and regression-testable."""
    return sum(
        [
            0 if dedicated_ip_research else 2,  # generic probe + summary
            4 if dedicated_ip_research else 0,  # two searches + two compiles
            1,  # Director (also plans lore dimensions)
            1,  # world base
            1,  # roster
            1 + math.ceil(scale.active_roles_target / 6),  # lore + character batches
            1,  # shared events
            math.ceil(scale.events_target / 3),
            1,  # free-start batch
            1,  # moderation
            1,  # visual brief
        ]
    )
