"""Image storage abstraction — local filesystem now, OSS/S3 later.

Usage:
    storage = get_image_storage()
    url = await storage.save(image_bytes, "worlds/cover.png")
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import re
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
import structlog

from config import settings
from llm.base import ImageResult

logger = structlog.get_logger()

_oss_upload_sem: asyncio.Semaphore | None = None
_oss_upload_sem_cap: int | None = None


class ImageStorageUploadError(RuntimeError):
    """Storage exhausted its own retries; callers must not regenerate the image."""


def _get_oss_upload_semaphore() -> asyncio.Semaphore:
    global _oss_upload_sem, _oss_upload_sem_cap
    cap = max(int(settings.oss_upload_concurrency), 1)
    if _oss_upload_sem is None or _oss_upload_sem_cap != cap:
        _oss_upload_sem = asyncio.Semaphore(cap)
        _oss_upload_sem_cap = cap
    return _oss_upload_sem


class ImageStorage(ABC):
    """Abstract image storage backend."""

    @abstractmethod
    async def save(self, data: bytes, key: str) -> str:
        """Save image bytes under `key`, return public URL."""

    @abstractmethod
    async def save_from_url(self, source_url: str, key: str) -> str:
        """Download image from URL and save, return public URL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete image by key (best-effort)."""


class LocalImageStorage(ImageStorage):
    """Store images on local filesystem, served via FastAPI static mount.

    Files go to `backend/static/images/<key>`.
    Returned URLs are relative: `/static/images/<key>`.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.image_storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, data: bytes, key: str) -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("image_saved_local", key=key, size=len(data))
        return f"/static/images/{key}"

    async def save_from_url(self, source_url: str, key: str) -> str:
        # Follow redirects because generated image hosts often
        # return a 301 from http:// to https:// for their generated assets;
        # without this httpx raises and the image lands as a placeholder.
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            return await self.save(resp.content, key)

    async def delete(self, key: str) -> None:
        path = self.base_dir / key
        if path.exists():
            path.unlink()
            logger.info("image_deleted_local", key=key)


