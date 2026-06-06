"""Cross-artifact integrity checks for publish-time validation."""
from __future__ import annotations

import pytest

from services.cross_artifact_validator import (
    CrossArtifactError,
    validate_cross_artifact,
)


def test_clean_payload_passes():
    world = {
        "characters": [{"name": "Alice"}, {"name": "Bob"}],
        "events_data": [
            {
                "id": "evt_1",
                "present_npcs": ["Alice"],
                "effects": {"spawn_clues": [{"id": "clue_a"}]},
            }
        ],
    }
    script = {
        "events_data": [{"id": "sevt_1", "present_npcs": ["Bob"]}],
        "endings_data": [{"hard_conditions": {"required_clues": ["clue_a"]}}],
    }
    validate_cross_artifact(world, script)  # must not raise


def test_event_npc_not_in_characters_raises():
    world = {
        "characters": [{"name": "Alice"}],
        "events_data": [{"id": "evt_1", "present_npcs": ["Alice", "Ghost"]}],
    }
    script = {"events_data": [], "endings_data": []}
    with pytest.raises(CrossArtifactError) as exc:
        validate_cross_artifact(world, script)
    assert "Ghost" in str(exc.value)
    assert "evt_1" in str(exc.value)


def test_ending_references_unknown_clue_raises():
    world = {
        "characters": [{"name": "Alice"}],
        "events_data": [{"id": "e", "effects": {"spawn_clues": [{"id": "clue_known"}]}}],
    }
    script = {
        "events_data": [],
        "endings_data": [{"hard_conditions": {"required_clues": ["clue_unknown"]}}],
    }
    with pytest.raises(CrossArtifactError) as exc:
        validate_cross_artifact(world, script)
    assert "clue_unknown" in str(exc.value)
