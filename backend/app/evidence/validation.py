"""Decode actual media locally; filenames and caller MIME never establish the media type."""

import io

from app.evidence.schemas import (
    IMAGE_BYTES,
    IMAGE_PIXELS,
    VIDEO_BYTES,
)
from app.shared.errors import DomainError


def inspect_media(data: bytes, supplied_type: str) -> dict:
    if not data:
        raise DomainError("MEDIA_EMPTY", 422)
    if supplied_type in {"image/png", "image/jpeg"}:
        if len(data) > IMAGE_BYTES:
            raise DomainError("MEDIA_TOO_LARGE", 413)
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if width * height > IMAGE_PIXELS:
                    raise DomainError("MEDIA_PIXEL_LIMIT", 413)
                expected = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image.format or "")
                if expected != supplied_type:
                    raise DomainError("MEDIA_TYPE_MISMATCH", 422)
                image.verify()
            # Verification alone does not prove a complete decodable pixel stream.
            with Image.open(io.BytesIO(data)) as decoded:
                decoded.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise DomainError("MEDIA_DECODE_FAILED", 422) from None
        return {
            "media_type": "IMAGE",
            "width": width,
            "height": height,
            "duration_ms": None,
            "content_type": supplied_type,
        }
    if supplied_type not in {"video/mp4", "video/webm"}:
        raise DomainError("MEDIA_TYPE_UNSUPPORTED", 422)
    if len(data) > VIDEO_BYTES:
        raise DomainError("MEDIA_TOO_LARGE", 413)
    from app.evidence.video import decode_video

    metadata = decode_video(data, supplied_type)
    return {
        "media_type": "VIDEO",
        "width": metadata["width"],
        "height": metadata["height"],
        "duration_ms": metadata["duration_ms"],
        "content_type": supplied_type,
    }
