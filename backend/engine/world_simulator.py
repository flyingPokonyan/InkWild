"""WorldSimulator — pure rule engine orchestrating subsystems.

Runs before Director each tick: advances NPC intents, propagates
information, and processes world clock events. No LLM calls.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

import structlog

from engine.condition_dsl import ConditionDSLParseError
from engine.condition_dsl import evaluate as dsl_evaluate
from engine.condition_dsl import parse as dsl_parse
from engine.info_propagation import InfoPropagation
from engine.intent_system import IntentSystem, WorldEvent
from engine.state_manager import GameState, append_discovered_clue
from engine.world_clock import ClockResult, WorldClock

logger = structlog.get_logger()


@dataclass
class TickResult:
    """Output of a single WorldSimulator tick."""

    updated_state: GameState
    world_events: list[WorldEvent] = field(default_factory=list)
    environment_changes: list[str] = field(default_factory=list)


class WorldSimulator:
    """Pure rule engine — no LLM calls, <50ms per tick."""

    def __init__(
        self,
        intent_system: IntentSystem | None = None,
        info_propagation: InfoPropagation | None = None,
        world_clock: WorldClock | None = None,
    ):
        self.intent_system = intent_system or IntentSystem()
        self.info_propagation = info_propagation or InfoPropagation()
        self.world_clock = world_clock or WorldClock()

    def tick(
        self,
        state: GameState,
        world_config: dict,
        *,
        skip_intent_advance: bool = False,
    ) -> TickResult:
        """Run one rule-engine tick.

        ``skip_intent_advance`` is set by the v2 orchestrator path: rule-based
        intent advancement is deprecated when NPCs self-report intent_update
        via their action schema. info_propagation + world_clock still run so
        free-mode world dynamics keep moving.
        """
        updated_state = copy.deepcopy(state)
        events: list[WorldEvent] = []
        env_changes: list[str] = []

        # 1. Advance NPC intents (runtime v1 only; v2 NPCs self-report via
        # NPCAction.intent_update — see docs/plans/runtime-architecture-overhaul-2026-05.md §4.4).
        if not skip_intent_advance:
            try:
                intent_events = self.intent_system.advance(updated_state, world_config)
                apply_intent_effects(updated_state, intent_events)
                events.extend(intent_events)
            except Exception:
                logger.warning("intent_system_error", exc_info=True)

        # 2. Propagate information
        try:
            prop_events = self.info_propagation.propagate(updated_state)
            events.extend(prop_events)
        except Exception:
            logger.warning("info_propagation_error", exc_info=True)

        # 3. World clock (NPC positions, time events, environment)
        try:
            clock_result: ClockResult = self.world_clock.advance(updated_state, world_config)
            events.extend(clock_result.events)
            env_changes.extend(clock_result.environment_changes)
        except Exception:
            logger.warning("world_clock_error", exc_info=True)

        # 4. events_data trigger processing (scripted events from world/script data)
        _process_events_data(updated_state, world_config, events)
        _process_structural_milestones(updated_state, world_config)

        return TickResult(
            updated_state=updated_state,
            world_events=events,
            environment_changes=env_changes,
        )


def _process_events_data(
    state: GameState,
    world_config: dict,
    events: list[WorldEvent],
) -> None:
    """Process events_data triggers and apply effects in-place on *state*.

    Called at the end of each tick after all other subsystems have run.
    Robust: parse/eval errors are silently skipped; missing fields use
    safe defaults. Old worlds without events_data are handled transparently.
    """
    events_data = world_config.get("events_data") or []
    for event in events_data:
        event_id: str | None = event.get("id")
        if not event_id:
            continue
        if event.get("disabled"):
            continue
        if event_id in state.triggered_event_ids:
            continue

        trigger = event.get("trigger") or {}
        dsl_source: str = trigger.get("condition_dsl", "")
        if not dsl_source:
            continue

        try:
            expr = dsl_parse(dsl_source)
            condition_met: bool = dsl_evaluate(expr, state)
        except (ConditionDSLParseError, Exception):
            logger.warning(
                "events_data_dsl_error",
                event_id=event_id,
                dsl=dsl_source,
                exc_info=True,
            )
            continue

        if not condition_met:
            continue

        kind: str = event.get("kind", "")
        effects = event.get("effects") or {}

        if kind == "conditional":
            # Probabilistic gate
            prob = float(trigger.get("probability", 1.0))
            prob = max(0.0, min(1.0, prob))  # clamp to [0, 1]
            if prob < 1.0 and random.random() >= prob:
                continue

            # Apply world_state_changes
            ws_changes = effects.get("world_state_changes") or {}
            for k, v in ws_changes.items():
                state.world_state[k] = v

            # Apply npc_mood_changes → npc_relations[npc]["mood"]
            mood_changes = effects.get("npc_mood_changes") or {}
            for npc_name, new_mood in mood_changes.items():
                if npc_name not in state.npc_relations:
                    state.npc_relations[npc_name] = {
                        "trust": 3,
                        "mood": "正常",
                        "last_interaction": "",
                    }
                state.npc_relations[npc_name]["mood"] = new_mood

            # Apply spawn_clues → discovered_clues (validated)
            for clue_text in (effects.get("spawn_clues") or []):
                append_discovered_clue(
                    state.discovered_clues,
                    clue_text,
                    found_at=state.current_time,
                    source="events_data_spawn_clues",
                )

            events.append(
                WorldEvent(
                    event_type="scripted_event",
                    description=event.get("summary", ""),
                    involved_npcs=list(event.get("involved_npcs") or []),
                )
            )

        elif kind == "npc_intent_driven":
            npc_name: str = trigger.get("npc_name", "")
            intent_payload: dict = trigger.get("intent_payload") or {}
            if npc_name:
                state.npc_intents[npc_name] = intent_payload
            events.append(
                WorldEvent(
                    event_type="scripted_event",
                    description=f"{npc_name or '未知NPC'}：{event.get('summary', '')}",
                    involved_npcs=[npc_name] if npc_name else [],
                )
            )

        else:
            # Unknown kind — skip without marking as triggered
            logger.warning("events_data_unknown_kind", event_id=event_id, kind=kind)
            continue

        state.triggered_event_ids.add(event_id)


def _process_structural_milestones(state: GameState, world_config: dict) -> None:
    """Evaluate author-defined structural milestones; commit those whose
    condition_dsl is satisfied (spec §3.4). Deterministic, no LLM. Reuses the
    same condition_dsl evaluator as events_data. Robust: parse/eval errors are
    logged and skipped. Idempotency is handled by commit_structural_fact.
    """
    from engine.structural_ledger import commit_structural_fact

    milestones = world_config.get("structural_milestones") or []
    for ms in milestones:
        if not isinstance(ms, dict) or ms.get("disabled"):
            continue
        dsl_source = (ms.get("trigger") or {}).get("condition_dsl", "")
        if not dsl_source:
            continue
        try:
            expr = dsl_parse(dsl_source)
            met = dsl_evaluate(expr, state)
        except (ConditionDSLParseError, Exception):
            logger.warning(
                "structural_milestone_dsl_error",
                milestone_id=ms.get("milestone_id"),
                dsl=dsl_source,
                exc_info=True,
            )
            continue
        if not met:
            continue
        commit_structural_fact(
            state,
            {
                "fact_key": ms.get("fact_key"),
                "fact_text": ms.get("fact_text"),
                "kind": ms.get("kind"),
                "target_ref": ms.get("target_ref"),
                "provenance": "authored_milestone",
            },
        )


def apply_intent_effects(state: GameState, events: list[WorldEvent]) -> GameState:
    """Apply deterministic intent effects produced during this tick."""
    for event in events:
        effects = event.effects or {}

        state.npc_locations.update(effects.get("npc_locations", {}))
        state.info_items.extend(effects.get("new_info_items", []))
        state.flags.update(effects.get("flags", {}))

        for npc_name, relation_update in effects.get("npc_relations", {}).items():
            relation = state.npc_relations.setdefault(
                npc_name,
                {"trust": 3, "mood": "正常", "last_interaction": ""},
            )
            if isinstance(relation_update, dict):
                if "trust_change" in relation_update:
                    relation["trust"] = max(
                        0,
                        min(10, relation.get("trust", 3) + relation_update["trust_change"]),
                    )
                if "mood" in relation_update:
                    relation["mood"] = relation_update["mood"]
                if "last_interaction" in relation_update:
                    relation["last_interaction"] = relation_update["last_interaction"]
            else:
                relation["last_interaction"] = str(relation_update)

    return state
