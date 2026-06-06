import pytest
from pathlib import Path

from config import Settings


pytestmark = pytest.mark.no_db


def test_settings_ignores_legacy_anthropic_entries_in_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=test-key",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.deepseek_api_key == "test-key"
    assert settings.deepseek_base_url == "https://api.deepseek.com"


def test_observability_settings_are_available():
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.release_tag == ""
    assert settings.sentry_dsn == ""
    assert settings.backend_sentry_dsn == ""
    assert settings.db_pool_size == 5
    assert settings.db_max_overflow == 10
    assert settings.db_pool_timeout == 30
