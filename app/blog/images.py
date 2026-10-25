"""Uploaded images: what is accepted, where it goes, and how it is served back.

AN UPLOAD IS THE MOST HOSTILE INPUT THIS APPLICATION TAKES. It arrives from outside, it is bytes rather
than text, it ends up on disk, and it is served back to browsers under our own origin - which is the one
place a file we accepted can run as if we had written it. So:

  * **the type is sniffed from the bytes**, never read from the upload's `Content-Type` and never
    guessed from its name. A caller controls both of those completely.
  * **SVG IS NOT AN IMAGE FORMAT FOR THIS PURPOSE.** An SVG is a document that can carry `<script>`, and
    served from our origin it would run with our origin's privileges, inside a Content-Security-Policy
    that allows `'self'`. PNG, JPEG and WebP only - a raster, which cannot execute.
  * **there is no file name in the protocol at all.** The upload is the raw request body, not a
    multipart form, so the caller never sends a name - there is nothing to sanitise, no `..` to strip,
    no NUL, no unicode that normalises into a directory separator and no case-insensitive collision.
    The stored name is `<our hex id>.<the extension that goes with the sniffed type>`. Refusing the
    envelope also removes a third-party multipart parser from the path of our most hostile input.
  * **the size limit is enforced while reading**, not from `Content-Length`. A client that lies about
    its length finds the connection refused at the limit rather than after filling the disk.
  * **nothing decodes the image.** We store and serve bytes; no library parses them here, so a malformed
    or deliberately malicious file has nothing in this process to exploit. The cost of that choice is
    that we cannot report dimensions, which docs/BLOG_API.md says plainly.
  * **the same bytes twice are the same image.** A writer whose upload times out and retries does not
    leave two copies in var/.

They are served with `Cache-Control: immutable` because an id is never reused: a new file is a new id.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from pathlib import Path

from fastapi.responses import FileResponse

from . import config, store

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]

#: Raster formats only, and the extension each one is stored with. The key is the magic-byte test.
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
EXTENSIONS = {PNG: "png", JPEG: "jpg", WEBP: "webp"}
ACCEPTED = tuple(EXTENSIONS)

class UploadRefused(Exception):
    """Anything wrong with an upload. `status` is what the API answers; `message` is for the writer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def directory() -> Path:
    """Where the files live. Under `var/`, like every other runtime artefact on this box."""
    configured = os.environ.get("BLOG_IMAGES_DIR", "").strip()
    path = Path(configured) if configured else ROOT / "var" / "blog-images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff(data: bytes) -> str | None:
    """The media type these bytes actually are, or None. Magic numbers only.

    WebP is checked on BOTH halves of its header: "RIFF" alone is also the start of a WAV and an AVI,
    and a container we do not understand being served as `image/webp` is exactly the sort of mismatch
    `X-Content-Type-Options: nosniff` is there to make loud rather than to make safe.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    return None


async def read_body_within_limit(request) -> bytes:
    """The request body, refused AT the limit rather than after it.

    THE BODY IS THE IMAGE - this endpoint takes no multipart form, and that is a decision rather than a
    shortcut. A multipart upload would mean parsing an attacker-controlled envelope (boundaries, nested
    headers, a `filename` field) with a third-party parser, to extract bytes we then refuse to trust
    anything the envelope said about. Taking the raw body removes the envelope, removes the dependency,
    and removes the file name from the protocol altogether: there is no name to sanitise because the
    caller never sends one. docs/BLOG_API.md says so plainly, with the curl line.

    `request.stream()` yields the body as it arrives, so a client that lies about `Content-Length` - or
    does not send one - is cut off at the limit instead of after filling the disk.
    """
    limit = config.MAX_IMAGE_BYTES
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        # A cheap refusal before reading anything, for an honest client. Never the only check: the loop
        # below is what makes the limit true for a client that is not honest.
        raise UploadRefused(413, f"the image is {int(declared)} bytes; the limit is "
                                 f"{config.MAX_IMAGE_BYTES} ({config.MAX_IMAGE_KB} KB)")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise UploadRefused(413, f"the image is larger than {config.MAX_IMAGE_KB} KB. Resize it: "
                                     "this is a hero image on a page people open on a phone")
    if not data:
        raise UploadRefused(400, "the request body was empty; the body IS the image file")
    return bytes(data)


def label_of(value: str) -> str:
    """The optional caller-supplied label, reduced to something safe to print. Never a path."""
    return re.sub(r"[^A-Za-z0-9 ._-]", "", (value or "").strip())[:120]


def save(data: bytes, sent_as: str = "") -> dict:
    """Store one image and return its row plus `url`. Raises `UploadRefused` for anything unacceptable."""
    media_type = sniff(data)
    if media_type is None:
        raise UploadRefused(415, "that is not a PNG, a JPEG or a WebP. The type is read from the file's "
                                 "own first bytes, not from its name or its Content-Type, and SVG is "
                                 "refused on purpose - it can carry a script")
    digest = hashlib.sha256(data).hexdigest()
    if (existing := store.image_by_digest(digest)):
        return with_url(existing)       # the same bytes: the same image, not a second copy
    if store.image_count() >= config.MAX_IMAGES:
        raise UploadRefused(409, f"this install holds the maximum of {config.MAX_IMAGES} blog images")

    extension = EXTENSIONS[media_type]
    image_id = secrets.token_hex(16)
    # THE NAME IS OURS. `sent_as` is whatever the optional `X-Blog-Image-Label` header said - a label
    # for the admin page so an operator can tell two uploads apart, stripped to printable characters,
    # recorded in a column and NEVER used to build a path. The path is `image_id` + the sniffed type's
    # extension, both of which we generated.
    target = directory() / f"{image_id}.{extension}"
    target.write_bytes(data)
    row = store.add_image(image_id, media_type=media_type, extension=extension, bytes_len=len(data),
                          sha256=digest, sent_as=label_of(sent_as))
    log.info("blog: image %s stored, %s, %d bytes", image_id, media_type, len(data))
    return with_url(row)


def with_url(row: dict) -> dict:
    from . import paths

    return {**row, "url": paths.media_path(row["id"])}


def file_for(image_id: str) -> tuple[Path, dict] | None:
    """(path on disk, row) for an id, or None. The id must be exactly what we generated."""
    if not image_id or len(image_id) != 32 or any(c not in "0123456789abcdef" for c in image_id):
        return None     # not a shape we ever issued, so it cannot be a file of ours
    row = store.image(image_id)
    if row is None:
        return None
    path = directory() / f"{image_id}.{row['extension']}"
    return (path, row) if path.is_file() else None


def response(image_id: str) -> FileResponse | None:
    """The image, served with the type it was STORED as - which is the type its bytes actually are."""
    found = file_for(image_id)
    if found is None:
        return None
    path, row = found
    return FileResponse(
        path, media_type=row["media_type"],
        headers={
            # An id is never reused, so the bytes behind this URL cannot change.
            "Cache-Control": "public, max-age=31536000, immutable",
            # `inline` with OUR name. A download prompt carrying a caller's own file name is how an
            # upload endpoint becomes a way to hand somebody a file called invoice.pdf.exe.
            "Content-Disposition": f'inline; filename="{image_id}.{row["extension"]}"',
        })
