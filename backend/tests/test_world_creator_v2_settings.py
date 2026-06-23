"""Test world creator v2 settings configuration."""

from types import SimpleNamespace

import pytest
from config import settings

from services.world_creator_agent_v2 import _ip_location_band


@pytest.mark.no_db
def test_world_creator_v2_flag_default_true():
    """Feature flag defaults to True since 2026-05-12; env var can flip back to False as kill switch."""
    assert settings.world_creator_v2_enabled is True


@pytest.mark.no_db
def test_ip_location_band_none_for_original_world():
    """无研究信号（原创世界）→ 返回 None，让 world_base LLM 读描述自己判断体量。"""
    assert _ip_location_band(None) is None
    assert _ip_location_band(SimpleNamespace(places=[], characters=[0] * 5)) is None


@pytest.mark.no_db
def test_ip_location_band_anchors_on_research_places():
    """IP 世界护栏锚定研究地点数：下限尽量用全、上限留增补空间，且按规模浮动。"""
    # 甄嬛传体量：10 地点 → 下限用全 10，上限 15
    big = _ip_location_band(SimpleNamespace(places=[0] * 10, characters=[0] * 22))
    assert big == (10, 15)
    # 小 IP：3 地点 → 下限兜底 5，上限 8（世界小则少）
    small = _ip_location_band(SimpleNamespace(places=[0] * 3, characters=[0] * 8))
    assert small == (5, 8)
    # 大长篇：16 地点 → 16-20（世界大则充实），上限封顶 20
    huge = _ip_location_band(SimpleNamespace(places=[0] * 16, characters=[0] * 40))
    assert huge == (16, 20)


@pytest.mark.no_db
def test_ip_location_band_decoupled_from_character_count():
    """同样的地点数、角色数差很多 → 护栏不变（地点规模只锚研究地点，不被角色数硬耦合）。"""
    few_chars = _ip_location_band(SimpleNamespace(places=[0] * 8, characters=[0] * 4))
    many_chars = _ip_location_band(SimpleNamespace(places=[0] * 8, characters=[0] * 40))
    assert few_chars == many_chars


@pytest.mark.no_db
def test_research_pack_limits_present():
    """Research pack capacity limits should be present and set."""
    assert settings.research_pack_max_passages == 100
    assert settings.research_pack_max_passage_chars == 600
    assert settings.research_pack_max_admin_description_chars == 50_000
