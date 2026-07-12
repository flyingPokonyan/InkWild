"""OpenAI-compatible image provider tests."""
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import settings
from llm.openai_compatible import (
    OpenAICompatibleImageProvider,
    _image_httpx_timeout,
    _size_for_aspect_ratio,
)


def test_legacy_ratios_unchanged():
    assert _size_for_aspect_ratio("1:1") == "1024x1024"
    assert _size_for_aspect_ratio("16:9") == "1536x1024"
    assert _size_for_aspect_ratio("3:4") == "1024x1536"
    assert _size_for_aspect_ratio("4:3") == "1536x1024"


def test_new_ratios_supported():
    # 21:9 super-wide hero — width-dominant
    out = _size_for_aspect_ratio("21:9")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - (21 / 9)) < 0.05

    # 3:2 cinematic horizontal card
    out = _size_for_aspect_ratio("3:2")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - 1.5) < 0.05

    # 2:3 vertical portrait
    out = _size_for_aspect_ratio("2:3")
    w, h = (int(x) for x in out.split("x"))
    assert h > w
    assert abs((w / h) - (2 / 3)) < 0.05


def test_unknown_falls_back_to_square():
    assert _size_for_aspect_ratio("nonsense") == "1024x1024"


def test_image_timeout_defaults_to_100_seconds():
    timeout = _image_httpx_timeout()

    assert timeout.read == 100.0


def test_image_timeout_uses_settings(monkeypatch):
    monkeypatch.setattr(settings, "image_generation_timeout_seconds", 42.0)

    timeout = _image_httpx_timeout()

    assert timeout.read == 42.0


@pytest.mark.asyncio
async def test_gpt_image_uses_gateway_supported_request_shape():
    provider = OpenAICompatibleImageProvider(
        api_key="test",
        base_url="https://example.test/v1",
        model="gpt-image-2",
    )
    provider.client.images.generate = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(b"webp-bytes").decode())]
        )
    )

    result = await provider.generate_image("cover", aspect_ratio="3:2")

    provider.client.images.generate.assert_awaited_once_with(
        model="gpt-image-2",
        prompt="cover",
        size="1536x1024",
        quality="high",
    )
    assert result.base64_data == b"webp-bytes"
    assert result.format == "png"
