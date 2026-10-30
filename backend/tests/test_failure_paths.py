"""Failure handling end to end (build plan phase 12, item 2).

The product's claim is that nothing in the chain can stop a customer finishing.
These are the links, and what each one degrades to:

| Fails | Degrades to |
|---|---|
| Speech-to-text | The response flips to demo mode and the journey continues by typing |
| Text-to-speech | `audioUrl` is null; the caption is already on screen |
| The LLM | Seeded templates, which is what the golden path uses anyway |
| A malformed or oversized clip | 415 / 413 the app can act on, not a 500 |
| An expired token | 401, so the app ends the session rather than retrying forever |

Every row is asserted against the real HTTP API. The ones that need Sarvam to
*fail* are made to fail on purpose, because an outage that is only ever
hypothetical is an outage nobody has handled.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.sarvam_client import SarvamError
from app.config import settings
from app.security.ratelimit import limiter

# A minimal m4a: `ftyp` at offset 4 is what `stt.detect_format` matches, and the
# padding takes it over the 1 KB floor the app's recorder also enforces.
M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 2048


@pytest.fixture(autouse=True)
def _reset_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def headers() -> dict[str, str]:
    return {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}


def _journey(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/journeys", json={"product": "personal_loan", "language": "mr-IN"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["journeyId"]


def _voice(
    client: TestClient,
    headers: dict[str, str],
    journey_id: str,
    audio: bytes = M4A,
    filename: str = "turn.m4a",
) -> Any:
    """Post a clip exactly as the iPhone's `APIClient.upload` does."""
    return client.post(
        f"/api/journeys/{journey_id}/voice",
        files={"audio": (filename, audio, "audio/mp4")},
        data={"clientTurnId": str(uuid.uuid4()), "languageHint": "mr-IN"},
        headers=headers,
    )


# --- speech-to-text ----------------------------------------------------------


def test_the_voice_contract_the_app_sends_is_accepted(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The field names the iOS recorder uploads: `audio`, `clientTurnId`, `languageHint`."""
    journey_id = _journey(client, headers)
    response = _voice(client, headers, journey_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["journeyId"] == journey_id
    # Demo mode is forced in the suite, so nothing was transcribed: §10.1 says
    # ask again rather than guess on the customer's behalf.
    assert body["transcript"] is None
    assert body["step"]
    assert body["messages"], "the assistant said something rather than nothing"


def test_a_speech_to_text_failure_continues_the_journey(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sarvam is reachable but fails. The turn must not 500."""
    journey_id = _journey(client, headers)

    # Take the route off the demo-mode shortcut so it really calls, then make
    # the call fail the way a timeout does.
    monkeypatch.setattr("app.api.voice.demo_mode_active", lambda _settings: False)

    async def _fail(*args: object, **kwargs: object) -> None:
        raise SarvamError("timeout", "/speech-to-text timed out")

    monkeypatch.setattr("app.ai.stt.transcribe", _fail)

    response = _voice(client, headers, journey_id)
    # Not an error to the customer: the turn succeeds, the journey stays where
    # it was, and the `didnt_catch` line asks again (§10.1).
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] is None
    assert body["messages"]


def test_a_non_audio_upload_is_415_not_500(client: TestClient, headers: dict[str, str]) -> None:
    journey_id = _journey(client, headers)
    response = _voice(client, headers, journey_id, audio=b"this is not audio" * 100)

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media"


def test_an_oversized_clip_is_413_before_it_is_buffered(
    client: TestClient, headers: dict[str, str]
) -> None:
    """The middleware's 2 MB ceiling, which the recorder's 25 s limit stays under."""
    journey_id = _journey(client, headers)
    response = _voice(client, headers, journey_id, audio=b"\x00" * (3 * 1024 * 1024))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_a_voice_turn_on_another_customers_journey_is_404(
    client: TestClient, headers: dict[str, str]
) -> None:
    journey_id = _journey(client, headers)
    other = {"X-Demo-User": "ramesh", "X-Demo-Key": settings.demo_auth_key}
    assert _voice(client, other, journey_id).status_code == 404


# --- text-to-speech ---------------------------------------------------------


def test_a_text_to_speech_failure_leaves_the_caption(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead mouth is a quiet turn, never a failed one (§10.2)."""
    monkeypatch.setattr("app.voice.turns.demo_mode_active", lambda _settings: False)
    monkeypatch.setattr("app.voice.turns.is_cached", lambda _key: False)

    async def _fail(*args: object, **kwargs: object) -> None:
        raise SarvamError("status", "/text-to-speech returned 503", status=503)

    monkeypatch.setattr("app.voice.turns.synthesise", _fail)

    response = client.post(
        "/api/journeys", json={"product": "personal_loan", "language": "mr-IN"}, headers=headers
    )
    assert response.status_code == 200, response.text

    messages = response.json()["messages"]
    assert messages, "the assistant still said something"
    assert all(message["audioUrl"] is None for message in messages)
    assert all(message["text"].strip() for message in messages)


# --- the LLM ----------------------------------------------------------------


def test_an_llm_timeout_falls_back_to_the_seeded_line(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A text turn with the brain unavailable still advances the journey.

    The rules classifier runs first and the templates carry the words, so the
    golden path never depends on a model answering (§10.6).
    """
    monkeypatch.setattr("app.journey.understand.demo_mode_active", lambda _settings: False)

    async def _fail(*args: object, **kwargs: object) -> None:
        raise SarvamError("timeout", "/v1/chat/completions timed out")

    monkeypatch.setattr("app.journey.understand.understand_with_llm", _fail)

    journey_id = _journey(client, headers)
    response = client.post(
        f"/api/journeys/{journey_id}/turn",
        json={
            "clientTurnId": str(uuid.uuid4()),
            "input": {"type": "text", "text": "मला ५०,००० रुपये कर्ज हवे आहे"},
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["step"]


# --- auth -------------------------------------------------------------------


def test_an_expired_token_is_401_so_the_app_can_end_the_session(
    client: TestClient,
) -> None:
    """The app signs out on a 401 rather than retrying a dead token forever."""
    response = client.get("/api/me", headers={"Authorization": "Bearer expired.token.value"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_a_wrong_demo_key_is_401_and_says_nothing_useful(client: TestClient) -> None:
    """§13.2: one message for every authentication failure, so it is no oracle."""
    response = client.get(
        "/api/me", headers={"X-Demo-User": "sunita", "X-Demo-Key": "wrong-key-entirely"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Not authenticated"


# --- the database -----------------------------------------------------------


def test_health_reports_a_database_problem_rather_than_crashing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/health` is what the demo checks first, so it must answer even when the
    database does not."""

    def _fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.api.health.check_db", _fail)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["db"].startswith("error:")
