"""The admin guard (`current_admin`).

The dashboard API itself lands in phase 8, so these tests mount the real
dependency on a throwaway route rather than inventing production surface. The
guard is what stands between a signed-in customer and the compliance dashboard,
so it is tested now, not when the dashboard arrives.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import CurrentAdmin, CurrentUser
from app.main import create_app
from app.security.demo_auth import DEMO_ADMIN
from tests.conftest import make_token

AUTH = {"Authorization": "Bearer good-token"}
DEMO_KEY = "test-demo-key-0123456789abcdef"


def guarded_app(**overrides: object) -> TestClient:
    """An app exposing one admin-only route and one merely-authenticated route."""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    app: FastAPI = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/api/_test/admin-only")
    def admin_only(_: CurrentAdmin) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/_test/any-user")
    def any_user(_: CurrentUser) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_admin_route_allows_an_allowlisted_user(
    mock_verifier: Callable[..., None],
) -> None:
    mock_verifier(make_token(uid="test:boss", email="boss@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/admin-only", headers=AUTH).status_code == 200


def test_admin_route_returns_403_for_a_signed_in_non_admin(
    mock_verifier: Callable[..., None],
) -> None:
    """403, not 401: they are authenticated, just not permitted."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        response = c.get("/api/_test/admin-only", headers=AUTH)

    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "forbidden"
    assert body["message"] == "Admin access required"


def test_admin_route_returns_401_with_no_credentials() -> None:
    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/admin-only").status_code == 401


def test_a_non_admin_still_reaches_ordinary_protected_routes(
    mock_verifier: Callable[..., None],
) -> None:
    """The guard must gate the dashboard, not the customer's own journey."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/any-user", headers=AUTH).status_code == 200


def test_the_demo_customer_is_never_an_admin() -> None:
    """Demo auth is a convenience for the customer flow, not a way into the dashboard."""
    demo = {"X-Demo-User": "sunita", "X-Demo-Key": DEMO_KEY}

    with guarded_app(
        demo_auth=True,
        app_env="dev",
        demo_auth_key=DEMO_KEY,
        dashboard_admin_emails="boss@example.com",
    ) as c:
        assert c.get("/api/_test/any-user", headers=demo).status_code == 200
        assert c.get("/api/_test/admin-only", headers=demo).status_code == 403


def test_the_demo_admin_reaches_the_dashboard_when_allowlisted() -> None:
    """`demo-admin` is the dev way onto the dashboard with no network (13.2)."""
    demo = {"X-Demo-User": DEMO_ADMIN, "X-Demo-Key": DEMO_KEY}

    with guarded_app(
        demo_auth=True,
        app_env="dev",
        demo_auth_key=DEMO_KEY,
        dashboard_admin_emails="demo-admin@spasht.invalid",
    ) as c:
        assert c.get("/api/_test/admin-only", headers=demo).status_code == 200


def test_the_demo_admin_is_refused_when_not_allowlisted() -> None:
    """The identity alone is not enough; the allowlist still governs."""
    demo = {"X-Demo-User": DEMO_ADMIN, "X-Demo-Key": DEMO_KEY}

    with guarded_app(
        demo_auth=True, app_env="dev", demo_auth_key=DEMO_KEY, dashboard_admin_emails=""
    ) as c:
        assert c.get("/api/_test/admin-only", headers=demo).status_code == 403


# --- the email must be verified (build plan 13.2) ----------------------------


def test_an_unverified_allowlisted_email_is_not_an_admin(
    mock_verifier: Callable[..., None],
) -> None:
    """Anyone can put an address in a profile; only Google can verify it.

    Without this check the allowlist would admit whoever *claimed* one of its
    addresses, which is no barrier at all.
    """
    mock_verifier(make_token(uid="test:boss", email="boss@example.com", email_verified=False))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        response = c.get("/api/_test/admin-only", headers=AUTH)
        assert response.status_code == 403
        # Still a perfectly good ordinary user.
        assert c.get("/api/_test/any-user", headers=AUTH).status_code == 200


def test_a_verified_allowlisted_email_is_an_admin(
    mock_verifier: Callable[..., None],
) -> None:
    mock_verifier(make_token(uid="test:boss", email="boss@example.com", email_verified=True))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/admin-only", headers=AUTH).status_code == 200


def test_verifying_the_email_later_grants_access_on_the_next_request(
    mock_verifier: Callable[..., None],
) -> None:
    """`is_admin` is recomputed every request (D-014), so no re-login is needed."""
    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        mock_verifier(make_token(uid="test:boss", email="boss@example.com", email_verified=False))
        assert c.get("/api/_test/admin-only", headers=AUTH).status_code == 403

        mock_verifier(make_token(uid="test:boss", email="boss@example.com", email_verified=True))
        assert c.get("/api/_test/admin-only", headers=AUTH).status_code == 200
