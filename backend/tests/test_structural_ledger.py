from engine.state_manager import GameState


def _state(**kw):
    base = dict(current_time="第1天·上午", current_location="主厅")
    base.update(kw)
    return GameState(**base)


def test_structural_facts_defaults_empty_and_roundtrips():
    s = _state()
    assert s.structural_facts == []
    s.structural_facts.append(
        {"fact_key": "char.role.x", "fact_text": "X 已登基", "kind": "entity_role_changed",
         "target_ref": "X", "effective_round": 3, "provenance": "authored_milestone"}
    )
    restored = GameState.from_dict(s.to_dict())
    assert restored.structural_facts == s.structural_facts


from engine.structural_ledger import apply_structural_overlay


def test_overlay_appends_entity_note_to_npc_descriptions():
    world = {
        "base_setting": "一座王朝后宫。",
        "npc_descriptions": "华妃年世兰：性烈，掌一宫。\n甄嬛：新晋。",
    }
    facts = [
        {"fact_key": "alive.huafei", "fact_text": "华妃年世兰已于第12回合被赐死，不在人世。",
         "kind": "entity_removed", "target_ref": "年世兰", "effective_round": 12,
         "provenance": "authored_milestone"},
    ]
    out = apply_structural_overlay(world, facts)
    # Original is not mutated.
    assert "已于第12回合被赐死" not in world["npc_descriptions"]
    # Overlay text reaches the spine the Director will read.
    assert "已于第12回合被赐死" in out["npc_descriptions"]


def test_overlay_appends_world_fact_to_base_setting():
    world = {"base_setting": "深空殖民船方舟七号。", "npc_descriptions": ""}
    facts = [
        {"fact_key": "world.capital", "fact_text": "叛军已占领中央舰桥，旧指挥链瓦解。",
         "kind": "world_fact_changed", "target_ref": None, "effective_round": 8,
         "provenance": "authored_milestone"},
    ]
    out = apply_structural_overlay(world, facts)
    assert "叛军已占领中央舰桥" in out["base_setting"]


def test_overlay_noop_when_no_facts():
    world = {"base_setting": "A", "npc_descriptions": "B"}
    out = apply_structural_overlay(world, [])
    assert out["base_setting"] == "A" and out["npc_descriptions"] == "B"


from engine.structural_ledger import commit_structural_fact


def test_commit_appends_to_ledger_and_is_idempotent():
    s = _state(round_number=5)
    fact = {"fact_key": "alive.x", "fact_text": "X 已死。", "kind": "entity_removed",
            "target_ref": "X"}
    assert commit_structural_fact(s, fact) is True
    assert len(s.structural_facts) == 1
    assert s.structural_facts[0]["effective_round"] == 5
    # Same terminal fact again → idempotent no-op.
    assert commit_structural_fact(s, dict(fact)) is False
    assert len(s.structural_facts) == 1


def test_commit_entity_removed_drops_npc_location():
    s = _state(round_number=2)
    s.npc_locations = {"年世兰": "翊坤宫", "甄嬛": "永寿宫"}
    commit_structural_fact(
        s, {"fact_key": "alive.huafei", "fact_text": "年世兰已赐死。",
            "kind": "entity_removed", "target_ref": "年世兰"}
    )
    assert "年世兰" not in s.npc_locations
    assert "甄嬛" in s.npc_locations  # others untouched


def test_commit_relation_redefined_records_without_removing():
    # Generality: relationship structural fact (e.g. romance breakup / alliance).
    s = _state(round_number=4)
    s.npc_locations = {"里夫斯": "舰桥"}
    ok = commit_structural_fact(
        s, {"fact_key": "rel.reeves_carol", "fact_text": "里夫斯与卡萝结成同盟。",
            "kind": "relation_redefined", "target_ref": "里夫斯"}
    )
    assert ok is True
    assert "里夫斯" in s.npc_locations  # relation change does not remove presence
