"""Test world creator v2 settings configuration."""

import pytest
from config import settings


@pytest.mark.no_db
def test_world_creator_v2_flag_default_true():
    """Feature flag defaults to True since 2026-05-12; env var can flip back to False as kill switch."""
    assert settings.world_creator_v2_enabled is True


@pytest.mark.no_db
def test_research_pack_limits_present():
    """Research pack capacity limits should be present and set."""
    assert settings.research_pack_max_passages == 100
    assert settings.research_pack_max_passage_chars == 600
    assert settings.research_pack_max_admin_description_chars == 50_000
