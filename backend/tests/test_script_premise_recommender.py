"""Tests for script_premise_recommender — grok 选题 / 去重 / 兜底。

Verifies:
- 确定性兜底跳过已被 existing_scripts 覆盖的 canon 事件
- _parse_premises 过滤掉不在世界可玩名单里的 POV
- LLM/grok 合成成功时优先采用，POV 受可玩名单约束
- 任何依赖缺失 / 异常都不抛错，最差返回兜底
"""
from __future__ import annotations

import json

import pytest

import services.script_premise_recommender as r
from schemas.script_premise import ScriptPremise


def _world() -> dict:
    return {
        "name": "权力的游戏",
        "era": "五王之战",
        "genre": "史诗奇幻",
        "base_setting": "维斯特洛大陆…",
        "world_characters": [
            {"name": "琼恩·雪诺", "playable": True},
            {"name": "瑟曦", "playable": True},
            {"name": "艾德", "playable": False},
        ],
        "locations": [{"name": "君临"}, {"name": "长城"}],
        "shared_events": [
            {"era": "劳勃驾崩后", "title": "艾德·史塔克被斩首", "summary": "奈德被处决引爆五王之战"},
            {"era": "五王之战", "title": "红色婚礼", "summary": "佛雷波顿背叛屠杀北境军"},
        ],
        "existing_scripts": [
            {"name": "红色婚礼前夜", "description": "…", "event_names": ["红色婚礼"]},
        ],
    }


def test_deterministic_fallback_skips_covered_events():
    fb = r._deterministic_fallback(_world(), count=4)
    titles = [p.title for p in fb]
    assert "艾德·史塔克被斩首" in titles
    assert "红色婚礼" not in titles  # 已被 existing_scripts 覆盖
    assert fb[0].povs and all(p in {"琼恩·雪诺", "瑟曦"} for p in fb[0].povs)


def test_parse_premises_filters_non_playable_pov():
    data = {
        "premises": [
            {
                "title": "君临的首相之死",
                "theme": "查案",
                "entry_event": "奈德赴君临",
                "povs": ["瑟曦", "图利昂"],  # 图利昂不在可玩名单
                "core_conflict": "权力真空",
                "ending_directions": "好/坏",
            }
        ]
    }
    ps = r._parse_premises(data, r._playable_names(_world()), count=4)
    assert len(ps) == 1
    assert ps[0].povs == ["瑟曦"]


@pytest.mark.asyncio
async def test_recommend_never_raises_without_deps():
    res = await r.recommend_script_premises(
        world_data=_world(), broker=None, llm_router=None, count=2
    )
    assert res  # 退回确定性兜底
    assert all(isinstance(p, ScriptPremise) for p in res)


@pytest.mark.asyncio
async def test_recommend_prefers_llm_synthesis():
    class _FakeProvider:
        async def stream_with_tools(self, **kwargs):
            payload = {
                "premises": [
                    {
                        "title": "长城的誓言",
                        "theme": "守夜人职责与私情",
                        "entry_event": "艰难屯",
                        "povs": ["琼恩·雪诺", "不存在的人"],
                        "core_conflict": "人类内斗 vs 异鬼",
                        "ending_directions": "结盟 / 殉誓",
                    }
                ]
            }
            yield {"type": "text_delta", "text": json.dumps(payload, ensure_ascii=False)}

    res = await r.recommend_script_premises(
        world_data=_world(), broker=None, llm_router=_FakeProvider(), count=2
    )
    assert len(res) == 1
    assert res[0].title == "长城的誓言"
    assert res[0].povs == ["琼恩·雪诺"]  # 非可玩 POV 被剔除
