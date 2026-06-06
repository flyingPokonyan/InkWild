"""Tests for the IP pack storage helper (T7).

Persists an IPKnowledgePack to the ``ip_knowledge_packs`` table and
verifies the row can be re-read via ORM with the same payload.
"""
from uuid import uuid4

import pytest

from models.ip_knowledge_pack import IPKnowledgePack as IPKnowledgePackRow
from schemas.ip_knowledge_pack import IPCharacter, IPKnowledgePack, IPPlace
from services.ip_pack_storage import save_ip_knowledge_pack


@pytest.mark.asyncio
async def test_save_ip_knowledge_pack_persists_row(db):
    pack = IPKnowledgePack(
        ip_name="逐玉",
        ip_type="tv",
        fidelity_mode="strict",
        summary="test summary",
        characters=[
            IPCharacter(
                name="樊长玉",
                role_in_story="女主",
                relation_to_protagonist="本人",
                traits=["坚韧"],
                must_have=True,
                source_passage_ids=[],
            )
        ],
        places=[IPPlace(name="临安镇", must_have=True)],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )
    draft_id = str(uuid4())

    row = await save_ip_knowledge_pack(db, pack, draft_id=draft_id)
    await db.commit()

    fetched = await db.get(IPKnowledgePackRow, row.id)
    assert fetched is not None
    assert fetched.ip_name == "逐玉"
    assert fetched.fidelity_mode == "strict"
    assert fetched.draft_id == draft_id
    assert fetched.world_id is None
    assert "characters" in fetched.pack_json
    assert fetched.pack_json["characters"][0]["name"] == "樊长玉"


@pytest.mark.asyncio
async def test_save_ip_knowledge_pack_accepts_world_id(db):
    pack = IPKnowledgePack(
        ip_name="X", ip_type="other", fidelity_mode="loose",
        summary="", characters=[], places=[], factions=[],
        iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
    )
    world_id = str(uuid4())

    row = await save_ip_knowledge_pack(db, pack, draft_id="ignored-id", world_id=world_id)
    await db.commit()

    fetched = await db.get(IPKnowledgePackRow, row.id)
    assert fetched is not None
    assert fetched.world_id == world_id
    assert fetched.fidelity_mode == "loose"
