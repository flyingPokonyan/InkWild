"""World clock — time-based world changes.

Updates NPC positions from schedule data, triggers time-based events,
and generates environment transition descriptions each tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.intent_system import WorldEvent
from engine.state_manager import GameState

ENVIRONMENT_TRANSITIONS: dict[str, str] = {
    "上午": "晨光熹微，镇上渐渐热闹起来",
    "下午": "午后的阳光有些慵懒，街上行人不多",
    "傍晚": "天色渐暗，街上行人渐少",
    "夜晚": "夜幕降临，镇上只剩零星灯火",
    "深夜": "万籁俱寂，远处偶尔传来犬吠",
}


@dataclass
class ClockResult:
    """Result of a world clock advance step."""

    events: list[WorldEvent] = field(default_factory=list)
    environment_changes: list[str] = field(default_factory=list)


def _extract_time_slot(current_time: str) -> str:
    """Extract the time-of-day slot from a time string like '第1天·上午'."""
    if "·" in current_time:
        return current_time.split("·", 1)[1]
    return current_time


class WorldClock:
    """Advances world time: NPC positions, time events, environment changes."""

    def advance(self, state: GameState, world_config: dict) -> ClockResult:
        """Run one clock tick against *state* and return a `ClockResult`."""
        events: list[WorldEvent] = []
        env_changes: list[str] = []

        current_slot = _extract_time_slot(state.current_time)

        # --- Update NPC positions from schedule ---
        for npc in world_config.get("npcs", []):
            schedule = npc.get("schedule", {})
            expected_location = schedule.get(current_slot)
            if expected_location:
                state.npc_locations[npc["name"]] = expected_location

        # --- Check time-based events ---
        for event_def in world_config.get("events", []):
            if event_def.get("trigger_type") != "time":
                continue
            if self._time_condition_met(event_def, state):
                events.append(
                    WorldEvent(
                        event_type="time_event",
                        description=event_def.get("description", ""),
                        involved_npcs=event_def.get("involved_npcs", []),
                        effects=event_def.get("effects", {}),
                    )
                )

        # --- Environment transition description ---
        if current_slot in ENVIRONMENT_TRANSITIONS:
            env_changes.append(ENVIRONMENT_TRANSITIONS[current_slot])

        return ClockResult(events=events, environment_changes=env_changes)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _time_condition_met(self, event_def: dict, state: GameState) -> bool:
        """Check whether a time-based event should fire.

        An event fires when:
        1. ``state.time_index >= event_def["min_time_index"]``
        2. The event has not already been triggered (its id is not in
           ``state.triggered_events``).
        """
        event_id = event_def.get("id", event_def.get("description", ""))
        if event_id in state.triggered_events:
            return False

        min_time_index = event_def.get("min_time_index", 0)
        return state.time_index >= min_time_index
