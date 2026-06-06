"""eval pairwise（A/B 相对评测）核心逻辑单测——纯函数，不依赖 LLM/DB。"""
from eval.judge_pairwise import build_pairs, aggregate_pairwise, parse_pairwise_verdict


def _pair(turn=0, a_label="voice", b_label="no_voice"):
    return {"turn": turn, "A_label": a_label, "B_label": b_label}


def test_parse_verdict_maps_pick_A_to_a_label():
    v = parse_pairwise_verdict('{"winner":"A","reason":"好"}', _pair(a_label="voice"))
    assert v["pick"] == "A" and v["winner_label"] == "voice" and v["reason"] == "好"


def test_parse_verdict_maps_pick_B_to_b_label():
    v = parse_pairwise_verdict('{"winner":"B","reason":"x"}', _pair(a_label="voice", b_label="no_voice"))
    assert v["winner_label"] == "no_voice"


def test_parse_verdict_strips_code_fence():
    v = parse_pairwise_verdict('```json\n{"winner":"A","reason":"y"}\n```', _pair(a_label="no_voice"))
    assert v["winner_label"] == "no_voice"


def test_parse_verdict_unparseable_returns_error():
    v = parse_pairwise_verdict('我觉得两个都不错', _pair())
    assert "error" in v and "winner_label" not in v


def _cap(session_id, turns_npc):
    """turns_npc: list of (turn:int, npc_dialogues:dict)."""
    return {"session_id": session_id, "turns": [
        {"turn": t, "player_action": f"p{t}", "narrative": f"n{t}",
         "npc_dialogues": npc, "state_snapshot": {}}
        for t, npc in turns_npc
    ]}


def test_build_pairs_aligns_only_common_turns_with_npc():
    cap_a = _cap("a", [(0, {"X": "a0"}), (1, {"X": "a1"}), (2, {"X": "a2"})])
    cap_b = _cap("b", [(0, {"Y": "b0"}), (1, {"Y": "b1"}), (2, {})])  # voice turn2 无 npc
    pairs = build_pairs(cap_a, cap_b, "no_voice", "voice", seed=42)
    assert [p["turn"] for p in pairs] == [0, 1]


def test_build_pairs_a_content_matches_a_label():
    cap_a = _cap("a", [(t, {"X": f"a{t}"}) for t in range(6)])
    cap_b = _cap("b", [(t, {"Y": f"b{t}"}) for t in range(6)])
    pairs = build_pairs(cap_a, cap_b, "no_voice", "voice", seed=42)
    assert len(pairs) == 6
    for p in pairs:
        expected_a = {"X": f"a{p['turn']}"} if p["A_label"] == "no_voice" else {"Y": f"b{p['turn']}"}
        expected_b = {"X": f"a{p['turn']}"} if p["B_label"] == "no_voice" else {"Y": f"b{p['turn']}"}
        assert p["A"] == expected_a
        assert p["B"] == expected_b
        assert {p["A_label"], p["B_label"]} == {"no_voice", "voice"}


def test_build_pairs_blind_mapping_is_seed_deterministic_and_shuffles():
    cap_a = _cap("a", [(t, {"X": f"a{t}"}) for t in range(8)])
    cap_b = _cap("b", [(t, {"Y": f"b{t}"}) for t in range(8)])
    p1 = build_pairs(cap_a, cap_b, "no_voice", "voice", seed=42)
    p2 = build_pairs(cap_a, cap_b, "no_voice", "voice", seed=42)
    assert [(p["turn"], p["A_label"]) for p in p1] == [(p["turn"], p["A_label"]) for p in p2]
    # 确实做了盲随机左右：8 个 turn 里两个 label 都当过 A
    assert {p["A_label"] for p in p1} == {"no_voice", "voice"}


def test_aggregate_pairwise_winrate_and_per_turn_consensus():
    judge_results = {
        "j1": [{"turn": 0, "winner_label": "voice"}, {"turn": 1, "winner_label": "voice"},
               {"turn": 2, "winner_label": "no_voice"}],
        "j2": [{"turn": 0, "winner_label": "voice"}, {"turn": 1, "winner_label": "no_voice"},
               {"turn": 2, "winner_label": "no_voice"}],
    }
    agg = aggregate_pairwise(judge_results, labels=("no_voice", "voice"))
    assert agg["per_judge"]["j1"] == {"no_voice": 1, "voice": 2, "err": 0}
    assert agg["per_judge"]["j2"] == {"no_voice": 2, "voice": 1, "err": 0}
    assert agg["per_turn"][0] == {"no_voice": 0, "voice": 2}
    assert agg["per_turn"][1] == {"no_voice": 1, "voice": 1}
    assert agg["per_turn"][2] == {"no_voice": 2, "voice": 0}


def test_aggregate_counts_errors():
    judge_results = {"j1": [{"turn": 0, "winner_label": "voice"},
                            {"turn": 1, "error": "parse_fail"}]}
    agg = aggregate_pairwise(judge_results, labels=("no_voice", "voice"))
    assert agg["per_judge"]["j1"]["err"] == 1
    assert agg["per_judge"]["j1"]["voice"] == 1
