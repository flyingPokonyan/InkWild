"""Information propagation model.

Manages how information spreads between NPCs based on location,
social ties, and time delay rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.intent_system import WorldEvent
from engine.state_manager import GameState


@dataclass
class InfoItem:
    """A piece of information tracked in the world."""

    source: str
    content: str
    known_by: list[str] = field(default_factory=list)
    created_at_round: int = 0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "content": self.content,
            "known_by": list(self.known_by),
            "created_at_round": self.created_at_round,
        }

    @classmethod
    def from_dict(cls, data: dict) -> InfoItem:
        return cls(
            source=str(data.get("source", "")),
            content=str(data.get("content", "")),
            known_by=list(data.get("known_by", [])),
            created_at_round=int(data.get("created_at_round", 0)),
        )


class InfoPropagation:
    """Propagates information between NPCs each tick."""

    SAME_LOCATION_DELAY = 0
    SOCIAL_TIE_DELAY = 2
    TOWN_WIDE_DELAY = 5

    def propagate(self, state: GameState) -> list[WorldEvent]:
        events: list[WorldEvent] = []
        current_round = state.round_number

        updated_items: list[dict] = []
        for item_data in state.info_items:
            info = InfoItem.from_dict(item_data) if isinstance(item_data, dict) else item_data

            if not info.known_by:
                updated_items.append(info.to_dict())
                continue

            new_knowers = self._find_new_knowers(info, state, current_round)
            if new_knowers:
                info.known_by.extend(new_knowers)
                events.append(
                    WorldEvent(
                        event_type="info_spread",
                        description=f"信息传播：{'、'.join(new_knowers)}得知了「{info.content[:20]}...」",
                        involved_npcs=new_knowers,
                        effects={},
                    )
                )

            updated_items.append(info.to_dict())

        state.info_items = updated_items
        return events

    def _find_new_knowers(
        self, info: InfoItem, state: GameState, current_round: int
    ) -> list[str]:
        new_knowers: list[str] = []
        rounds_since = current_round - info.created_at_round

        all_npcs = set(state.npc_intents.keys()) | set(state.npc_locations.keys())

        for npc_name in all_npcs:
            if npc_name in info.known_by:
                continue

            if self._same_location(npc_name, info.known_by, state):
                new_knowers.append(npc_name)
            elif rounds_since >= self.SOCIAL_TIE_DELAY and self._has_social_tie(
                npc_name, info.known_by, state
            ):
                new_knowers.append(npc_name)
            elif rounds_since >= self.TOWN_WIDE_DELAY:
                new_knowers.append(npc_name)

        return new_knowers

    def _same_location(
        self, npc_name: str, knowers: list[str], state: GameState
    ) -> bool:
        npc_loc = state.npc_locations.get(npc_name)
        if not npc_loc:
            return False
        return any(state.npc_locations.get(k) == npc_loc for k in knowers)

    def _has_social_tie(
        self, npc_name: str, knowers: list[str], state: GameState
    ) -> bool:
        """Simple heuristic: NPCs that share a relation entry are socially tied."""
        npc_rel = state.npc_relations.get(npc_name, {})
        for knower in knowers:
            if knower in npc_rel or npc_name in state.npc_relations.get(knower, {}):
                return True
        return False
