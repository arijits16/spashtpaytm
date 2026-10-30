"""AES-256-GCM for conversation transcripts (build plan §11.2, §13.8).

A transcript is the most personal thing in this database: someone explaining,
in their own language, that they are short of money. It is encrypted at rest
with a fresh 12-byte nonce per message, and only an admin sees it decrypted, on
the dashboard.

AES-256-GCM because it is authenticated: a transcript altered in the database
fails to decrypt rather than decrypting to something else. The key is
`TRANSCRIPT_KEY` from `make keys`, base64 of 32 random bytes.

The journey id is bound in as additional authenticated data, so a ciphertext
cannot be moved from one journey to another even by someone with write access.
"""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings

log = logging.getLogger(__name__)

NONCE_BYTES = 12
KEY_BYTES = 32


class TranscriptKeyMissing(RuntimeError):
    """`TRANSCRIPT_KEY` is absent or malformed. Run `make keys`."""


@lru_cache(maxsize=2)
def _cipher(key_b64: str) -> AESGCM:
    try:
        key = base64.b64decode(key_b64, validate=True)
    except Exception as exc:
        raise TranscriptKeyMissing("TRANSCRIPT_KEY is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise TranscriptKeyMissing(
            f"TRANSCRIPT_KEY decodes to {len(key)} bytes, expected {KEY_BYTES}"
        )
    return AESGCM(key)


def encrypt(plaintext: str, settings: Settings, *, aad: str = "") -> tuple[bytes, bytes]:
    """Encrypt one message. Returns `(ciphertext, nonce)`.

    @param aad  Additional authenticated data - the journey id. Not secret, but
                bound to the ciphertext, so moving a row between journeys breaks
                decryption instead of silently succeeding.
    """
    if not settings.transcript_key:
        raise TranscriptKeyMissing("TRANSCRIPT_KEY is not set. Run `make keys`.")

    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _cipher(settings.transcript_key).encrypt(
        nonce, plaintext.encode("utf-8"), aad.encode("utf-8") or None
    )
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes, settings: Settings, *, aad: str = "") -> str | None:
    """Decrypt one message, or None if it cannot be authenticated.

    None rather than an exception: the dashboard shows "[unreadable]" for a row
    whose key has rotated, which is a better answer than a 500 on a page that is
    showing twenty other rows correctly.
    """
    if not settings.transcript_key:
        return None
    try:
        plaintext = _cipher(settings.transcript_key).decrypt(
            nonce, ciphertext, aad.encode("utf-8") or None
        )
    except (InvalidTag, TranscriptKeyMissing, ValueError):
        log.warning("transcript could not be decrypted")
        return None
    return plaintext.decode("utf-8")
