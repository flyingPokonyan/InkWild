import pytest
from pydantic import ValidationError

from schemas.research_pack import ResearchPack, Passage, IPCanon


@pytest.mark.no_db
def test_passage_round_trip():
    p = Passage(id="p_001", text="content", tags=["character:A"], source="tavily")
    assert p.id == "p_001"
    assert p.source == "tavily"


@pytest.mark.no_db
def test_passage_invalid_source_rejected():
    with pytest.raises(ValidationError):
        Passage(id="p_001", text="x", tags=[], source="invalid")


@pytest.mark.no_db
def test_research_pack_empty_default():
    pack = ResearchPack(summary="", passages=[], ip_canon=IPCanon())
    assert pack.passages == []
    assert pack.ip_canon.canonical_names == []


@pytest.mark.no_db
def test_ip_canon_truncation_not_at_schema_layer():
    # truncation 由 builder 做，schema 层不强制
    ipc = IPCanon(canonical_names=["x"] * 300)
    pack = ResearchPack(summary="", passages=[], ip_canon=ipc)
    assert len(pack.ip_canon.canonical_names) == 300


@pytest.mark.no_db
def test_passage_tags_default_empty():
    p = Passage(id="p_001", text="content", source="admin_note")
    assert p.tags == []


@pytest.mark.no_db
def test_ip_canon_all_fields_default_empty():
    ipc = IPCanon()
    assert ipc.title_guesses == []
    assert ipc.canonical_names == []
    assert ipc.canonical_places == []
    assert ipc.iconic_objects == []
    assert ipc.lingo == []
    assert ipc.notable_events == []


@pytest.mark.no_db
def test_passage_valid_sources():
    """Passage should accept all three source types."""
    for source in ["tavily", "ip_probe", "admin_note"]:
        p = Passage(id="p_001", text="content", source=source)
        assert p.source == source


@pytest.mark.no_db
def test_research_pack_with_passages():
    passages = [
        Passage(id="p_001", text="text 1", source="tavily"),
        Passage(id="p_002", text="text 2", tags=["char:X"], source="admin_note"),
    ]
    ipc = IPCanon(canonical_names=["Alice", "Bob"])
    pack = ResearchPack(summary="test summary", passages=passages, ip_canon=ipc)
    assert len(pack.passages) == 2
    assert pack.passages[0].id == "p_001"
    assert pack.ip_canon.canonical_names == ["Alice", "Bob"]
