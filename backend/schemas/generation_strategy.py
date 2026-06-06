from __future__ import annotations

from pydantic import BaseModel, Field


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_str_list(values: object, limit: int | None = None) -> list[str]:
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = []

    result: list[str] = []
    for item in candidates:
        text = _clean_str(item)
        if not text or text in result:
            continue
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _clamp_int(value: object, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


class SearchPlan(BaseModel):
    needs_search: bool = False
    reference_mode: str = "hybrid"
    queries: list[str] = Field(default_factory=list)
    focuses: list[str] = Field(default_factory=list)
    must_have_terms: list[str] = Field(default_factory=list)
    avoid_terms: list[str] = Field(default_factory=list)
    freshness_sensitive: bool = False
    source_bias: str = ""
    reason: str = ""


class WorldBrief(BaseModel):
    world_shape: str = ""
    tone: str = ""
    realism_level: str = ""
    lore_density: str = ""
    conflict_axes: list[str] = Field(default_factory=list)
    location_count_target: int = 6
    tension_count_target: int = 4
    npc_count_target: int = 10
    playtime_band: str = "30-60分钟"
    reference_utilization_mode: str = ""


class CharacterBrief(BaseModel):
    count_target: int = 10
    relationship_density: str = ""
    faction_count: int = 2
    secret_density: str = ""
    knowledge_distribution: str = ""
    schedule_granularity: str = "时段"
    archetype_mix: list[str] = Field(default_factory=list)
    power_distribution: str = ""
    playable_candidate_count: int = 4


class PlayableBrief(BaseModel):
    playable_count_target: int = 4
    recommended_count_target: int = 4
    viewpoint_mix: list[str] = Field(default_factory=list)
    ability_mix: str = ""
    spoiler_exposure_cap: str = ""
    inventory_richness: str = ""
    role_diversity_axes: list[str] = Field(default_factory=list)


class ScriptBrief(BaseModel):
    script_type: str = ""
    event_count_target: int = 7
    clue_density: str = ""
    reveal_cadence: str = ""
    red_herring_level: str = ""
    branchiness: str = ""
    time_pressure: str = ""
    ending_mix: list[str] = Field(default_factory=list)
    ending_count_target: int = 4
    trigger_type_mix: list[str] = Field(default_factory=list)
    player_agency_level: str = ""


class CharacterVisualHook(BaseModel):
    name: str = ""
    appearance: str = ""
    costume: str = ""
    mood: str = ""
    motif: str = ""


class VisualBrief(BaseModel):
    cover_subject: str = ""
    character_visual_hooks: list[CharacterVisualHook] = Field(default_factory=list)
    mood: str = ""
    palette: str = ""
    composition: str = ""
    camera_language: str = ""
    style_tags: list[str] = Field(default_factory=list)
    negative_tags: list[str] = Field(default_factory=list)
    consistency_notes: str = ""


class ResearchRequest(BaseModel):
    stage: str
    goal: str = ""
    query_candidates: list[str] = Field(default_factory=list)
    focuses: list[str] = Field(default_factory=list)
    source_preference: str = "hybrid"
    freshness_sensitive: bool = False
    max_queries: int = 3


class ResearchArtifact(BaseModel):
    artifact_id: str
    query: str
    source: str
    title: str = ""
    excerpt: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    url: str = ""


class ResearchContext(BaseModel):
    stage: str
    summary: str = ""
    artifacts: list[ResearchArtifact] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def text(self) -> str:
        if self.summary:
            return self.summary
        return "\n".join(artifact.summary or artifact.excerpt for artifact in self.artifacts if artifact.summary or artifact.excerpt)


def normalize_search_plan(value: SearchPlan | dict | None) -> SearchPlan:
    raw = value if isinstance(value, SearchPlan) else SearchPlan.model_validate(value or {})
    needs_search = bool(raw.needs_search and _clean_str_list(raw.queries, limit=5))
    return SearchPlan(
        needs_search=needs_search,
        reference_mode=_clean_str(raw.reference_mode) or "hybrid",
        queries=_clean_str_list(raw.queries, limit=5),
        focuses=_clean_str_list(raw.focuses, limit=6),
        must_have_terms=_clean_str_list(raw.must_have_terms, limit=8),
        avoid_terms=_clean_str_list(raw.avoid_terms, limit=8),
        freshness_sensitive=bool(raw.freshness_sensitive),
        source_bias=_clean_str(raw.source_bias),
        reason=_clean_str(raw.reason),
    )


def normalize_world_brief(value: WorldBrief | dict | None) -> WorldBrief:
    raw = value if isinstance(value, WorldBrief) else WorldBrief.model_validate(value or {})
    return WorldBrief(
        world_shape=_clean_str(raw.world_shape),
        tone=_clean_str(raw.tone),
        realism_level=_clean_str(raw.realism_level),
        lore_density=_clean_str(raw.lore_density),
        conflict_axes=_clean_str_list(raw.conflict_axes, limit=6),
        location_count_target=_clamp_int(raw.location_count_target, 6, 4, 12),
        tension_count_target=_clamp_int(raw.tension_count_target, 4, 2, 6),
        npc_count_target=_clamp_int(raw.npc_count_target, 10, 6, 18),
        playtime_band=_clean_str(raw.playtime_band) or "30-60分钟",
        reference_utilization_mode=_clean_str(raw.reference_utilization_mode),
    )


def normalize_character_brief(value: CharacterBrief | dict | None) -> CharacterBrief:
    raw = value if isinstance(value, CharacterBrief) else CharacterBrief.model_validate(value or {})
    return CharacterBrief(
        count_target=_clamp_int(raw.count_target, 10, 6, 18),
        relationship_density=_clean_str(raw.relationship_density),
        faction_count=_clamp_int(raw.faction_count, 2, 0, 6),
        secret_density=_clean_str(raw.secret_density),
        knowledge_distribution=_clean_str(raw.knowledge_distribution),
        schedule_granularity=_clean_str(raw.schedule_granularity) or "时段",
        archetype_mix=_clean_str_list(raw.archetype_mix, limit=8),
        power_distribution=_clean_str(raw.power_distribution),
        playable_candidate_count=_clamp_int(raw.playable_candidate_count, 4, 1, 12),
    )


def normalize_playable_brief(value: PlayableBrief | dict | None) -> PlayableBrief:
    raw = value if isinstance(value, PlayableBrief) else PlayableBrief.model_validate(value or {})
    recommended_count_target = _clamp_int(raw.recommended_count_target, 4, 1, 6)
    playable_count_target = _clamp_int(raw.playable_count_target, recommended_count_target, 1, None)
    return PlayableBrief(
        playable_count_target=max(playable_count_target, recommended_count_target),
        recommended_count_target=recommended_count_target,
        viewpoint_mix=_clean_str_list(raw.viewpoint_mix, limit=8),
        ability_mix=_clean_str(raw.ability_mix),
        spoiler_exposure_cap=_clean_str(raw.spoiler_exposure_cap),
        inventory_richness=_clean_str(raw.inventory_richness),
        role_diversity_axes=_clean_str_list(raw.role_diversity_axes, limit=8),
    )


def normalize_script_brief(value: ScriptBrief | dict | None) -> ScriptBrief:
    raw = value if isinstance(value, ScriptBrief) else ScriptBrief.model_validate(value or {})
    return ScriptBrief(
        script_type=_clean_str(raw.script_type),
        event_count_target=_clamp_int(raw.event_count_target, 7, 5, 12),
        clue_density=_clean_str(raw.clue_density),
        reveal_cadence=_clean_str(raw.reveal_cadence),
        red_herring_level=_clean_str(raw.red_herring_level),
        branchiness=_clean_str(raw.branchiness),
        time_pressure=_clean_str(raw.time_pressure),
        ending_mix=_clean_str_list(raw.ending_mix, limit=6),
        ending_count_target=_clamp_int(raw.ending_count_target, 4, 3, 6),
        trigger_type_mix=_clean_str_list(raw.trigger_type_mix, limit=6),
        player_agency_level=_clean_str(raw.player_agency_level),
    )


def normalize_visual_brief(value: VisualBrief | dict | None) -> VisualBrief:
    raw = value if isinstance(value, VisualBrief) else VisualBrief.model_validate(value or {})
    hooks: list[CharacterVisualHook] = []
    for hook in raw.character_visual_hooks:
        if isinstance(hook, CharacterVisualHook):
            hooks.append(hook)
        else:
            hooks.append(CharacterVisualHook.model_validate(hook))
    return VisualBrief(
        cover_subject=_clean_str(raw.cover_subject),
        character_visual_hooks=hooks,
        mood=_clean_str(raw.mood),
        palette=_clean_str(raw.palette),
        composition=_clean_str(raw.composition),
        camera_language=_clean_str(raw.camera_language),
        style_tags=_clean_str_list(raw.style_tags, limit=10),
        negative_tags=_clean_str_list(raw.negative_tags, limit=12),
        consistency_notes=_clean_str(raw.consistency_notes),
    )
