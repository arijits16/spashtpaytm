"""Text to speech, with an HMAC-keyed cache (build plan §10.2).

Two things matter here, and the second is the interesting one.

**The voices.** One per language, from the §10 voice map, with a `bulbul:v3`
fallback. The Marathi and Hindi voices are female, which is why the templates
are written in the first person feminine (§7.4) - a mismatch between the voice
and the grammar is immediately audible to a native speaker.

**The cache key is an HMAC, not a hash.**

    key = HMAC-SHA256(TTS_CACHE_SECRET, model | speaker | lang | text)

That is what lets `/api/audio/<key>.mp3` be served with **no auth header**. The
app plays audio through `AVAudioPlayer`, which would need the bearer token
plumbed into an audio session; instead the URL itself is the capability. A plain
SHA-256 would not do: anyone could compute the key for a line they guessed and
confirm whether that exact sentence had been spoken to someone. With the secret,
a key is unguessable and reveals nothing.

Cached lines also play instantly, which is what keeps the golden path inside the
4-second voice budget (§10.4).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import re
from pathlib import Path

from app.ai.sarvam_client import SarvamError, client_for
from app.ai.speakable import speakable
from app.config import BACKEND_DIR, Settings
from app.journey.states import Lang

log = logging.getLogger(__name__)

CACHE_DIR = BACKEND_DIR / ".cache" / "tts"

# §10: the voice map, kept in one place.
VOICES: dict[Lang, str] = {
    "mr-IN": "ishita_mr_conversational",
    "hi-IN": "ritu_hi_banking",
    "en-IN": "ishita_en_customer",
}

# Alternates, for when a voice is withdrawn or sounds wrong on the day.
ALTERNATE_VOICES: dict[Lang, str] = {
    "mr-IN": "ritu_mr_insurance",
    "hi-IN": "ishita_hi_banking",
    "en-IN": "ishita_en_customer",
}

# The `bulbul:v3` fallback has a different, smaller voice set.
FALLBACK_VOICE = "ishita"

SAMPLE_RATE = 24_000
PACE = 1.0

# Hex SHA-256, so a path parameter that is not one cannot reach the filesystem.
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


def cache_key(text: str, language: Lang, settings: Settings, *, model: str | None = None) -> str:
    """The unguessable cache key for one spoken line.

    Keyed on the *speakable* text, so two source strings that are read
    identically share one file - and on the model and speaker, so switching
    voices does not serve the old one from cache.
    """
    secret = settings.tts_cache_secret or "dev-tts-cache-secret"
    chosen_model = model or settings.sarvam_tts_model
    speaker = VOICES.get(language, VOICES["en-IN"])
    material = "|".join([chosen_model, speaker, language, speakable(text, language)])
    return hmac.new(secret.encode(), material.encode("utf-8"), hashlib.sha256).hexdigest()


def cache_path(key: str) -> Path:
    """Where a key's mp3 lives. Raises on anything that is not a 64-hex key."""
    if not _KEY_RE.match(key):
        # The key comes from a URL path. Validating the *shape* here means a
        # traversal attempt never reaches `Path`, rather than relying on a
        # later containment check to catch it.
        raise ValueError("malformed audio key")
    return CACHE_DIR / f"{key}.mp3"


def cached_url(key: str) -> str:
    """The relative URL the client plays. Relative so the same payload works on
    localhost and through the tunnel."""
    return f"/api/audio/{key}.mp3"


def is_cached(key: str) -> bool:
    try:
        path = cache_path(key)
    except ValueError:
        return False
    return path.is_file() and path.stat().st_size > 0


async def synthesise(
    text: str, language: Lang, settings: Settings, *, force: bool = False
) -> str | None:
    """Speak `text`, cache it, and return the relative audio URL.

    @param force  Re-synthesise even on a cache hit (`make tts-cache --force`).
    @returns The URL, or **None** when audio is unavailable.

    None rather than an exception: a line with no audio shows as text only
    (§10.6), and a missing voice must never be able to stop the journey. The
    captions are always on screen, so silence degrades to reading.
    """
    if not text.strip():
        return None

    key = cache_key(text, language, settings)
    if not force and is_cached(key):
        return cached_url(key)

    spoken = speakable(text, language)
    client = client_for(settings)
    if not client.configured:
        return None

    for model, speaker in _attempts(language, settings):
        try:
            result = await client.post_json(
                "/text-to-speech",
                {
                    "text": spoken,
                    "target_language_code": language,
                    "speaker": speaker,
                    "model": model,
                    "pace": PACE,
                    "speech_sample_rate": SAMPLE_RATE,
                    "output_audio_codec": "mp3",
                },
                kind="tts",
            )
        except SarvamError as exc:
            log.warning(
                "tts attempt failed",
                extra={"model": model, "kind": exc.kind, "status": exc.status},
            )
            continue

        audio = _first_audio(result.payload)
        if audio is None:
            log.warning("tts returned no audio", extra={"model": model})
            continue

        _write(key, audio)
        log.info(
            "tts cached",
            extra={"language": language, "model": model, "latency_ms": result.latency_ms},
        )
        return cached_url(key)

    return None


def _attempts(language: Lang, settings: Settings) -> list[tuple[str, str]]:
    """(model, speaker) pairs to try, in order.

    The primary voice, then the alternate on the same model, then the older
    model with its own voice - the fallback chain of §10, written out so a
    withdrawn voice degrades instead of going silent.
    """
    primary = settings.sarvam_tts_model
    return [
        (primary, VOICES.get(language, VOICES["en-IN"])),
        (primary, ALTERNATE_VOICES.get(language, VOICES["en-IN"])),
        (settings.sarvam_tts_fallback_model, FALLBACK_VOICE),
    ]


def _first_audio(payload: dict) -> bytes | None:
    """Pull the base64 audio out of the response (`audios[0]`, §10)."""
    audios = payload.get("audios")
    if not isinstance(audios, list) or not audios:
        return None
    try:
        return base64.b64decode(audios[0], validate=True)
    except (binascii.Error, TypeError, ValueError):
        return None


def _write(key: str, audio: bytes) -> None:
    """Write the mp3 atomically.

    Via a temporary file and a rename, because the cache is read by the audio
    route at the same time: a half-written file served to the app is a few
    hundred milliseconds of noise in the middle of a demo.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    final = cache_path(key)
    temporary = final.with_suffix(".mp3.part")
    temporary.write_bytes(audio)
    temporary.replace(final)
