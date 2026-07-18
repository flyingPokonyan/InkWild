"""world_gen_quality_check 确定性层回归测试。

覆盖今天扫描发现的真实缺陷形态：gender 全空、personality 百科腔、must-have 缺失、
可玩不足、base_setting 过薄、事件禁用率过高。语义 judge 层需要 LLM，不在此单测。
"""
from services.world_gen_quality_check import run_deterministic_checks


def _codes(flags):
    return {f.code for f in flags}


def _clean_world() -> dict:
    return {
        "name": "甄嬛传",
        "base_setting": "雍" * 500,
        "world_characters": [
            {"name": "甄嬛", "gender": "女", "personality": "聪慧隐忍，以退为进。"},
            {"name": "华妃", "gender": "女", "personality": "恃宠骄纵，手段狠辣。"},
            {"name": "雍正", "gender": "男", "personality": "多疑寡恩，权欲极强。"},
        ],
        "playable": [{"name": "甄嬛"}, {"name": "华妃"}, {"name": "雍正"}],
        "events_data": [
            {"id": "evt_001", "summary": "结义", "disabled": False},
            {"id": "evt_002", "summary": "专宠", "disabled": False},
        ],
    }


def test_clean_world_has_no_flags():
    assert run_deterministic_checks(_clean_world(), must_have=["甄嬛", "华妃"]) == []


def test_gender_missing_flagged():
    w = _clean_world()
    for c in w["world_characters"]:
        c["gender"] = ""
    flags = run_deterministic_checks(w)
    assert "gender_missing" in _codes(flags)
    g = next(f for f in flags if f.code == "gender_missing")
    assert g.severity == "warning"
    assert len(g.entities) == 3


def test_meta_referential_bio_flagged():
    w = _clean_world()
    w["world_characters"][0]["personality"] = "《甄嬛传》中的女主角甄玉嬛，聪慧才貌。"
    w["world_characters"][1]["description"] = "本作中的角色，恃宠而骄。"
    assert "meta_referential_bio" in _codes(run_deterministic_checks(w))


def test_must_have_missing_is_blocking():
    w = _clean_world()
    flags = run_deterministic_checks(w, must_have=["甄嬛", "皇后", "沈眉庄"])
    mh = next(f for f in flags if f.code == "must_have_missing")
    assert mh.severity == "blocking"
    assert set(mh.entities) == {"皇后", "沈眉庄"}


def test_playable_below_min_blocking():
    w = _clean_world()
    w["playable"] = [{"name": "甄嬛"}]
    flags = run_deterministic_checks(w, playable_min=3)
    pf = next(f for f in flags if f.code == "playable_below_min")
    assert pf.severity == "blocking"


def test_base_setting_thin_flagged():
    w = _clean_world()
    w["base_setting"] = "太短了"
    assert "base_setting_thin" in _codes(run_deterministic_checks(w))


def test_high_disabled_event_ratio_flagged():
    w = _clean_world()
    w["events_data"] = [
        {"id": "evt_001", "summary": "a", "disabled": True},
        {"id": "evt_002", "summary": "b", "disabled": True},
        {"id": "evt_003", "summary": "c", "disabled": False},
    ]
    assert "high_disabled_event_ratio" in _codes(run_deterministic_checks(w))
