from engine.intent_system import init_npc_intents


def test_init_npc_intents_builds_free_mode_state():
    state = init_npc_intents(
        [
            {"name": "李守夜", "secret": "知道矿井真相", "knowledge": ["矿井夜里有人"]},
            {"name": "陈医生", "secret": "救治了某人", "knowledge": []},
        ],
        ["矿井有异响"],
    )

    assert state["npc_intents"]["李守夜"]["current_goal"] == "知道矿井真相"
    assert state["info_items"][0]["known_by"] == ["李守夜"]
    assert state["world_conflicts"][0]["description"] == "矿井有异响"
