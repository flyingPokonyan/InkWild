"""Image cropping utilities — center crop bytes to a target aspect ratio.

Used by the world creator pipeline to derive a 3:2 browse-card cover from the
21:9 cinematic hero (single LLM call → two output images, guaranteed visual
consistency).
"""
from __future__ import annotations

import io

import httpx
from PIL import Image

from llm.base import ImageResult


def crop_to_aspect_ratio(image_bytes: bytes, *, target_w: int, target_h: int) -> bytes:
    """Center-crop input bytes to target_w:target_h aspect ratio.

    Preserves the source format (JPEG / PNG / WEBP). Returns new bytes.
    """
    src = Image.open(io.BytesIO(image_bytes))
    src_format = src.format or "JPEG"
    w, h = src.size
    target_ratio = target_w / target_h
    src_ratio = w / h

    if abs(src_ratio - target_ratio) < 1e-3:
        # already the right ratio — re-encode to drop any input-side metadata
        new_w, new_h, left, top = w, h, 0, 0
    elif src_ratio > target_ratio:
        # source is wider than target → crop horizontally
        new_w = int(round(h * target_ratio))
        new_h = h
        left = (w - new_w) // 2
        top = 0
    else:
        # source is taller than target → crop vertically
        new_w = w
        new_h = int(round(w / target_ratio))
        left = 0
        top = (h - new_h) // 2

    cropped = src.crop((left, top, left + new_w, top + new_h))
    out = io.BytesIO()
    save_kwargs: dict = {}
    if src_format == "JPEG":
        save_kwargs["quality"] = 92
        save_kwargs["optimize"] = True
        # JPEG can't encode RGBA — drop alpha if present
        if cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")
    cropped.save(out, format=src_format, **save_kwargs)
    return out.getvalue()


async def materialize_image_bytes(result: ImageResult) -> bytes:
    """Get raw bytes from an ImageResult regardless of url/base64 form.

    For url-form results, fetches the image. For base64-form, returns directly.
    """
    if result.has_data:
        return result.base64_data
    if result.has_url:
        # Follow redirects — image hosts may 301 http→https.
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(result.url)
            resp.raise_for_status()
            return resp.content
    raise ValueError("ImageResult has neither url nor base64_data")
