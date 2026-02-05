from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, status

from app.config import Settings


@dataclass(frozen=True)
class SavedImage:
    relative_path: str  # e.g. "masters/1.jpg"
    content_type: str  # e.g. "image/jpeg"
    size_bytes: int


def build_public_url(settings: Settings, *, relative_path: str) -> str:
    """Build URL to a file under media_url_prefix.

    If PUBLIC_BASE_URL is configured, returns absolute URL, otherwise relative.
    """

    prefix = settings.media_url_prefix.rstrip("/")
    rel = relative_path.lstrip("/")
    url = f"{prefix}/{rel}"

    if settings.public_base_url:
        return settings.public_base_url.rstrip("/") + url
    return url


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, path)


def compress_and_save_image(
    settings: Settings,
    *,
    master_id: int,
    content_type: str | None,
    raw: bytes,
    max_side: int = 1024,
    jpeg_quality: int = 82,
) -> SavedImage:
    """Validate, compress and save uploaded image for a master.

    Stores as JPEG at {media_root}/masters/{master_id}.jpg.

    Raises HTTPException(400) on invalid image.
    """

    if content_type and (not content_type.startswith("image/")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    # Lazy import to keep module import lightweight
    try:
        from PIL import Image, ImageOps
    except Exception as e:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image processing is not available (Pillow is missing)",
        ) from e

    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image") from e

    # Convert to RGB for JPEG
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_side:
        img.thumbnail((max_side, max_side))

    out = BytesIO()
    img.save(out, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
    data = out.getvalue()

    rel = f"masters/{master_id}.jpg"
    dst = Path(settings.media_root) / rel
    _atomic_write(dst, data)

    return SavedImage(relative_path=rel, content_type="image/jpeg", size_bytes=len(data))


def delete_media_file(settings: Settings, *, relative_path: str) -> None:
    path = Path(settings.media_root) / relative_path.lstrip("/")
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        # Python <3.8 compat; not needed but safe
        if path.exists():
            path.unlink()
