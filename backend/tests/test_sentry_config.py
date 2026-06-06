import pytest

from sentry_config import before_send


pytestmark = pytest.mark.no_db


def test_before_send_scrubs_sensitive_fields():
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer token",
                "cookie": "session=secret",
                "x-admin-key": "admin-secret",
                "user-agent": "pytest",
            },
            "query_string": "api_key=secret&world=1",
            "data": {
                "password": "secret",
                "nested": {"session": "secret"},
                "safe": "visible",
            },
        },
        "extra": {"api_key": "secret", "safe": "visible"},
    }

    scrubbed = before_send(event, hint={})

    assert scrubbed["request"]["headers"]["authorization"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["cookie"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["x-admin-key"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["user-agent"] == "pytest"
    assert scrubbed["request"]["query_string"] == "[Filtered]"
    assert scrubbed["request"]["data"]["password"] == "[Filtered]"
    assert scrubbed["request"]["data"]["nested"]["session"] == "[Filtered]"
    assert scrubbed["request"]["data"]["safe"] == "visible"
    assert scrubbed["extra"]["api_key"] == "[Filtered]"
    assert scrubbed["extra"]["safe"] == "visible"
