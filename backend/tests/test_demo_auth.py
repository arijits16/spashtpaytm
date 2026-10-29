"""`X-Demo-User` behaviour (build plan phase 1, step 4).

The demo header is what keeps the pitch alive when venue Wi-Fi dies, so the
rules around it are tested as carefully as real auth: it works in dev when
enabled, and is refused everywhere else.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.demo import DEFAULT_DEMO_PERSONA, demo_token
from app.config import Settings, get_settings
from app.db.models.user import User
from app.main import create_app
from tests.conftest import make_token

DEMO = {"X-Demo-User": "sunita"}


def app_with_settings(**overrides: object) -> TestClient:
    """TestClient whose `get_settings` returns explicit values."""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


# --- enabled in dev ----------------------------------------------------------


def test_demo_header_signs_in_when_enabled_in_dev(db: Session) -> None:
    with app_with_settings(demo_auth=True, app_env="dev") as c:
        body = c.get("/api/me", headers=DEMO).json()

    assert body["displayName"] == "Sunita J."
    assert body["preferredLanguage"] == "mr-IN"
    assert db.scalar(select(User).where(User.firebase_uid == "demo:sunita")) is not None


def test_demo_login_needs_no_network() -> None:
    """Nothing in the demo path may call out to Firebase or Google."""
    import app.deps as deps_module

    def _explode(raw: str, settings: Settings) -> object:
        raise AssertionError("the verifier must not be called for demo auth")

    original = deps_module.verify_id_token
    deps_module.verify_id_token = _explode  # type: ignore[assignment]
    try:
        with app_with_settings(demo_auth=True, app_env="dev") as c:
            assert c.get("/api/me", headers=DEMO).status_code == 200
    finally:
        deps_module.verify_id_token = original  # type: ignore[assignment]


def test_each_demo_persona_gets_its_own_user() -> None:
    with app_with_settings(demo_auth=True, app_env="dev") as c:
        sunita = c.get("/api/me", headers={"X-Demo-User": "sunita"}).json()
        ramesh = c.get("/api/me", headers={"X-Demo-User": "ramesh"}).json()

    assert sunita["id"] != ramesh["id"]
    assert ramesh["displayName"] == "Ramesh Y."


def test_an_unknown_persona_falls_back_to_the_default() -> None:
    with app_with_settings(demo_auth=True, app_env="dev") as c:
        body = c.get("/api/me", headers={"X-Demo-User": "nobody"}).json()

    assert body["displayName"] == "Sunita J."


# --- refused everywhere else -------------------------------------------------


def test_demo_header_is_refused_when_disabled() -> None:
    with app_with_settings(demo_auth=False, app_env="dev") as c:
        response = c.get("/api/me", headers=DEMO)

    assert response.status_code == 401
    assert response.json()["detail"] == "Demo auth is disabled"


def test_demo_header_is_refused_in_production() -> None:
    """Even with DEMO_AUTH=true, prod must never honour the header."""
    with app_with_settings(demo_auth=True, app_env="prod") as c:
        assert c.get("/api/me", headers=DEMO).status_code == 401


def test_a_real_token_wins_over_the_demo_header(
    mock_verifier: Callable[..., None],
) -> None:
    """A signed-in user sending a stale demo header stays themselves."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with app_with_settings(demo_auth=True, app_env="dev") as c:
        body = c.get(
            "/api/me",
            headers={"Authorization": "Bearer good-token", **DEMO},
        ).json()

    assert body["email"] == "alice@example.com"


# --- uid namespacing ---------------------------------------------------------


def test_demo_uids_are_namespaced_away_from_real_firebase_uids() -> None:
    """The `demo:` prefix means a demo user can never collide with a real account."""
    assert demo_token(DEFAULT_DEMO_PERSONA).uid == "demo:sunita"
    assert demo_token("  SUNITA  ").uid == "demo:sunita"
