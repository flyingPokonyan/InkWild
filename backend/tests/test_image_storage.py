import io
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from config import settings
from llm.base import ImageResult
from services.image_storage import (
    ImageStorage,
    OSSImageStorage,
    get_image_storage,
    save_generated_image_result,
)


@pytest.mark.asyncio
async def test_get_image_storage_returns_oss_backend(monkeypatch: pytest.MonkeyPatch):
    uploads: list[tuple[str, bytes]] = []

    class FakeBucket:
        def __init__(self, auth, endpoint, bucket_name):
            self.auth = auth
            self.endpoint = endpoint
            self.bucket_name = bucket_name

        def put_object(self, key, data):
            uploads.append((key, data))

    fake_oss2 = SimpleNamespace(
        Auth=lambda ak, sk: ("auth", ak, sk),
        Bucket=FakeBucket,
    )
    monkeypatch.setitem(sys.modules, "oss2", fake_oss2)
    monkeypatch.setattr(settings, "image_storage_backend", "oss")
    monkeypatch.setattr(settings, "oss_access_key_id", "test-ak", raising=False)
    monkeypatch.setattr(settings, "oss_access_key_secret", "test-sk", raising=False)
    monkeypatch.setattr(settings, "oss_endpoint", "oss-cn-shanghai.aliyuncs.com", raising=False)
    monkeypatch.setattr(settings, "oss_bucket_name", "inkwild-assets", raising=False)
    monkeypatch.setattr(settings, "oss_public_base_url", "https://cdn.example.com", raising=False)
    monkeypatch.setattr(settings, "oss_key_prefix", "", raising=False)

    storage = get_image_storage()

    assert isinstance(storage, OSSImageStorage)

    url = await storage.save(b"image-bytes", "worlds/test.png")

    assert uploads == [("worlds/test.png", b"image-bytes")]
    assert url == "https://cdn.example.com/worlds/test.png"


@pytest.mark.asyncio
async def test_generated_png_is_compressed_before_storage():
    source = io.BytesIO()
    Image.new("RGB", (512, 512), (120, 80, 40)).save(source, format="PNG")
    uploads: list[tuple[str, bytes]] = []

    class CaptureStorage(ImageStorage):
        async def save(self, data: bytes, key: str) -> str:
            uploads.append((key, data))
            return f"https://cdn.example.com/{key}"

        async def save_from_url(self, source_url: str, key: str) -> str:
            raise AssertionError("unexpected URL path")

        async def delete(self, key: str) -> None:
            return None

    url = await save_generated_image_result(
        CaptureStorage(),
        ImageResult(base64_data=source.getvalue(), format="png"),
        "worlds/cover/test.png",
    )

    key, data = uploads[0]
    assert key == "worlds/cover/test.webp"
    assert data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    assert len(data) < len(source.getvalue())
    assert url.endswith("/worlds/cover/test.webp")
