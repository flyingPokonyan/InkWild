import sys
from types import SimpleNamespace

import httpx
import pytest

from config import settings
from llm.base import ImageResult
from services.image_storage import (
    ImageStorage,
    ImageStorageUploadError,
    OSSImageStorage,
    get_image_storage,
    save_generated_image_result,
)


@pytest.mark.asyncio
async def test_get_image_storage_returns_oss_backend(monkeypatch: pytest.MonkeyPatch):
    uploads: list[tuple[str, bytes, dict[str, str]]] = []

    class FakeBucket:
        def __init__(self, auth, endpoint, bucket_name):
            self.auth = auth
            self.endpoint = endpoint
            self.bucket_name = bucket_name

        def sign_url(self, method, key, expires, headers=None):
            assert method == "PUT"
            return f"https://upload.example.com/{key}?expires={expires}"

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def put(self, url, *, content, headers):
            uploads.append((url, content, headers))
            return FakeResponse()

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
    monkeypatch.setattr(settings, "oss_upload_timeout_seconds", 1.0, raising=False)
    monkeypatch.setattr(settings, "oss_upload_max_attempts", 2, raising=False)
    monkeypatch.setattr("services.image_storage.httpx.AsyncClient", FakeClient)

    storage = get_image_storage()

    assert isinstance(storage, OSSImageStorage)
    assert storage.endpoint == "https://oss-cn-shanghai.aliyuncs.com"

    url = await storage.save(b"image-bytes", "worlds/test.png")

    assert uploads == [(
        "https://upload.example.com/worlds/test.png?expires=300",
        b"image-bytes",
        {"Content-Type": "image/png"},
    )]
    assert url == "https://cdn.example.com/worlds/test.png"


@pytest.mark.asyncio
async def test_generated_bytes_keep_original_format():
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
        ImageResult(base64_data=b"png-bytes", format="png"),
        "worlds/cover/test.png",
    )

    key, data = uploads[0]
    assert key == "worlds/cover/test.png"
    assert data == b"png-bytes"
    assert url.endswith("/worlds/cover/test.png")


@pytest.mark.asyncio
async def test_oss_timeout_retries_same_bytes_without_regeneration(monkeypatch):
    attempts: list[bytes] = []

    class FakeBucket:
        def sign_url(self, method, key, expires, headers=None):
            return "https://upload.example.com/signed"

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def put(self, url, *, content, headers):
            attempts.append(content)
            raise httpx.ReadTimeout("slow upload")

    storage = object.__new__(OSSImageStorage)
    storage.bucket = FakeBucket()
    storage.bucket_name = "bucket"
    storage.public_base_url = "https://cdn.example.com"
    storage.key_prefix = ""
    monkeypatch.setattr(settings, "oss_upload_timeout_seconds", 0.1)
    monkeypatch.setattr(settings, "oss_upload_max_attempts", 2)
    monkeypatch.setattr(settings, "oss_upload_retry_backoff_seconds", 0.0)
    monkeypatch.setattr("services.image_storage.httpx.AsyncClient", FakeClient)

    with pytest.raises(ImageStorageUploadError):
        await storage.save(b"same-image", "worlds/test.png")

    assert attempts == [b"same-image", b"same-image"]
