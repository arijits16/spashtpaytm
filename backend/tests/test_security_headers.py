"""Security headers, request IDs and the standard error envelope (section 13.10).

These are middleware-level guarantees, so they are asserted on a real route
(`/api/health`) and on paths that never reach a route at all - an unknown URL and
a validation failure. If a header can be lost on an error path, a test here
fails rather than a judge's browser.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.auth.firebase import VerifiedToken
from app.security.headers import API_CSP, BASE_HEADERS, PUBLIC_PAGE_CSP, csp_for_path
from app.security.request_id import REQUEST_ID_HEADER
from tests.conftest import make_token


def test_health_carries_every_security_header(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    for name, value in BASE_HEADERS.items():
        assert response.headers[name] == value
    assert response.headers["Content-Security-Policy"] == API_CSP


def test_health_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id
    assert request_id != "-"


def test_two_requests_get_different_request_ids(client: TestClient) -> None:
    first = client.get("/api/health").headers[REQUEST_ID_HEADER]
    second = client.get("/api/health").headers[REQUEST_ID_HEADER]

    assert first != second


def test_inbound_request_id_is_reused(client: TestClient) -> None:
    """Honouring the caller's id lets a single id span the app and the backend."""
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: "ios-abc123"})

    assert response.headers[REQUEST_ID_HEADER] == "ios-abc123"


def test_unsafe_inbound_request_id_is_replaced(client: TestClient) -> None:
    """A header that ends up in logs must not carry attacker-chosen content."""
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: "a" * 200})

    assert response.headers[REQUEST_ID_HEADER] != "a" * 200
    assert len(response.headers[REQUEST_ID_HEADER]) <= 64


def test_server_banner_is_not_advertised(client: TestClient) -> None:
    assert "server" not in {name.lower() for name in client.get("/api/health").headers}


def test_unknown_route_uses_the_standard_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    # The id in the body and the header must match, or it cannot be used to
    # correlate a report from the app with a log line.
    assert body["error"]["requestId"] == response.headers[REQUEST_ID_HEADER]


def test_error_responses_also_carry_security_headers(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    for name, value in BASE_HEADERS.items():
        assert response.headers[name] == value


def test_validation_error_uses_the_standard_envelope(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    """PATCH /me with a bad language: a 422 must look like every other error.

    Signed in first, because dependencies resolve before the body is validated -
    an unauthenticated call would 401 and never reach the validator.
    """
    mock_verifier(make_token())

    response = client.patch(
        "/api/me",
        json={"preferredLanguage": "fr-FR"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "preferredLanguage" in body["error"]["message"]
    assert body["error"]["requestId"] == response.headers[REQUEST_ID_HEADER]


def test_validation_error_does_not_echo_the_rejected_value(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    """A rejected field may be a transcript; it must not be reflected back."""
    mock_verifier(make_token())

    response = client.patch(
        "/api/me",
        json={"preferredLanguage": "secret-value-xyz"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 422
    assert "secret-value-xyz" not in response.text


def test_public_receipt_path_gets_the_strict_csp() -> None:
    """Phase 6 serves HTML at /r/<no>; its policy is decided here, not there."""
    assert csp_for_path("/r/SP-7F3A9C2K") == PUBLIC_PAGE_CSP
    assert csp_for_path("/api/health") == API_CSP


def test_cors_preflight_is_allowed_for_the_website(client: TestClient) -> None:
    response = client.options(
        "/api/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_an_unlisted_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
