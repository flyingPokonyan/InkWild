"""Schema-level tests for IPKnowledgePack and friends.

Covers: construction, must_have_* helper methods, Literal validation.
"""
import pytest
from pydantic import ValidationError

from schemas.ip_knowledge_pack import (
    IPCharacter, IPPlace, IPKnowledgePack, FidelityMode,
)


def test_ip_character_minimal():
    c = IPCharacter(
        name="樊长玉",
        role_in_story="女主",
        relation_to_protagonist="本人",
        traits=["坚韧", "天生神力"],
        must_have=True,
        source_passage_ids=["p_tav_67fbf021"],
    )
    assert c.must_have is True
    assert c.name == "樊长玉"


def test_ip_knowledge_pack_full():
    pack = IPKnowledgePack(
        ip_name="逐玉",
        ip_type="tv",
        fidelity_mode="strict",
        summary="屠户女与落难侯爷假婚成真...",
        characters=[
            IPCharacter(name="樊长玉", role_in_story="女主",
                        relation_to_protagonist="本人", traits=[], must_have=True,
                        source_passage_ids=[]),
        ],
        places=[
            IPPlace(name="临安镇", description="女主家乡", must_have=True, source_passage_ids=[]),
        ],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )
    assert pack.must_have_character_names() == ["樊长玉"]
    assert pack.must_have_place_names() == ["临安镇"]


def test_fidelity_mode_rejects_invalid_value():
    with pytest.raises(ValidationError):
        IPKnowledgePack(
            ip_name="X", ip_type="other", fidelity_mode="invalid_mode",  # type: ignore[arg-type]
            summary="", characters=[], places=[], factions=[],
            iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
        )


def test_ip_type_rejects_invalid_value():
    with pytest.raises(ValidationError):
        IPKnowledgePack(
            ip_name="X", ip_type="manga",  # type: ignore[arg-type]
            fidelity_mode="none",
            summary="", characters=[], places=[], factions=[],
            iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
        )


def test_must_have_filters_correctly():
    pack = IPKnowledgePack(
        ip_name="X", ip_type="other", fidelity_mode="none",
        summary="",
        characters=[
            IPCharacter(name="A", role_in_story="主角",
                        relation_to_protagonist="本人", traits=[],
                        must_have=True, source_passage_ids=[]),
            IPCharacter(name="B", role_in_story="路人",
                        relation_to_protagonist="无", traits=[],
                        must_have=False, source_passage_ids=[]),
        ],
        places=[
            IPPlace(name="P1", must_have=True),
            IPPlace(name="P2", must_have=False),
            IPPlace(name="P3"),  # default False
        ],
        factions=[], iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
    )
    assert pack.must_have_character_names() == ["A"]
    assert pack.must_have_place_names() == ["P1"]
