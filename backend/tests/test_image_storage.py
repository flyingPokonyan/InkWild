import sys
from types import SimpleNamespace

import pytest

from config import settings
from services.image_storage import OSSImageStorage, get_image_storage


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

    storage = get_image_storage()

    assert isinstance(storage, OSSImageStorage)

    url = await storage.save(b"image-bytes", "worlds/test.png")

    assert uploads == [("worlds/test.png", b"image-bytes")]
    assert url == "https://cdn.example.com/worlds/test.png"
