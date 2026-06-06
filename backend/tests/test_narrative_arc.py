"""Phase 2.A.1 — three-act detection in narrative_arc."""

from engine.narrative_arc import (
    ACT_CLIMAX,
    ACT_INTRO,
    ACT_MIDDLE,
    ArcData,
    NarrativeArcTracker,
    detect_act,
)


# ---------------------------------------------------------------------------
# detect_act unit boundaries
# ---------------------------------------------------------------------------


def test_detect_act_intro_when_early_and_few_clues():
    assert detect_act(round_number=0, discovered_clues_count=0, key_decisions_count=0) == ACT_INTRO
    assert detect_act(round_number=7, discovered_clues_count=2, key_decisions_count=0) == ACT_INTRO


def test_detect_act_flips_to_middle_when_clue_threshold_crossed_early():
    # Even at round 4, 3+ clues means the player is uncovering things fast
    # → no longer "intro".
    assert detect_act(round_number=4, discovered_clues_count=3, key_decisions_count=0) == ACT_MIDDLE


def test_detect_act_flips_to_middle_at_round_threshold():
    # Round 8 alone (no extra clues) is enough to leave intro.
    assert detect_act(round_number=8, discovered_clues_count=0, key_decisions_count=0) == ACT_MIDDLE


def test_detect_act_climax_by_round():
    assert detect_act(round_number=25, discovered_clues_count=2, key_decisions_count=0) == ACT_CLIMAX


def test_detect_act_climax_by_clue_count():
    assert detect_act(round_number=12, discovered_clues_count=6, key_decisions_count=0) == ACT_CLIMAX


def test_detect_act_climax_by_key_decisions():
    assert detect_act(round_number=12, discovered_clues_count=2, key_decisions_count=3) == ACT_CLIMAX


# ---------------------------------------------------------------------------
# Director-reported dramatic_intensity drives climax (replaces the dead
# key_decisions path). Only the director's explicit "climax" self-report flips
# the act early — "high" is too common (any confrontation) to force resolution.
# ---------------------------------------------------------------------------


def test_detect_act_climax_when_director_reports_climax_intensity():
    # Round 5, 1 clue would normally be intro; but the director itself rated the
    # turn climax ("玩家直面凶手/结局条件已接近") → arc enters climax so resolution
    # pressure can arrive when the moment is dramatically earned, not at round 25.
    assert (
        detect_act(
            round_number=5,
            discovered_clues_count=1,
            key_decisions_count=0,
            dramatic_intensity="climax",
        )
        == ACT_CLIMAX
    )


def test_detect_act_high_intensity_does_not_force_climax():
    # "high" (逼问/受压) must NOT flip the act — guards against premature endings.
    assert (
        detect_act(
            round_number=5,
            discovered_clues_count=1,
            key_decisions_count=0,
            dramatic_intensity="high",
        )
        == ACT_INTRO
    )


def test_update_threads_director_intensity_into_climax():
    tracker = NarrativeArcTracker()
    arc = ArcData()
    arc = tracker.update(
        arc,
        action_text="我当众指认王福就是凶手，铁证如山",
        involved_npcs=["王福"],
        current_location="正堂",
        round_number=6,
        discovered_clues_count=2,
        dramatic_intensity="climax",
    )
    assert arc.current_act == ACT_CLIMAX


# ---------------------------------------------------------------------------
# Synthetic 30-turn arc — assert act labels track expected transitions
# within ±2 turns. Acceptance bar from roadmap §6 2.A.1.
# ---------------------------------------------------------------------------


def test_synthetic_30_turn_arc_transitions_within_two_rounds():
    """Drive 30 update() calls with progressively more clues. Expected:
    - rounds 0-7  → intro
    - rounds 8-24 → middle (round threshold hits before clue threshold)
    - rounds 25+  → climax (round threshold)
    """
    tracker = NarrativeArcTracker()
    arc = ArcData()
    expected_at: dict[int, str] = {}

    # Build a discovery curve: 1 clue every 3 turns starting at round 9
    # → reaches 6 clues around round 24 (clue threshold), but the round
    # threshold (25) still wins ordering, so no early climax flip.
    def clues_at(rnd: int) -> int:
        if rnd < 9:
            return 0
        return min(5, (rnd - 9) // 3 + 1)  # cap below clue-climax to isolate round threshold

    actual_acts: list[tuple[int, str]] = []
    for rnd in range(0, 30):
        arc = tracker.update(
            arc,
            action_text=f"turn {rnd}",
            involved_npcs=["王福"],
            current_location="茶摊",
            round_number=rnd,
            discovered_clues_count=clues_at(rnd),
        )
        actual_acts.append((rnd, arc.current_act))

    expected_intro_end = 7  # round 8 should be middle
    expected_climax_start = 25  # round 25+ should be climax

    # All rounds [0, 7] expected intro; allow ±2 round tolerance on transition.
    for rnd, act in actual_acts:
        if rnd <= expected_intro_end - 2:
            assert act == ACT_INTRO, f"round {rnd}: expected intro, got {act}"
        elif (expected_intro_end + 2) < rnd < (expected_climax_start - 2):
            assert act == ACT_MIDDLE, f"round {rnd}: expected middle, got {act}"
        elif rnd >= expected_climax_start + 2:
            assert act == ACT_CLIMAX, f"round {rnd}: expected climax, got {act}"

    # Spot-check the exact transition rounds.
    assert dict(actual_acts)[7] == ACT_INTRO
    assert dict(actual_acts)[8] == ACT_MIDDLE
    assert dict(actual_acts)[25] == ACT_CLIMAX


# ---------------------------------------------------------------------------
# Director context injection — build_summary leads with the act + guidance
# ---------------------------------------------------------------------------


def test_build_summary_starts_with_act_label_and_guidance():
    tracker = NarrativeArcTracker()
    arc = ArcData(current_act=ACT_CLIMAX)
    summary = tracker.build_summary(arc)
    first_line = summary.splitlines()[0]
    assert first_line.startswith("故事阶段：[climax]")
    # Director needs explicit pacing guidance, not just a label.
    assert "收束" in first_line or "结局" in first_line


def test_build_summary_intro_carries_intro_specific_guidance():
    tracker = NarrativeArcTracker()
    summary = tracker.build_summary(ArcData(current_act=ACT_INTRO))
    assert "[intro]" in summary
    assert "铺设" in summary or "建立" in summary


def test_arc_data_round_trip_preserves_current_act():
    arc = ArcData(current_act=ACT_CLIMAX, key_decisions=["指认了王福"])
    restored = ArcData.from_dict(arc.to_dict())
    assert restored.current_act == ACT_CLIMAX
    assert restored.key_decisions == ["指认了王福"]


# --- Phase 2.A.4: rounds_in_climax persistence ---------------------------------

def test_game_state_roundtrips_rounds_in_climax():
    from engine.state_manager import GameState

    s = GameState(current_time="t", current_location="l", rounds_in_climax=4)
    assert GameState.from_dict(s.to_dict()).rounds_in_climax == 4
    # default when absent (back-compat with old persisted state)
    assert GameState.from_dict({"current_time": "t", "current_location": "l"}).rounds_in_climax == 0
