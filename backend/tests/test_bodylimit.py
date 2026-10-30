"""Request body size limits (build plan section 13.5).

Two things matter: an oversized JSON body is refused with the standard envelope,
and an audio path gets the larger 2 MB allowance - because getting that mapping
backwards would either reject every voice turn or let any route accept 2 MB.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.security.bodylimit import AUDIO_BODY_LIMIT, JSON_BODY_LIMIT, limit_for_path


def test_json_routes_get_the_small_limit() -> None:
    assert limit_for_path("/api/me") == JSON_BODY_LIMIT
    assert limit_for_path("/api/journeys") == JSON_BODY_LIMIT


def test_voice_upload_gets_the_audio_limit() -> None:
    """Section 10.1: a 25 s m4a clip is far larger than the JSON limit."""
    assert limit_for_path("/api/journeys/abc-123/voice") == AUDIO_BODY_LIMIT


def test_oversized_json_is_rejected_with_the_standard_envelope(client: TestClient) -> None:
    """Refused on Content-Length, so the body is never buffered."""
    response = client.patch(
        "/api/me",
        content=b"x" * (JSON_BODY_LIMIT + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_a_body_inside_the_limit_still_reaches_the_route(client: TestClient) -> None:
    """The limiter must not interfere with an ordinary request.

    No credentials, so the expected answer is 401 from the auth dependency -
    which proves the request got past the body check to the route.
    """
    response = client.patch("/api/me", json={"preferredLanguage": "mr-IN"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_get_requests_are_not_inspected(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
