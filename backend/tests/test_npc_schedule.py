from engine.prompts import build_npc_schedule_context


def test_schedule_morning():
    npcs = [
        {
            "name": "陈医生",
            "personality": "谨慎的医生",
            "secret": "救治了某人",
            "initial_location": "诊所",
            "schedule": {"上午": "诊所", "下午": "诊所", "傍晚": "镇口茶摊", "夜晚": "后山", "深夜": "后山"},
        },
        {
            "name": "李守夜",
            "personality": "沉默的守夜人",
            "secret": None,
            "initial_location": "镇口",
            "schedule": {"上午": "家中休息", "夜晚": "镇口", "深夜": "镇口"},
        },
    ]

    context = build_npc_schedule_context(npcs, current_time="第1天·上午")
    assert "陈医生" in context
    assert "诊所" in context
    assert "李守夜" in context
    assert "家中休息" in context


def test_schedule_night():
    npcs = [
        {
            "name": "陈医生",
            "personality": "谨慎的医生",
            "secret": "救治了某人",
            "initial_location": "诊所",
            "schedule": {"上午": "诊所", "夜晚": "后山"},
        },
    ]

    context = build_npc_schedule_context(npcs, current_time="第2天·夜晚")
    assert "后山" in context


def test_schedule_empty_uses_initial():
    npcs = [
        {
            "name": "王铁匠",
            "personality": "暴脾气",
            "secret": None,
            "initial_location": "铁匠铺",
            "schedule": {},
        },
    ]

    context = build_npc_schedule_context(npcs, current_time="第1天·上午")
    assert "铁匠铺" in context
