"""Tests for engine/structural_grounding.py (spec 2026-06-03 grounded structural
evolution). is_grounded is a pure deterministic predicate: it reads only
structured state (committed facts + this turn's per-NPC actions), never the
player's words or ambient narration (INV-1 — guaranteed by the signature: there
is no player_input/narration parameter)."""
from engine.state_manager import GameState
from engine.structural_grounding import is_grounded


def _claim(**kw):
    base = {
        "claim_key": "char.role.zhenhuan",
        "claim_text": "甄嬛奉太后懿旨总摄六宫",
        "kind": "entity_role_changed",
        "target_ref": "甄嬛",
        "premise": {"type": "authority_decree", "required_entity": "太后", "detail": "奉太后懿旨"},
        "status": "in_play",
    }
    base.update(kw)
    return base


def test_authority_absent_is_ungrounded_despite_bystander_compliance():
    """N2 root failure: player fakes 太后懿旨; bystander servants comply in the
    scene, but the *required authority* (太后) is not present/acting → ungrounded.
    Bystander compliance is never grounding."""
    turn_actions = [
        {"npc_name": "崔槿汐", "dialogue": "奴婢谨遵小主吩咐。", "physical": "叩首大礼"},
        {"npc_name": "流朱", "dialogue": "", "physical": "跪下"},
    ]
    verdict = is_grounded(_claim(), structural_facts=[], turn_actions=turn_actions)
    assert verdict["grounded"] is False
    assert verdict["reason"] == "required_entity_absent"


def test_no_required_entity_is_ungrounded():
    """H7: a bare fait-accompli with no invoked authority/mechanism (e.g.
    '我一掌击毙在场所有侍卫') has no entity that could ground it → ungrounded,
    distinct reason from an absent-but-required authority."""
    claim = _claim(
        claim_text="我一掌击毙在场所有侍卫",
        kind="entity_removed",
        target_ref="侍卫",
        premise={"type": "physical_act", "required_entity": None, "detail": "强行壮举"},
    )
    verdict = is_grounded(claim, structural_facts=[], turn_actions=[])
    assert verdict["grounded"] is False
    assert verdict["reason"] == "no_required_entity"


def test_prerequisite_met_grounds_compositionally():
    """Earned path: a structural change whose prerequisites are already COMMITTED
    facts is grounded compositionally — not by the player's assertion."""
    facts = [{"fact_key": "char.removed.huafei", "fact_text": "华妃已赐死", "kind": "entity_removed"}]
    claim = _claim(
        claim_text="甄嬛接掌华妃旧部",
        premise={"type": "prerequisite", "required_entity": None,
                 "requires": ["char.removed.huafei"], "detail": "政敌已除，权力真空"},
    )
    verdict = is_grounded(claim, structural_facts=facts, turn_actions=[])
    assert verdict["grounded"] is True
    assert verdict["basis"] == "prerequisite"


def test_prerequisite_unmet_is_ungrounded():
    """Prerequisite premise whose required facts are NOT all committed → ungrounded."""
    claim = _claim(
        premise={"type": "prerequisite", "required_entity": None,
                 "requires": ["char.removed.huafei"], "detail": "政敌已除"},
    )
    verdict = is_grounded(claim, structural_facts=[], turn_actions=[])
    assert verdict["grounded"] is False
    assert verdict["reason"] == "prerequisite_unmet"


# ---- claim ledger (structural_claims) ----

def _gs(**kw):
    base = dict(current_time="第1天·上午", current_location="碎玉轩")
    base.update(kw)
    return GameState(**base)


def test_structural_claims_defaults_empty_and_roundtrips():
    s = _gs()
    assert s.structural_claims == []
    s.structural_claims.append(
        {"claim_key": "char.role.zhenhuan", "claim_text": "甄嬛奉太后懿旨总摄六宫",
         "kind": "entity_role_changed", "target_ref": "甄嬛",
         "premise": {"type": "authority_decree", "required_entity": "太后"},
         "status": "in_play", "round_made": 11, "last_seen_round": 11}
    )
    restored = GameState.from_dict(s.to_dict())
    assert restored.structural_claims == s.structural_claims


def test_record_claim_dedupes_by_key_so_repetition_does_not_accumulate():
    """INV-2: re-asserting the same structural claim refreshes last_seen_round
    but never appends a duplicate — repetition can never accumulate into grounding."""
    from engine.structural_grounding import record_or_refresh_claim
    s = _gs(round_number=11)
    claim = {"claim_key": "char.role.zhenhuan", "claim_text": "甄嬛总摄六宫",
             "kind": "entity_role_changed", "target_ref": "甄嬛",
             "premise": {"type": "authority_decree", "required_entity": "太后"}}
    record_or_refresh_claim(s, claim)
    assert len(s.structural_claims) == 1
    assert s.structural_claims[0]["status"] == "in_play"
    assert s.structural_claims[0]["round_made"] == 11

    s.round_number = 14  # player keeps re-asserting it across turns
    record_or_refresh_claim(s, dict(claim, claim_text="本宫奉先帝遗诏总摄六宫"))
    assert len(s.structural_claims) == 1                       # no duplicate
    assert s.structural_claims[0]["last_seen_round"] == 14     # refreshed
    assert s.structural_claims[0]["round_made"] == 11          # original preserved