class OSSImageStorage(ImageStorage):
    """Store images in Alibaba Cloud OSS and return public URLs."""

    def __init__(
        self,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        endpoint: str | None = None,
        bucket_name: str | None = None,
        public_base_url: str | None = None,
        key_prefix: str | None = None,
    ):
        access_key_id = access_key_id or settings.oss_access_key_id
        access_key_secret = access_key_secret or settings.oss_access_key_secret
        endpoint = endpoint or settings.oss_endpoint
        bucket_name = bucket_name or settings.oss_bucket_name
        missing = [
            name
            for name, value in [
                ("oss_access_key_id", access_key_id),
                ("oss_access_key_secret", access_key_secret),
                ("oss_endpoint", endpoint),
                ("oss_bucket_name", bucket_name),
            ]
            if not value
        ]
        if missing:
            raise ValueError(f"Missing OSS config: {', '.join(missing)}")

        import oss2

        raw_endpoint = str(endpoint).strip().rstrip("/")
        self.endpoint = (
            raw_endpoint
            if raw_endpoint.startswith(("https://", "http://"))
            else f"https://{raw_endpoint}"
        )
        self.bucket_name = str(bucket_name)
        self.public_base_url = (public_base_url or settings.oss_public_base_url).rstrip("/")
        self.key_prefix = (key_prefix or settings.oss_key_prefix).strip("/")
        auth = oss2.Auth(str(access_key_id), str(access_key_secret))
        self.bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)

    def _full_key(self, key: str) -> str:
        clean_key = key.lstrip("/")
        if self.key_prefix:
            return f"{self.key_prefix}/{clean_key}"
        return clean_key

    def _public_url(self, key: str) -> str:
        full_key = self._full_key(key)
        if self.public_base_url:
            return f"{self.public_base_url}/{full_key}"
        endpoint = self.endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
        return f"https://{self.bucket_name}.{endpoint}/{full_key}"

    async def _upload_once(
        self,
        data: bytes,
        full_key: str,
        *,
        timeout_seconds: float,
    ) -> None:
        content_type = mimetypes.guess_type(full_key)[0] or "application/octet-stream"
        headers = {"Content-Type": content_type}
        expires = max(300, round(timeout_seconds * 4))
        signed_url = self.bucket.sign_url(
            "PUT",
            full_key,
            expires,
            headers=headers,
        )
        timeout = httpx.Timeout(
            connect=min(10.0, timeout_seconds),
            read=timeout_seconds,
            write=timeout_seconds,
            pool=10.0,
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with asyncio.timeout(timeout_seconds):
                response = await client.put(signed_url, content=data, headers=headers)
            response.raise_for_status()

    async def save(self, data: bytes, key: str) -> str:
        full_key = self._full_key(key)
        timeout_seconds = max(float(settings.oss_upload_timeout_seconds), 0.1)
        max_attempts = max(int(settings.oss_upload_max_attempts), 1)
        backoff_seconds = max(float(settings.oss_upload_retry_backoff_seconds), 0.0)
        semaphore = _get_oss_upload_semaphore()
        queue_started_at = time.monotonic()

        async with semaphore:
            queue_wait_ms = round((time.monotonic() - queue_started_at) * 1000)
            for attempt in range(1, max_attempts + 1):
                started_at = time.monotonic()
                try:
                    await self._upload_once(
                        data,
                        full_key,
                        timeout_seconds=timeout_seconds,
                    )
                except (TimeoutError, httpx.TimeoutException, httpx.NetworkError) as exc:
                    duration_ms = round((time.monotonic() - started_at) * 1000)
                    logger.warning(
                        "image_oss_upload_retry",
                        key=full_key,
                        size=len(data),
                        bucket=self.bucket_name,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        queue_wait_ms=queue_wait_ms,
                        error_type=type(exc).__name__,
                    )
                    if attempt >= max_attempts:
                        raise ImageStorageUploadError(
                            f"OSS upload timed out after {max_attempts} attempts"
                        ) from exc
                    await asyncio.sleep(backoff_seconds * attempt)
                    continue
                except httpx.HTTPStatusError as exc:
                    duration_ms = round((time.monotonic() - started_at) * 1000)
                    status_code = exc.response.status_code
                    retryable = status_code in {408, 409, 425, 429} or status_code >= 500
                    logger.warning(
                        "image_oss_upload_http_error",
                        key=full_key,
                        size=len(data),
                        bucket=self.bucket_name,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        duration_ms=duration_ms,
                        queue_wait_ms=queue_wait_ms,
                        status_code=status_code,
                        retryable=retryable,
                    )
                    if not retryable or attempt >= max_attempts:
                        raise ImageStorageUploadError(
                            f"OSS upload failed with HTTP {status_code}"
                        ) from exc
                    await asyncio.sleep(backoff_seconds * attempt)
                    continue

                duration_ms = round((time.monotonic() - started_at) * 1000)
                logger.info(
                    "image_saved_oss",
                    key=full_key,
                    size=len(data),
                    bucket=self.bucket_name,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    queue_wait_ms=queue_wait_ms,
                )
                return self._public_url(key)

        raise ImageStorageUploadError("OSS upload failed")

    async def save_from_url(self, source_url: str, key: str) -> str:
        # Follow redirects (see LocalImageStorage.save_from_url).
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            return await self.save(resp.content, key)

    async def delete(self, key: str) -> None:
        full_key = self._full_key(key)
        await asyncio.to_thread(self.bucket.delete_object, full_key)
        logger.info("image_deleted_oss", key=full_key, bucket=self.bucket_name)


def get_image_storage() -> ImageStorage:
    """Factory — returns the configured storage backend."""
    backend = settings.image_storage_backend.lower().strip()
    if backend == "oss":
        return OSSImageStorage()
    return LocalImageStorage()


# Returned by image generation when all retries fail. Callers store it as-is
# (no download); frontend renders the placeholder asset.
IMAGE_PLACEHOLDER_URL = "/static/placeholder-cover.png"


def make_image_key(category: str, name: str, ext: str = "png") -> str:
    """Generate a unique storage key like 'worlds/abc123-雾隐镇.png'."""
    short_id = uuid.uuid4().hex[:8]
    safe_name = name.replace("/", "_").replace(" ", "_")[:40]
    return f"{category}/{short_id}-{safe_name}.{ext}"


_UPLOAD_IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_UPLOAD_DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-z+]+);base64,(?P<b64>.+)$", re.DOTALL)


def decode_data_url_image(data_url: str, *, max_bytes: int) -> tuple[bytes, str]:
    """Decode a base64 image data URL → (bytes, ext). Raises AppError on bad input.

    共享给头像 / 公告配图 / 反馈截图等 JSON-base64 上传路径。
    """
    from middleware.error_handler import AppError

    match = _UPLOAD_DATA_URL_RE.match(data_url.strip())
    if not match:
        raise AppError(42202, "图片格式不正确", status_code=422)
    ext = _UPLOAD_IMAGE_TYPES.get(match.group("mime"))
    if not ext:
        raise AppError(42202, "仅支持 PNG / JPEG / WebP 图片", status_code=422)
    try:
        data = base64.b64decode(match.group("b64"), validate=True)
    except Exception:  # noqa: BLE001 — 任何解码失败都按非法图片处理
        raise AppError(42204, "图片数据无法解析", status_code=422)
    if not data:
        raise AppError(42204, "图片为空", status_code=422)
    if len(data) > max_bytes:
        raise AppError(42203, "图片体积超出限制", status_code=422)
    return data, ext


async def save_generated_image_result(storage: ImageStorage, result: ImageResult, key: str) -> str:
    """Persist an image result regardless of whether the provider returned a URL or raw bytes.

    When the provider already returned the placeholder URL (image generation
    gave up after retries), pass it through unchanged — there's nothing to
    download or persist.
    """
    if result.has_url:
        if result.url == IMAGE_PLACEHOLDER_URL:
            return IMAGE_PLACEHOLDER_URL
        return await storage.save_from_url(result.url, key)
    if result.has_data:
        ext = (result.format or "png").lower().strip() or "png"
        normalized_key = key.rsplit(".", 1)[0]
        return await storage.save(result.base64_data, f"{normalized_key}.{ext}")
    return ""
