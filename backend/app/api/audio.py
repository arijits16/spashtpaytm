"""Serving cached text-to-speech audio (build plan §8.2, §10.2).

`GET /api/audio/<key>.mp3` is **public and unauthenticated**, and that is a
deliberate design decision rather than an oversight.

The key is `HMAC-SHA256(TTS_CACHE_SECRET, model | speaker | lang | text)`, so it
is unguessable without the server's secret: the URL *is* the capability. The
alternative - requiring a bearer token - would mean plumbing auth headers into
`AVAudioPlayer`'s own fetching, and an expired token mid-journey would silence
the assistant rather than show an error anyone could act on.

What a key could leak if guessed is one synthesised sentence of template text
that is the same for every customer. There is nothing personal in the cache.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.ai.tts import cache_path
from app.errors import not_found
from app.security.ratelimit import client_identity, limiter

log = logging.getLogger(__name__)

router = APIRouter(tags=["audio"], include_in_schema=False)


@router.get("/audio/{key}.mp3")
def get_audio(key: str, request: Request) -> FileResponse:
    """Stream a cached mp3."""
    limiter.enforce("public", client_identity(request))

    try:
        path = cache_path(key)
    except ValueError:
        # Not a 64-hex key, so it never touched the filesystem. Reported as a
        # 404 rather than a 422: a malformed key and an unknown one should be
        # indistinguishable to a caller probing the cache.
        log.info("malformed audio key rejected")
        raise not_found("Audio not found") from None

    if not path.is_file():
        raise not_found("Audio not found")

    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={
            # The key is a pure function of the text, so a file at a given key
            # never changes. A year is effectively forever for a demo, and it
            # means a replayed line costs nothing.
            "Cache-Control": "public, max-age=31536000, immutable",
            "Accept-Ranges": "bytes",
        },
    )
