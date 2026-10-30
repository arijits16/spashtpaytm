"""`POST /api/journeys/{id}/voice` (build plan §8.2, §10.1).

The voice turn: a recorded clip in, a complete `TurnResponse` out. It is the
same engine the tap path uses - speech only produces the `understood_input` that
a tap would have produced (§9) - so there is no way for the spoken journey and
the tapped journey to disagree about what is allowed.

The order of work is the order of the failure modes:

1. **Validate the upload** by magic bytes before anything is forwarded to a paid
   API over a tunnel that is open to the internet (§10.1).
2. **Transcribe.** A failure here is not fatal: it flips the response into demo
   mode rather than erroring, so the journey continues by typing.
3. **Run the engine** on the transcript, exactly as a text turn would.
4. **Attach audio** to the assistant's lines, from the cache when possible.

Latencies for each stage are stored on `conversation_turns` (§10.4), because
"the median voice turn was under 4 seconds" has to be measurable.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.ai import stt
from app.ai.sarvam_client import SarvamError, demo_mode_active
from app.deps import CurrentUser, DbDep, SettingsDep
from app.errors import ApiError
from app.journey import events
from app.journey.engine import ConsentLocked, Engine
from app.journey.responses import TextInput, TurnResponse
from app.journey.states import LANGUAGES, Lang
from app.journey.templates import render
from app.security.ratelimit import client_identity, limiter
from app.voice.turns import attach_audio, record_turn

log = logging.getLogger(__name__)

router = APIRouter(tags=["journeys"], prefix="/journeys")


@router.post("/{journey_id}/voice", response_model=TurnResponse)
async def voice_turn(
    journey_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    # B008 is the wrong call here: `File()` and `Form()` in defaults are
    # FastAPI's documented way to declare multipart parameters, and the names
    # are camelCase because that is what crosses the wire (section 8.1).
    audio: UploadFile = File(...),  # noqa: B008
    clientTurnId: uuid.UUID = Form(...),  # noqa: B008
    languageHint: str | None = Form(default=None),
) -> TurnResponse:
    """Transcribe a clip and take one turn with it."""
    # Routes imported here to avoid a cycle: `journeys.py` owns the helpers and
    # would otherwise import this module to mount it.
    from app.api.journeys import _actor, _finalise, _owned, _replay, _store_turn

    limiter.enforce("voice", client_identity(request, str(user.id)))

    replayed = _replay(db, clientTurnId, user)
    if replayed is not None:
        db.commit()
        return replayed

    journey = _owned(db, journey_id, user)

    raw = await audio.read()
    try:
        stt.detect_format(raw)
    except stt.AudioRejected as exc:
        # 413 and 415 are distinguished because the app can act on them
        # differently: too long means record again, wrong format is a bug.
        code = "upload_too_large" if exc.reason == "too_large" else "unsupported_media"
        raise ApiError(code, str(exc)) from exc

    hint: Lang | None = languageHint if languageHint in LANGUAGES else journey.language  # type: ignore[assignment]

    transcription: stt.Transcription | None = None
    if not demo_mode_active(settings):
        try:
            transcription = await stt.transcribe(
                raw, settings, filename=audio.filename or "turn.m4a", language_hint=hint
            )
        except SarvamError as exc:
            # Not an error to the customer: the response comes back in demo
            # mode with the `didnt_catch` line, and typing still works.
            log.warning("stt unavailable", extra={"kind": exc.kind, "status": exc.status})

    engine = Engine(db, journey, settings, actor=_actor(user))

    if transcription is None or not transcription.confident:
        # §10.1: an unclear recording asks again rather than guessing.
        engine.messages.append(render("didnt_catch", journey.language))
        engine.render_current_step_publicly()
        result = engine.finish()
        response = _finalise(db, journey, result, settings, user)
        response = response.model_copy(
            update={
                "transcript": transcription.text if transcription else None,
                "detectedLanguage": transcription.language if transcription else None,
            }
        )
        await attach_audio(response, settings)
        record_turn(
            db,
            journey,
            settings,
            user_text=transcription.text if transcription else "",
            assistant_messages=result.assistant_messages,
            source="voice",
            stt_ms=transcription.latency_ms if transcription else None,
        )
        _store_turn(db, journey, user, clientTurnId, response)
        db.commit()
        return response

    events.record(
        db,
        journey_id=journey.id,
        actor=_actor(user),
        event_type=events.TURN_RECEIVED,
        step=journey.step,
        # The transcript itself is never in an audit row (§13.8).
        data={
            "kind": "voice",
            "chars": len(transcription.text),
            "detected": transcription.language,
        },
    )

    # §10.1: offer to switch when the detected language differs twice in a row.
    engine.note_detected_language(transcription.language)

    try:
        result = engine.handle(TextInput(type="text", text=transcription.text[:500]))
    except ConsentLocked as exc:
        db.commit()
        raise ApiError("consent_locked", str(exc)) from exc

    if engine.needs_prefill():
        await engine.run_prefill()
        result = engine.finish(user_message=transcription.text)

    response = _finalise(db, journey, result, settings, user)
    response = response.model_copy(
        update={
            "transcript": transcription.text,
            "detectedLanguage": transcription.language,
        }
    )

    await attach_audio(response, settings)
    record_turn(
        db,
        journey,
        settings,
        user_text=transcription.text,
        assistant_messages=result.assistant_messages,
        source="voice",
        stt_ms=transcription.latency_ms,
    )
    _store_turn(db, journey, user, clientTurnId, response)
    db.commit()
    return response
