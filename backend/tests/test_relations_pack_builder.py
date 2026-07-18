from schemas.character_v2 import Character
from schemas.shared_events import SharedEvent
from services.relations_pack_builder import build_relations_pack


def _ch(name, faction=""):
    return Character(name=name, personality="p", faction=faction)


def test_relations_from_shared_events():
    chars = [_ch("A"), _ch("B"), _ch("C")]
    events = [
        SharedEvent(id="e1", title="T1", summary="S", involved_npcs=["A","B"], source_passage_ids=[]),
        SharedEvent(id="e2", title="T2", summary="S", involved_npcs=["B","C"], source_passage_ids=[]),
    ]
    pack = build_relations_pack(chars, events)

    a_rels = pack.relations_by_npc.get("A", [])
    assert any(r.target == "B" and r.kind == "event_tied" and r.why == "e1" for r in a_rels)

    b_rels = pack.relations_by_npc.get("B", [])
    assert any(r.target == "A" and r.why == "e1" for r in b_rels)
    assert any(r.target == "C" and r.why == "e2" for r in b_rels)


def test_explicit_character_relations_are_preserved_in_runtime_pack():
    from schemas.character_v2 import CharacterPeerRelation

    a = _ch("A")
    a.initial_peer_relations = [CharacterPeerRelation(target="B", trust=-8, kind="宿敌")]
    pack = build_relations_pack([a, _ch("B")], shared_events=[])

    relation = pack.relations_by_npc["A"][0]
    assert relation.target == "B"
    assert relation.trust == -8
    assert relation.kind == "宿敌"
    assert relation.why == "character.initial_peer_relations"


def test_no_self_relation():
    chars = [_ch("A"), _ch("B")]
    events = [SharedEvent(id="e1", title="T", summary="S", involved_npcs=["A","B"], source_passage_ids=[])]
    pack = build_relations_pack(chars, events)
    a_rels = pack.relations_by_npc.get("A", [])
    assert not any(r.target == "A" for r in a_rels)


def test_same_faction_default():
    chars = [_ch("A","gangX"), _ch("B","gangX"), _ch("C","gangY")]
    pack = build_relations_pack(chars, shared_events=[], same_faction_default_trust=3)
    a_rels = pack.relations_by_npc.get("A", [])
    same_faction = [r for r in a_rels if r.target == "B" and r.kind == "同派系"]
    assert len(same_faction) == 1
    assert same_faction[0].trust == 3


def test_enemy_faction_explicit_pairs():
    chars = [_ch("A","gangX"), _ch("B","gangY"), _ch("C","gangX")]
    pack = build_relations_pack(
        chars, shared_events=[],
        enemy_faction_pairs=[("gangX","gangY")],
        enemy_faction_default_trust=-3,
    )
    a_rels = pack.relations_by_npc.get("A", [])
    enemy = [r for r in a_rels if r.target == "B" and r.kind == "敌对派系"]
    assert len(enemy) == 1
    assert enemy[0].trust == -3


def test_max_faction_core_npcs_caps_relations():
    chars = [_ch(f"X{i}", "F1") for i in range(5)]
    pack = build_relations_pack(chars, shared_events=[], max_faction_core_npcs=2)
    x0_rels = pack.relations_by_npc.get("X0", [])
    same_faction = [r for r in x0_rels if r.kind == "同派系"]
    assert len(same_faction) <= 2  # 至多和 2 个同派系核心建关系


def test_dedup_target_kind():
    """同 (target, kind) 只保留一个 relation。"""
    chars = [_ch("A"), _ch("B")]
    events = [
        SharedEvent(id="e1", title="T1", summary="S", involved_npcs=["A","B"], source_passage_ids=[]),
        SharedEvent(id="e2", title="T2", summary="S", involved_npcs=["A","B"], source_passage_ids=[]),
    ]
    pack = build_relations_pack(chars, events)
    a_to_b = [r for r in pack.relations_by_npc["A"] if r.target == "B" and r.kind == "event_tied"]
    assert len(a_to_b) == 1
