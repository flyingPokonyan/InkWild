import pytest

import api.auth as auth_module
from config import settings


class _FakeGoogleClient:
    async def authorize_access_token(self, request):
        return {
            "userinfo": {
                "sub": "g-77",
                "email": "oauth@ex.com",
                "email_verified": True,
                "name": "OAuth User",
                "picture": None,
            }
        }


@pytest.mark.asyncio
async def test_oauth_callback_creates_session_and_redirects(auth_client, monkeypatch):
    monkeypatch.setattr(auth_module.oauth, "create_client", lambda provider: _FakeGoogleClient())
    r = await auth_client.get("/api/auth/oauth/google/callback?state=x&code=y", follow_redirects=False)
    assert r.status_code == 302
    assert settings.auth_cookie_name in r.cookies
    assert r.headers["location"].startswith(settings.public_web_url)


@pytest.mark.asyncio
async def test_oauth_unsupported_provider_404(auth_client):
    r = await auth_client.get("/api/auth/oauth/wechat/start", follow_redirects=False)
    assert r.status_code == 404
