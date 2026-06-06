"""Image cropper utility tests."""
import io
from PIL import Image
import pytest

from services.image_cropper import crop_to_aspect_ratio, materialize_image_bytes
from llm.base import ImageResult


def _make_test_image_bytes(width: int, height: int, color: tuple = (50, 50, 50), fmt: str = "JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_crop_21_9_to_3_2_horizontal():
    """21:9 source (2880x1234) cropped to 3:2 should remove width, keep height."""
    src = _make_test_image_bytes(2880, 1234)
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.height == 1234
    # 1234 * 3/2 = 1851
    assert out_img.width == 1851
    # ratio close to 3:2
    assert abs((out_img.width / out_img.height) - 1.5) < 0.01


def test_crop_already_target_ratio_passthrough():
    """If source is already exactly the target ratio, output dimensions match input."""
    src = _make_test_image_bytes(1500, 1000)  # 3:2
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.width == 1500
    assert out_img.height == 1000


def test_crop_preserves_format_jpeg():
    src = _make_test_image_bytes(2000, 1000, fmt="JPEG")
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.format == "JPEG"


def test_crop_preserves_format_png():
    src = _make_test_image_bytes(2000, 1000, fmt="PNG")
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.format == "PNG"


def test_crop_taller_than_target_crops_vertically():
    """3:4 source cropped to 3:2 should remove height."""
    src = _make_test_image_bytes(900, 1200)  # 3:4 ratio
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.width == 900
    # 900 * 2/3 = 600
    assert out_img.height == 600


@pytest.mark.asyncio
async def test_materialize_image_bytes_from_base64():
    """ImageResult with base64_data → returns the raw bytes."""
    raw = _make_test_image_bytes(100, 100)
    result = ImageResult(base64_data=raw, format="jpeg")
    out = await materialize_image_bytes(result)
    assert out == raw
