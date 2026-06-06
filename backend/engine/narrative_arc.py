"""Narrative arc tracker — player behavior pattern + 3-act detection.

Tracks which NPCs and locations the player interacts with most, detects
interest focus points, and labels the current story act (intro / middle /
climax) so Director prompts can adjust pacing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Phase 2.A.1 — three-act detection thresholds. Intentionally simple
# heuristics; a richer beat-sheet view (Phase 3.3) is deferred. These values
# were tuned against synthetic 30-turn arcs in tests; the acceptance bar is
# detection within ±2 rounds of an expected transition.
ACT_INTRO = "intro"
ACT_MIDDLE = "middle"
ACT_CLIMAX = "climax"

# Climax kicks in once any of these signals say "we're heading for the
# resolution": late round count, lots of clues uncovered, or several key
# decisions already taken.
CLIMAX_ROUND_THRESHOLD = 25
CLIMAX_CLUE_THRESHOLD = 6
CLIMAX_KEY_DECISIONS_THRESHOLD = 3

# Intro is bounded by both being early in rounds AND having few clues so the
# label flips to middle as soon as the player starts uncovering things even
# in the first few rounds (rapid-onset story).
INTRO_ROUND_THRESHOLD = 8
INTRO_CLUE_THRESHOLD = 3

# Phase 2.A.4 — climax resolution controller (SCRIPT mode only; free mode has
# no ending). detect_act labels climax but is open-loop: nothing forces a
# resolution, so a session can hang at climax indefinitely. These thresholds
# close the loop. Consumed by ending_system.check_forced_ending +
# prompts.build_resolution_directive; gameplay gating lives in the orchestrator.
RESOLUTION_BUDGET_ROUNDS = 6      # climax rounds of soft pressure before escalating to an explicit final-choice prompt
FORCED_NO_PROGRESS_ROUNDS = 8    # consecutive rounds with no new clue → stall → force an ending
FORCED_AFTER_ROUND = 12          # never force before this round (protect fast openings from a premature end)
FORCED_CLIMAX_LINGER_ROUNDS = 12 # rounds stuck in climax → force, even if minor clues keep trickling in

RES_TIER_NONE = "none"
RES_TIER_PRESSURE = "pressure"
RES_TIER_DECISION = "decision"


def resolution_tier(current_act: str, rounds_in_climax: int) -> str:
    """Soft-escalation tier for a SCRIPT session at climax.

    ``none``     — not at climax yet; no resolution pressure.
    ``pressure`` — at climax; nudge Director to steer toward an ending.
    ``decision`` — lingered at climax past the budget; Director must present
                   the player an explicit final choice and trigger an ending
                   when a soft condition is plausibly met.

    Caller is responsible for only invoking this in script mode — the tiers
    are meaningless (and must never fire) in free mode.
    """
    if current_act != ACT_CLIMAX:
        return RES_TIER_NONE
    if rounds_in_climax >= RESOLUTION_BUDGET_ROUNDS:
        return RES_TIER_DECISION
    return RES_TIER_PRESSURE


@dataclass
class ArcData:
    """Persistent player behavior pattern data."""

    frequent_npcs: dict[str, int] = field(default_factory=dict)
    frequent_locations: dict[str, int] = field(default_factory=dict)
    topic_interests: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    focus_npcs: list[str] = field(default_factory=list)
    focus_locations: list[str] = field(default_factory=list)
    # Phase 2.A.1 — current 3-act label. Defaults to intro on a fresh arc.
    current_act: str = ACT_INTRO

    def to_dict(self) -> dict:
        return {
            "frequent_npcs": dict(self.frequent_npcs),
            "frequent_locations": dict(self.frequent_locations),
            "topic_interests": list(self.topic_interests),
            "key_decisions": list(self.key_decisions),
            "focus_npcs": list(self.focus_npcs),
            "focus_locations": list(self.focus_locations),
            "current_act": self.current_act,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ArcData:
        return cls(
            frequent_npcs=dict(data.get("frequent_npcs", {})),
            frequent_locations=dict(data.get("frequent_locations", {})),
            topic_interests=list(data.get("topic_interests", [])),
            key_decisions=list(data.get("key_decisions", [])),
            focus_npcs=list(data.get("focus_npcs", [])),
            focus_locations=list(data.get("focus_locations", [])),
            current_act=str(data.get("current_act") or ACT_INTRO),
        )


def detect_act(
    round_number: int,
    discovered_clues_count: int,
    key_decisions_count: int,
    dramatic_intensity: str | None = None,
) -> str:
    """Heuristically label the current story act.

    Climax wins when ANY late-game signal fires (rounds, clues, key decisions,
    or the Director's own ``dramatic_intensity == "climax"`` self-report).
    Intro requires BOTH the early-round and low-clue signals so a fast-paced
    opening flips to middle as soon as a real clue lands. Anything in between
    is middle.

    The ``dramatic_intensity`` signal is what lets a player who *earns* a
    resolution early (decisive confrontation / final accusation, which the
    Director rates ``climax``) reach the climax act — and thus the resolution
    pressure in ``build_resolution_directive`` — without waiting for the round
    or clue counters. Only an explicit ``"climax"`` rating flips the act; the
    far more common ``"high"`` does not, so ordinary confrontations don't
    prematurely force an ending.
    """
    if (
        round_number >= CLIMAX_ROUND_THRESHOLD
        or discovered_clues_count >= CLIMAX_CLUE_THRESHOLD
        or key_decisions_count >= CLIMAX_KEY_DECISIONS_THRESHOLD
        or dramatic_intensity == ACT_CLIMAX
    ):
        return ACT_CLIMAX
    if round_number < INTRO_ROUND_THRESHOLD and discovered_clues_count < INTRO_CLUE_THRESHOLD:
        return ACT_INTRO
    return ACT_MIDDLE


_ACT_GUIDANCE = {
    ACT_INTRO: "当前处于序幕，节奏放缓；铺设场景、建立人物、埋下钩子",
    ACT_MIDDLE: "张力上升期；加快节奏、激化冲突、让信任与对立成形",
    ACT_CLIMAX: "临近收束；让关键决定推向结局，避免新开线",
}


class NarrativeArcTracker:
    """Tracks player behavior patterns and detects interest focus + act."""

    FOCUS_THRESHOLD = 5

    def update(
        self,
        arc_data: ArcData,
        action_text: str,
        involved_npcs: list[str],
        current_location: str,
        *,
        round_number: int = 0,
        discovered_clues_count: int = 0,
        dramatic_intensity: str | None = None,
    ) -> ArcData:
        for npc_name in involved_npcs:
            arc_data.frequent_npcs[npc_name] = arc_data.frequent_npcs.get(npc_name, 0) + 1

        arc_data.frequent_locations[current_location] = (
            arc_data.frequent_locations.get(current_location, 0) + 1
        )

        arc_data.focus_npcs = [
            name for name, count in arc_data.frequent_npcs.items()
            if count >= self.FOCUS_THRESHOLD
        ]
        arc_data.focus_locations = [
            loc for loc, count in arc_data.frequent_locations.items()
            if count >= self.FOCUS_THRESHOLD
        ]

        # Phase 2.A.1 — recompute current act every update so Director sees a
        # fresh label each turn.
        arc_data.current_act = detect_act(
            round_number=round_number,
            discovered_clues_count=discovered_clues_count,
            key_decisions_count=len(arc_data.key_decisions),
            dramatic_intensity=dramatic_intensity,
        )

        return arc_data

    def build_summary(self, arc_data: ArcData) -> str:
        parts: list[str] = []
        # Lead with the current act so Director's pacing instructions are
        # always aligned with where we are in the story.
        guidance = _ACT_GUIDANCE.get(arc_data.current_act, "")
        if guidance:
            parts.append(f"故事阶段：[{arc_data.current_act}] — {guidance}")
        else:
            parts.append(f"故事阶段：[{arc_data.current_act}]")

        if arc_data.focus_npcs:
            parts.append(f"玩家兴趣焦点NPC：{'、'.join(arc_data.focus_npcs)}")
        if arc_data.focus_locations:
            parts.append(f"玩家常去地点：{'、'.join(arc_data.focus_locations)}")
        if arc_data.key_decisions:
            parts.append(f"关键决定：{'、'.join(arc_data.key_decisions[-3:])}")
        return "\n".join(parts)
