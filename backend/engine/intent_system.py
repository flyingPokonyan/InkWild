"""NPC autonomous intent engine.

Each NPC maintains an intent state (goal, urgency, plan stages).
The IntentSystem advances these deterministically each tick,
generating action events when urgency is high enough.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.state_manager import GameState


@dataclass
class WorldEvent:
    """A world event produced by the simulation layer."""

    event_type: str  # "npc_action" | "info_spread" | "environment" | "time_event"
    description: str
    involved_npcs: list[str] = field(default_factory=list)
    effects: dict = field(default_factory=dict)


@dataclass
class NPCIntent:
    """Structured intent state for a single NPC."""

    current_goal: str
    urgency: float  # 1-10
    plan_stage: int
    blocked_by: str | None
    plan_stages: list[str] = field(default_factory=lambda: ["观望", "准备", "行动"])

    def to_dict(self) -> dict:
        return {
            "current_goal": self.current_goal,
            "urgency": self.urgency,
            "plan_stage": self.plan_stage,
            "blocked_by": self.blocked_by,
            "plan_stages": self.plan_stages,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NPCIntent:
        return cls(
            current_goal=str(data.get("current_goal", "")),
            urgency=float(data.get("urgency", 3)),
            plan_stage=int(data.get("plan_stage", 0)),
            blocked_by=data.get("blocked_by"),
            plan_stages=list(data.get("plan_stages", ["观望", "准备", "行动"])),
        )


def init_npc_intents(npcs: list[dict], world_tensions: list[str] | None = None) -> dict:
    """Build initial WorldSimulator state for free mode without seed_system."""
    npc_intents: dict[str, dict] = {}
    info_items: list[dict] = []
    npc_names = [str(npc.get("name", "")) for npc in npcs if npc.get("name")]

    for npc in npcs:
        name = str(npc.get("name", ""))
        if not name:
            continue
        secret = str(npc.get("secret") or "")
        intent = NPCIntent(
            current_goal=secret or f"{name}维持日常秩序",
            urgency=float(npc.get("initial_urgency", 3)),
            plan_stage=0,
            blocked_by=npc.get("blocked_by"),
            plan_stages=list(npc.get("plan_stages") or ["观望", "准备", "行动"]),
        )
        npc_intents[name] = intent.to_dict()

        for knowledge in npc.get("knowledge") or []:
            info_items.append(
                {
                    "source": name,
                    "content": str(knowledge),
                    "known_by": [name],
                    "created_at_round": 0,
                }
            )

    conflicts = [
        {
            "involved_npcs": [name for name in npc_names if name in tension] or npc_names[:2],
            "severity": 7,
            "description": tension,
            "progression_rules": [],
        }
        for tension in (world_tensions or [])
        if tension
    ]

    return {
        "npc_intents": npc_intents,
        "info_items": info_items,
        "world_conflicts": conflicts,
    }


_CONDITION_RE = re.compile(r"^(\w+)\s*(>=|<=|>|<|==)\s*(\d+)$")


class IntentSystem:
    """Advances NPC intents each tick based on deterministic rules."""

    def advance(self, state: GameState, world_config: dict) -> list[WorldEvent]:
        events: list[WorldEvent] = []

        for npc_name, intent_data in state.npc_intents.items():
            intent = NPCIntent.from_dict(intent_data) if isinstance(intent_data, dict) else intent_data

            # 1. Check if blocked_by condition is now resolved
            if intent.blocked_by and self._is_unblocked(intent, state):
                intent.blocked_by = None
                intent.plan_stage = min(intent.plan_stage + 1, len(intent.plan_stages) - 1)

            # 2. Urgency grows naturally each tick
            intent.urgency = min(10.0, intent.urgency + 0.5)

            # 3. High urgency + no blocker → generate action event
            if intent.urgency >= 8 and not intent.blocked_by:
                stage_label = (
                    intent.plan_stages[intent.plan_stage]
                    if intent.plan_stage < len(intent.plan_stages)
                    else intent.current_goal
                )
                events.append(
                    WorldEvent(
                        event_type="npc_action",
                        description=f"{npc_name}执行计划：{stage_label}",
                        involved_npcs=[npc_name],
                        effects=self._compute_action_effects(npc_name, intent, state, world_config),
                    )
                )

            # Persist updated intent back to state
            state.npc_intents[npc_name] = intent.to_dict()

        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_unblocked(self, intent: NPCIntent, state: GameState) -> bool:
        condition = (intent.blocked_by or "").strip()
        if not condition:
            return False

        # Pattern: "clue_count >= 5"
        match = _CONDITION_RE.match(condition)
        if not match:
            return False

        var_name, operator, threshold_str = match.groups()
        threshold = int(threshold_str)

        value = self._resolve_variable(var_name, state)
        if value is None:
            return False

        ops = {">=": value >= threshold, "<=": value <= threshold, ">": value > threshold, "<": value < threshold, "==": value == threshold}
        return ops.get(operator, False)

    def _resolve_variable(self, var_name: str, state: GameState) -> int | None:
        if var_name == "clue_count":
            return len(state.discovered_clues)
        if var_name == "round_number":
            return state.round_number
        if var_name == "time_index":
            return state.time_index
        return None

    def _compute_action_effects(
        self,
        npc_name: str,
        intent: NPCIntent,
        state: GameState,
        world_config: dict,
    ) -> dict:
        """Translate an urgent NPC plan stage into deterministic state effects."""
        stage_text = self._stage_text(intent)
        effects: dict = {
            "npc_locations": {},
            "new_info_items": [],
            "npc_relations": {},
            "flags": {},
        }

        if "监视" in stage_text or "跟踪" in stage_text:
            effects["npc_locations"][npc_name] = state.current_location
            effects["flags"][f"{npc_name}_observing"] = True
            return effects

        target = self._extract_target_from_stage(stage_text, world_config, actor=npc_name)

        if "威胁" in stage_text or "警告" in stage_text:
            content = f"{npc_name}{stage_text}"
            if target:
                content = f"{npc_name}威胁{target}保持沉默"
                target_location = state.npc_locations.get(target)
                if target_location:
                    effects["npc_locations"][npc_name] = target_location
                effects["npc_relations"][target] = {
                    "mood": "紧张",
                    "last_interaction": f"受到{npc_name}威胁",
                }
            effects["new_info_items"].append(
                {
                    "source": npc_name,
                    "content": content,
                    "known_by": [name for name in [npc_name, target] if name],
                    "created_at_round": state.round_number,
                }
            )
            return effects

        if "灭口" in stage_text or "袭击" in stage_text or "执行" in stage_text:
            if target:
                effects["flags"][f"{target}_in_danger"] = True
                effects["new_info_items"].append(
                    {
                        "source": npc_name,
                        "content": f"{npc_name}对{target}采取行动",
                        "known_by": [npc_name],
                        "created_at_round": state.round_number,
                    }
                )
            else:
                effects["flags"][f"{npc_name}_active_plan"] = stage_text
            return effects

        if "准备" in stage_text:
            effects["flags"][f"{npc_name}_preparing"] = True

        return effects

    def _stage_text(self, intent: NPCIntent) -> str:
        if 0 <= intent.plan_stage < len(intent.plan_stages):
            return intent.plan_stages[intent.plan_stage]
        return intent.current_goal

    def _extract_target_from_stage(
        self,
        stage_text: str,
        world_config: dict,
        actor: str,
    ) -> str | None:
        for npc in world_config.get("npcs", []):
            name = str(npc.get("name", ""))
            if name and name != actor and name in stage_text:
                return name
        return None
