"""Listing-photo validation and re-encoding.

Pure functions (no app/DB imports) so they can be unit-tested in isolation.

Security/robustness properties, each deliberate:
  * The file's real format is detected by Pillow from its bytes - the
    client-supplied filename and Content-Type are never trusted.
  * Only JPEG/PNG/WEBP are accepted (no GIF/SVG/TIFF/BMP/PDF polyglots).
  * Byte size AND pixel count are capped (decompression-bomb defence).
  * Output is always a fresh JPEG re-encode, which strips EXIF/GPS metadata
    (a phone photo taken at the farm would otherwise publish its exact
    coordinates) and any appended/embedded payload.
  * EXIF orientation is applied *before* stripping so photos aren't rotated.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_LISTING = 8
MAX_PIXELS = 40_000_000
FULL_MAX_EDGE = 1600
THUMB_MAX_EDGE = 480
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class InvalidImageError(ValueError):
    """Raised with a user-presentable message when an upload is rejected."""


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    thumb: bytes
    width: int
    height: int
    content_type: str = "image/jpeg"


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """JPEG has no alpha channel - composite transparency over white rather
    than letting it turn black."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return img.convert("RGB")


def _encode(img: Image.Image, max_edge: int, quality: int) -> tuple[bytes, tuple[int, int]]:
    resized = img.copy()
    resized.thumbnail((max_edge, max_edge), Image.LANCZOS)  # never upscales
    buffer = io.BytesIO()
    resized.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue(), resized.size


def process_image(raw: bytes) -> ProcessedImage:
    if not raw:
        raise InvalidImageError("The uploaded file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidImageError(f"Image is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per photo)")

    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = probe.format
        width, height = probe.size
        if fmt not in ALLOWED_FORMATS:
            raise InvalidImageError("Unsupported image type - please upload a JPEG, PNG or WebP photo")
        if width * height > MAX_PIXELS:
            raise InvalidImageError("Image dimensions are too large - please upload a smaller photo")
        probe.verify()  # detects truncated/corrupt data; the object is unusable afterwards
        image = Image.open(io.BytesIO(raw))
        image.load()
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise InvalidImageError("The file is not a valid image") from exc

    image = ImageOps.exif_transpose(image)
    image = _flatten_to_rgb(image)
    data, (out_w, out_h) = _encode(image, FULL_MAX_EDGE, 85)
    thumb, _ = _encode(image, THUMB_MAX_EDGE, 80)
    return ProcessedImage(data=data, thumb=thumb, width=out_w, height=out_h)
