"""Pure unit tests for listing-photo validation/re-encoding (no database)."""
import io

import pytest
from PIL import Image

from app.modules.commerce import images


def _make(fmt: str, size=(3000, 2000), mode="RGB") -> bytes:
    buf = io.BytesIO()
    fill = (200, 30, 30) if mode == "RGB" else (200, 30, 30, 0)
    Image.new(mode, size, fill).save(buf, fmt)
    return buf.getvalue()


def test_large_photo_is_downscaled_and_gets_a_thumbnail():
    out = images.process_image(_make("JPEG"))
    assert max(out.width, out.height) == images.FULL_MAX_EDGE
    assert Image.open(io.BytesIO(out.data)).format == "JPEG"
    assert max(Image.open(io.BytesIO(out.thumb)).size) == images.THUMB_MAX_EDGE


def test_small_photo_is_never_upscaled():
    out = images.process_image(_make("PNG", (200, 100)))
    assert (out.width, out.height) == (200, 100)


def test_transparency_is_flattened_onto_white_not_black():
    out = images.process_image(_make("PNG", (50, 50), "RGBA"))
    assert min(Image.open(io.BytesIO(out.data)).getpixel((5, 5))) > 240


def test_webp_is_accepted():
    images.process_image(_make("WEBP", (300, 300)))


def test_exif_metadata_including_gps_block_is_stripped():
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # camera make - stands in for any EXIF (GPS lives in the same block)
    buf = io.BytesIO()
    Image.new("RGB", (100, 60), "green").save(buf, "JPEG", exif=exif.tobytes())
    assert b"SecretCamera" in buf.getvalue()

    out = images.process_image(buf.getvalue())
    assert b"SecretCamera" not in out.data
    assert not Image.open(io.BytesIO(out.data)).getexif()


def test_exif_orientation_is_applied_before_stripping():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90deg
    buf = io.BytesIO()
    Image.new("RGB", (100, 60)).save(buf, "JPEG", exif=exif.tobytes())
    out = images.process_image(buf.getvalue())
    assert (out.width, out.height) == (60, 100)


@pytest.mark.parametrize("label,raw", [
    ("empty", b""),
    ("plain text", b"hello, definitely not an image"),
    ("svg with script", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ("truncated jpeg", _make("JPEG")[:500]),
    ("gif", _make("GIF", (10, 10))),
    ("over the byte cap", b"\xff\xd8" + b"0" * (images.MAX_UPLOAD_BYTES + 1)),
])
def test_invalid_uploads_are_rejected(label, raw):
    with pytest.raises(images.InvalidImageError):
        images.process_image(raw)


def test_pixel_count_cap_stops_decompression_bombs():
    buf = io.BytesIO()
    Image.new("L", (7000, 7000), 0).save(buf, "PNG")  # tiny on disk, 49M pixels decoded
    assert len(buf.getvalue()) < images.MAX_UPLOAD_BYTES
    with pytest.raises(images.InvalidImageError, match="dimensions"):
        images.process_image(buf.getvalue())
