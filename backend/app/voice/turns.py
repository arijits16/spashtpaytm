"""Attaching audio to a response, and recording the conversation (plan §10.2, §11.2).

Two jobs that both sit between the engine and the wire.

**`attach_audio`** gives each assistant line a `audioUrl`. Cache hits are free,
so on the golden path - where every line is a template that `make tts-cache`
pre-generated - the audio is already on disk and the turn costs nothing extra
(§10.4). A line with no audio simply has none: the captions are always on
screen, so silence degrades to reading rather than to a broken turn.

**`record_turn`** writes the conversation to `conversation_turns`, encrypted
with AES-256-GCM (§11.2). A transcript is the most personal thing in this
database - someone explaining in their own words that they are short of money -
so it is encrypted at rest and only an admin sees it decrypted, on the
dashboard.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.sarvam_client import demo_mode_active
from app.ai.tts import cache_key, cached_url, is_cached, synthesise
from app.config import Settings
from app.db.models.journey import ConversationTurn, Journey
from app.journey.responses import Message, TurnResponse
from app.journey.states import Lang
from app.trust.crypto_box import TranscriptKeyMissing, encrypt

log = logging.getLogger(__name__)


async def attach_audio(response: TurnResponse, settings: Settings) -> None:
    """Fill in `audioUrl` on every assistant message, in place.

    Cache hits are resolved synchronously. Misses are synthesised concurrently,
    because a turn can carry three explanation lines and doing them in sequence
    would triple the wait for no reason.

    In demo mode nothing is synthesised - only cache hits are attached - so a
    dead network produces a journey that still speaks its pre-generated lines
    (§10.6).
    """
    language: Lang = response.language
    pending: list[tuple[int, Message]] = []

    for index, message in enumerate(response.messages):
        if message.role != "assistant" or not message.text.strip():
            continue

        key = cache_key(message.text, language, settings)
        if is_cached(key):
            response.messages[index] = message.model_copy(update={"audioUrl": cached_url(key)})
        else:
            pending.append((index, message))

    if not pending or demo_mode_active(settings):
        if pending:
            log.info("demo mode: %d line(s) have no cached audio", len(pending))
        return

    urls = await asyncio.gather(
        *(synthesise(message.text, language, settings) for _, message in pending),
        return_exceptions=True,
    )

    for (index, message), url in zip(pending, urls, strict=True):
        if isinstance(url, BaseException):
            log.warning("tts failed for a line", extra={"error": type(url).__name__})
            continue
        if url:
            response.messages[index] = message.model_copy(update={"audioUrl": url})


def record_turn(
    db: Session,
    journey: Journey,
    settings: Settings,
    *,
    user_text: str,
    assistant_messages: list[str],
    source: str,
    stt_ms: int | None = None,
    llm_ms: int | None = None,
    tts_ms: int | None = None,
) -> None:
    """Append this turn's lines to `conversation_turns`, encrypted.

    @param source  'voice' | 'text' | 'tap' | 'voice-demo'.

    The journey id is bound in as additional authenticated data, so a ciphertext
    cannot be moved between journeys even by someone with write access to the
    table.

    A missing `TRANSCRIPT_KEY` is logged and skipped rather than raised: losing
    the transcript of a turn is bad, and losing the *turn* because we could not
    store its transcript would be worse.
    """
    next_turn = (
        db.scalar(
            select(func.coalesce(func.max(ConversationTurn.turn_no), 0)).where(
                ConversationTurn.journey_id == journey.id
            )
        )
        or 0
    ) + 1

    lines: list[tuple[str, str]] = []
    if user_text.strip():
        lines.append(("user", user_text))
    lines.extend(("assistant", text) for text in assistant_messages if text.strip())

    aad = str(journey.id)

    for offset, (role, text) in enumerate(lines):
        try:
            ciphertext, nonce = encrypt(text, settings, aad=aad)
        except TranscriptKeyMissing:
            log.warning("TRANSCRIPT_KEY is not set; transcript not stored. Run `make keys`.")
            return

        db.add(
            ConversationTurn(
                journey_id=journey.id,
                turn_no=next_turn + offset,
                role=role,
                text_enc=ciphertext,
                nonce=nonce,
                language=journey.language,
                source=source,
                # Attributed to the user's line, which is the one the latency
                # was spent on; the assistant's lines carry none.
                stt_ms=stt_ms if role == "user" else None,
                llm_ms=llm_ms if role == "assistant" else None,
                tts_ms=tts_ms if role == "assistant" else None,
            )
        )

    db.flush()
