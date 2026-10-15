"""Uploaded images for the blog: the featured image and pictures inside a post.

A file from a browser is never stored as it arrives. It is opened as an image (so something that
only calls itself a picture is refused), cut down to a sensible size, and written out again as a
fresh JPEG, PNG or WebP under a random name. That drops embedded metadata (location, camera) and
anything hidden in the bytes, and means the name on disk says nothing about the upload.

Files live in `<data dir>/uploads/blog`, beside the database on the mounted data volume, so they
survive a redeploy. They are served by `GET /content/media/{name}` and reached by visitors at
`/media/{name}` on the website.
"""

from __future__ import annotations

import io
import re
import secrets
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path

# Pillow arrives with matplotlib (a declared dependency), so it is in every environment.
from PIL import Image, ImageOps, UnidentifiedImageError

from app.utils.config import get_settings

MAX_UPLOAD_BYTES = 6 * 1024 * 1024
MAX_EDGE = 2000  # pixels, longest side
MAX_PIXELS = 40_000_000  # refuse a decompression bomb before decoding it
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
NAME_PATTERN = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp)$")
CONTENT_TYPES = {ext: mime for ext, mime in FORMATS.values()}


class MediaError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def media_dir() -> Path:
    """Where uploads are kept (created on first use)."""
    settings = get_settings()
    if settings.uploads_dir:
        base = Path(settings.uploads_dir)
    elif settings.database_url.startswith("sqlite:///"):
        base = Path(settings.database_url.removeprefix("sqlite:///")).parent / "uploads"
    else:
        base = Path("data/uploads")
    target = base / "blog"
    target.mkdir(parents=True, exist_ok=True)
    return target


def extract_upload(content_type: str, body: bytes) -> bytes:
    """The file bytes from a request body: a raw image, or a multipart form with one file.

    The editor's image dialog posts a multipart form (field `upload`); the featured-image box
    posts the file itself. No third-party multipart library is needed for either.
    """
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    if kind.startswith("multipart/"):
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        message = BytesParser(policy=HTTP).parsebytes(header + body)
        for part in message.iter_parts():
            if part.get_filename() or part.get_param("name", header="content-disposition") in {
                "upload",
                "file",
            }:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload
        raise MediaError("no_file", "No file was sent.")
    if not body:
        raise MediaError("no_file", "No file was sent.")
    return body


def save_image(data: bytes) -> str:
    """Validate, re-encode and store an image; returns its file name."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise MediaError(
            "too_large", f"Images can be up to {MAX_UPLOAD_BYTES // 1_048_576} MB.", status=413
        )
    try:
        probe = Image.open(io.BytesIO(data))
        width, height = probe.size
        if width * height > MAX_PIXELS:
            raise MediaError("too_large", "That image is too large in pixels.", status=413)
        fmt = probe.format or ""
        if fmt not in FORMATS:
            raise MediaError("bad_type", "Use a JPEG, PNG or WebP image.", status=415)
        probe.verify()
        image = Image.open(io.BytesIO(data))  # verify() leaves the first handle unusable
        image = ImageOps.exif_transpose(image)
    except MediaError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise MediaError("bad_image", "That file is not a readable image.", status=415) from None

    image.thumbnail((MAX_EDGE, MAX_EDGE))
    ext, _ = FORMATS[fmt]
    if fmt == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    name = f"{secrets.token_hex(16)}.{ext}"
    options = {"quality": 85, "optimize": True} if fmt in {"JPEG", "WEBP"} else {"optimize": True}
    image.save(media_dir() / name, format=fmt, **options)
    return name


def path_for(name: str) -> Path | None:
    """The stored file for a public name, or None (the name is checked, never joined blindly)."""
    if not NAME_PATTERN.match(name or ""):
        return None
    path = media_dir() / name
    return path if path.is_file() else None


def public_url(name: str | None) -> str | None:
    return f"/media/{name}" if name else None
