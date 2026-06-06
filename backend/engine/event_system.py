from engine.state_manager import GameState, apply_state_updates


def check_events(events: list[dict], state: GameState, game_mode: str) -> list[dict]:
    triggered = []

    for event in events:
        event_key = event.get("name") or event.get("id", "")
        if not event_key:
            continue
        if event_key in state.triggered_events:
            continue

        mode = event.get("mode", "both")
        if mode == "script_only" and game_mode != "script":
            continue
        if mode == "free_only" and game_mode != "free":
            continue

        if _matches_condition(event, state):
            triggered.append(event)

    return triggered


def _matches_condition(event: dict, state: GameState) -> bool:
    trigger_type = event.get("trigger_type", "")
    condition = event.get("trigger_condition", {})

    try:
        if trigger_type == "time":
            threshold = condition.get("min_time_index") or condition.get("round", 0)
            return (state.time_index or state.round_number or 0) >= threshold

        if trigger_type == "clue":
            required = set(condition.get("required_clues", []))
            if not required:
                return False
            found = {clue["id"] for clue in state.discovered_clues if isinstance(clue, dict) and "id" in clue}
            return required.issubset(found)

        if trigger_type == "location":
            return state.current_location == condition.get("location", "")

        if trigger_type == "clue_count":
            min_count = condition.get("min_clues_found") or condition.get("clue_count", 0)
            return len(state.discovered_clues) >= min_count

        if trigger_type == "rounds_without_progress":
            min_rounds = condition.get("min_rounds") or condition.get("rounds", 0)
            return (state.rounds_since_last_clue or 0) >= min_rounds
    except (KeyError, TypeError):
        return False

    return False


def apply_event_effects(state: GameState, event: dict) -> GameState:
    effects = event.get("effects", {})
    updates = {}

    if clues := effects.get("add_clues"):
        updates["new_clues"] = clues
    if npc_updates := effects.get("npc_updates"):
        updates["npc_updates"] = npc_updates
    if location := effects.get("unlock_location"):
        updates["location"] = location

    new_state = apply_state_updates(state, updates) if updates else state
    # Store both id (for dedup) and name (for display)
    event_key = event.get("name") or event.get("id", "")
    new_state.triggered_events.append(event_key)
    return new_state
