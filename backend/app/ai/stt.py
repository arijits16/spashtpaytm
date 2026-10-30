"""Speech to text (build plan §10.1).

Saaras transcribes and detects the language in one call, which is what makes
code-mixed speech work: "mujhe loan chahiye for machine" comes back as a single
transcript rather than as two failed attempts in two languages.

**Uploads are validated before they are forwarded**, and by magic bytes rather
than by the declared content type (§10.1). A client controls its own
`Content-Type` header, so trusting it would mean forwarding whatever was posted
to a paid API - and the tunnel is open to the internet during a demo.

**An unclear recording is not an error.** Low `language_probability` or an empty
transcript produces the `didnt_catch` line and a hint to type instead, because a
customer in a noisy shop will hit this and must not be stuck.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.sarvam_client import SarvamError, client_for
from app.config import Settings
from app.journey.states import LANGUAGES, Lang

log = logging.getLogger(__name__)

# §13.5: audio uploads are capped at 2 MB.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# §10.1: clips are capped at 25 s by the recorder; Saaras rejects longer ones.
MAX_CLIP_SECONDS = 25

# Below this, treat the detection as a guess and do not act on it (§10.1).
MIN_LANGUAGE_PROBABILITY = 0.5

# Domain words the model would otherwise mangle. They are the words this
# product cannot afford to mishear.
KEYTERMS = [
    "Paytm",
    "Spasht",
    "EMI",
    "CIBIL",
    "KFS",
    "DigiLocker",
    "Account Aggregator",
    "UPI AutoPay",
]

# Magic-byte prefixes for the formats Saaras accepts (§10.1).
#
# MP4/M4A carries `ftyp` at offset 4, not 0, which is why this is a list of
# (offset, prefix) pairs rather than a simple startswith check.
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (4, b"ftyp", "audio/mp4"),
    (0, b"ID3", "audio/mpeg"),
    (0, b"RIFF", "audio/wav"),
    (0, b"OggS", "audio/ogg"),
    (0, b"\x1a\x45\xdf\xa3", "audio/webm"),
    (0, b"fLaC", "audio/flac"),
)


class AudioRejected(Exception):
    """The upload is not acceptable audio.

    @param reason  'too_large' | 'unsupported'
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def detect_format(audio: bytes) -> str:
    """The media type implied by the bytes, or raise `AudioRejected`."""
    if len(audio) > MAX_UPLOAD_BYTES:
        raise AudioRejected(
            "too_large",
            f"Audio must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if len(audio) < 16:
        raise AudioRejected("unsupported", "That file is too short to be audio.")

    for offset, prefix, media_type in _SIGNATURES:
        if audio[offset : offset + len(prefix)] == prefix:
            return media_type

    # An MPEG frame header, for an mp3 with no ID3 tag.
    if audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0:
        return "audio/mpeg"

    raise AudioRejected("unsupported", "That is not an audio format we can read. Please try again.")


@dataclass(frozen=True, slots=True)
class Transcription:
    """What we heard.

    `confident` is False when the transcript is empty or the language detection
    was a guess - the engine then says `didnt_catch` instead of acting on it.
    """

    text: str
    language: Lang | None
    probability: float
    latency_ms: int

    @property
    def confident(self) -> bool:
        return bool(self.text.strip()) and self.probability >= MIN_LANGUAGE_PROBABILITY


async def transcribe(
    audio: bytes,
    settings: Settings,
    *,
    filename: str = "turn.m4a",
    language_hint: Lang | None = None,
) -> Transcription:
    """Transcribe a clip.

    @param language_hint  The journey's language. Passed through so the model
                          favours it, but `unknown` is used when there is no
                          hint so a customer who switched language mid-sentence
                          is still understood.
    """
    media_type = detect_format(audio)
    client = client_for(settings)

    language_code = language_hint if language_hint in LANGUAGES else "unknown"

    result = await client.post_multipart(
        "/speech-to-text",
        files={"file": (filename, audio, media_type)},
        data={
            "model": settings.sarvam_stt_model,
            "language_code": language_code,
            # Sent as a repeated form field, which is how the API takes a list.
            "keyterms": ",".join(KEYTERMS),
        },
        kind="stt",
    )

    payload = result.payload
    text = str(payload.get("transcript") or "").strip()
    detected = payload.get("language_code")
    probability = payload.get("language_probability")

    language: Lang | None = detected if detected in LANGUAGES else None
    try:
        confidence = float(probability) if probability is not None else 1.0
    except (TypeError, ValueError):
        confidence = 1.0

    # The transcript itself is never logged: it is the customer's own words
    # about their money (§13.8). Only its length and the detection are.
    log.info(
        "stt ok",
        extra={
            "chars": len(text),
            "detected": language,
            "probability": round(confidence, 2),
            "latency_ms": result.latency_ms,
        },
    )

    return Transcription(
        text=text,
        language=language,
        probability=confidence,
        latency_ms=result.latency_ms,
    )


__all__ = [
    "MAX_CLIP_SECONDS",
    "MAX_UPLOAD_BYTES",
    "AudioRejected",
    "SarvamError",
    "Transcription",
    "detect_format",
    "transcribe",
]
