"""Auth and /api/me behaviour (build plan phase 1 acceptance criteria).

The token verifier is mocked; everything below it - upsert, admin allowlist,
guards, language update - is the real code path.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.firebase import VerifiedToken
from app.config import Settings, get_settings
from app.db.models.user import User
from app.main import create_app
from tests.conftest import make_token

AUTH = {"Authorization": "Bearer good-token"}


def app_with_settings(**overrides: object) -> TestClient:
    """A TestClient whose `get_settings` dependency returns explicit values.

    FastAPI resolves `Depends(get_settings)` through `dependency_overrides`,
    which is the only hook that reaches an already-constructed `Annotated`.
    """
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


# --- 401: no credentials -----------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/me")

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_me_rejects_a_bad_token(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token())

    response = client.get("/api/me", headers={"Authorization": "Bearer not-the-good-one"})

    assert response.status_code == 401


def test_rejection_reason_is_not_leaked_to_the_caller(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    """One generic message for every failure mode - no probing oracle."""
    mock_verifier(make_token())

    expired = client.get("/api/me", headers={"Authorization": "Bearer expired-one"})
    forged = client.get("/api/me", headers={"Authorization": "Bearer forged-one"})

    expired_error = expired.json()["error"]
    forged_error = forged.json()["error"]
    assert expired_error["code"] == forged_error["code"] == "unauthorized"
    assert expired_error["message"] == forged_error["message"] == "Not authenticated"


# --- 200: a valid token ------------------------------------------------------


def test_me_returns_the_profile_and_creates_the_user(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None], db: Session
) -> None:
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    body = client.get("/api/me", headers=AUTH).json()

    assert body["email"] == "alice@example.com"
    assert body["displayName"] == "Alice A."
    assert body["photoUrl"] == "https://example.invalid/a.jpg"
    assert body["preferredLanguage"] == "mr-IN"
    assert body["isAdmin"] is False
    assert body["persona"]["id"] == "sunita"
    assert body["session"] == "firebase"

    stored = db.scalar(select(User).where(User.firebase_uid == "test:alice"))
    assert stored is not None


def test_repeat_logins_do_not_create_duplicate_users(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None], db: Session
) -> None:
    mock_verifier(make_token(uid="test:alice"))

    first = client.get("/api/me", headers=AUTH).json()
    second = client.get("/api/me", headers=AUTH).json()

    assert first["uid"] == second["uid"]
    rows = db.scalars(select(User).where(User.firebase_uid == "test:alice")).all()
    assert len(rows) == 1


def test_profile_changes_are_picked_up_on_the_next_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new Google photo or name should replace the stored one."""
    from app import deps
    from app.auth.firebase import TokenError

    state = {"token": make_token(uid="test:alice", name="Alice A.")}

    def _fake(raw: str, settings: Settings) -> VerifiedToken:
        if raw == "good-token":
            return state["token"]
        raise TokenError("invalid")

    monkeypatch.setattr(deps, "verify_id_token", _fake)

    assert client.get("/api/me", headers=AUTH).json()["displayName"] == "Alice A."

    state["token"] = make_token(uid="test:alice", name="Alice B.", picture=None)
    body = client.get("/api/me", headers=AUTH).json()

    assert body["displayName"] == "Alice B."
    assert body["photoUrl"] is None


# --- admin allowlist ---------------------------------------------------------


def test_admin_flag_comes_from_the_allowlist(
    monkeypatch: pytest.MonkeyPatch, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token(uid="test:boss", email="BOSS@Example.com"))

    with app_with_settings(dashboard_admin_emails="boss@example.com") as c:
        # Matching is case-insensitive, so BOSS@Example.com counts.
        assert c.get("/api/me", headers=AUTH).json()["isAdmin"] is True


def test_non_allowlisted_user_is_not_admin(
    monkeypatch: pytest.MonkeyPatch, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with app_with_settings(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/me", headers=AUTH).json()["isAdmin"] is False


def test_admin_rights_are_revoked_when_the_allowlist_changes(
    monkeypatch: pytest.MonkeyPatch, mock_verifier: Callable[[VerifiedToken], None], db: Session
) -> None:
    """is_admin is recomputed every request, so removal takes effect at once."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with app_with_settings(dashboard_admin_emails="alice@example.com") as c:
        assert c.get("/api/me", headers=AUTH).json()["isAdmin"] is True

    with app_with_settings(dashboard_admin_emails="") as c:
        assert c.get("/api/me", headers=AUTH).json()["isAdmin"] is False


def test_a_client_cannot_make_itself_admin(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    response = client.patch("/api/me", headers=AUTH, json={"isAdmin": True})

    # `extra="forbid"` (build plan 13.5): an unknown field is a loud 422 rather
    # than a silent no-op, which otherwise looks to the caller like it worked.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    assert client.get("/api/me", headers=AUTH).json()["isAdmin"] is False


# --- PATCH /me ---------------------------------------------------------------


def test_preferred_language_can_be_updated(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token(uid="test:alice"))
    client.get("/api/me", headers=AUTH)

    body = client.patch("/api/me", headers=AUTH, json={"preferredLanguage": "hi-IN"}).json()

    assert body["preferredLanguage"] == "hi-IN"
    assert client.get("/api/me", headers=AUTH).json()["preferredLanguage"] == "hi-IN"


def test_an_unsupported_language_is_refused(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    mock_verifier(make_token(uid="test:alice"))

    response = client.patch("/api/me", headers=AUTH, json={"preferredLanguage": "fr-FR"})

    assert response.status_code == 422


def test_login_does_not_reset_a_chosen_language(
    client: TestClient, mock_verifier: Callable[[VerifiedToken], None]
) -> None:
    """The user owns their language; an upsert must not overwrite it."""
    mock_verifier(make_token(uid="test:alice"))
    client.patch("/api/me", headers=AUTH, json={"preferredLanguage": "en-IN"})

    assert client.get("/api/me", headers=AUTH).json()["preferredLanguage"] == "en-IN"