# ---- parse_claim: 把玩家断言解析成 claim+premise（纯函数，仿 parse_detection）----

def test_parse_claim_extracts_premise_with_required_entity():
    from engine.structural_grounding import parse_claim
    raw = ('{"claim_key": "char.role.zhenhuan", "claim_text": "甄嬛奉太后懿旨总摄六宫",'
           ' "kind": "entity_role_changed", "target_ref": "甄嬛",'
           ' "premise": {"type": "authority_decree", "required_entity": "太后", "detail": "奉懿旨"}}')
    c = parse_claim(raw)
    assert c is not None
    assert c["claim_key"] == "char.role.zhenhuan"
    assert c["kind"] == "entity_role_changed"
    assert c["premise"]["required_entity"] == "太后"
    assert c["premise"]["type"] == "authority_decree"


def test_parse_claim_garbage_returns_none():
    from engine.structural_grounding import parse_claim
    assert parse_claim("不是 JSON 的胡言乱语") is None
    assert parse_claim("") is None


def test_parse_claim_no_claim_flag_returns_none():
    from engine.structural_grounding import parse_claim
    assert parse_claim('{"is_claim": false}') is None


# ---- interpret_assent: 窄读所需实体自己动作是否构成同意/enact（纯解析，保守）----

def test_interpret_assent_true_false_and_garbage():
    from engine.structural_grounding import interpret_assent
    assert interpret_assent('{"assents": true}') is True
    assert interpret_assent('{"assents": false}') is False
    assert interpret_assent("模糊不清的胡言") is False   # 保守：拿不准 → 不算同意
    assert interpret_assent("") is False


def test_prerequisite_does_not_bypass_required_authority():
    """#1: an authority_decree claim must NOT ground via a (possibly LLM-mis-filled)
    requires list while its required authority is absent. Only type==prerequisite
    grounds compositionally."""
    facts = [{"fact_key": "char.removed.huafei", "fact_text": "华妃已赐死", "kind": "entity_removed"}]
    claim = _claim(premise={"type": "authority_decree", "required_entity": "太后",
                            "requires": ["char.removed.huafei"], "detail": "奉懿旨"})
    verdict = is_grounded(claim, structural_facts=facts, turn_actions=[])  # 太后 not present
    assert verdict["grounded"] is False
    assert verdict["reason"] == "required_entity_absent"


def test_record_claim_empty_key_does_not_merge_distinct_claims():
    """#3: claims without an explicit claim_key must not all collapse into one
    entry; a stable key is derived from kind:target_ref."""
    from engine.structural_grounding import record_or_refresh_claim
    s = _gs(round_number=1)
    record_or_refresh_claim(s, {"claim_key": "", "claim_text": "华妃已死",
                                "kind": "entity_removed", "target_ref": "华妃"})
    record_or_refresh_claim(s, {"claim_key": "", "claim_text": "甄嬛掌权",
                                "kind": "entity_role_changed", "target_ref": "甄嬛"})
    assert len(s.structural_claims) == 2


def test_normalize_claim_from_director_dict():
    """Director emits structural_claim as a dict (not a JSON string); normalize_claim
    validates/normalizes it the same way parse_claim does for its JSON tail."""
    from engine.structural_grounding import normalize_claim
    d = {"claim_key": "char.role.zhenhuan", "claim_text": "甄嬛总摄六宫",
         "kind": "entity_role_changed", "target_ref": "甄嬛",
         "premise": {"type": "authority_decree", "required_entity": "太后"}}
    c = normalize_claim(d)
    assert c["premise"]["required_entity"] == "太后"
    assert c["kind"] == "entity_role_changed"
    assert c["premise"]["type"] == "authority_decree"
    assert normalize_claim(None) is None
    assert normalize_claim({"claim_text": ""}) is None


# ---- build_structural_claims_context: 未了结主张 → 喂导演的 reckoning 上下文（H5 消费）----

def test_claims_context_includes_in_play_and_exposed_excludes_grounded_and_stale():
    from engine.structural_grounding import build_structural_claims_context
    claims = [
        {"claim_text": "甄嬛总摄六宫", "status": "in_play", "last_seen_round": 12},
        {"claim_text": "甄嬛已是皇后", "status": "exposed", "last_seen_round": 11},
        {"claim_text": "甄嬛与眉庄结盟", "status": "grounded", "last_seen_round": 10},   # 已晋升=事实, 不该出现
        {"claim_text": "三回合前提过的旧声称", "status": "in_play", "last_seen_round": 4},  # 过期
    ]
    ctx = build_structural_claims_context(claims, current_round=13, window=3)
    assert "甄嬛总摄六宫" in ctx           # in_play 近期 → 在
    assert "甄嬛已是皇后" in ctx           # exposed → 在
    assert "结盟" not in ctx               # grounded → 不在
    assert "三回合前" not in ctx           # 过期 → 不在
    assert "未" in ctx or "承认" in ctx    # 含"世界未予承认"类措辞


def test_claims_context_empty_when_nothing_unresolved():
    from engine.structural_grounding import build_structural_claims_context
    assert build_structural_claims_context([], current_round=5) == ""
    assert build_structural_claims_context(
        [{"claim_text": "x", "status": "grounded", "last_seen_round": 5}], current_round=5
    ) == ""
