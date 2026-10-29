"""Settings behaviour that other phases depend on."""

from __future__ import annotations

from app.config import Settings


def _settings(**overrides: object) -> Settings:
    """Build settings from explicit values, ignoring any local .env."""
    base: dict[str, object] = {"_env_file": None}
    return Settings(**(base | overrides))  # type: ignore[arg-type]


def test_bare_postgres_url_is_upgraded_to_psycopg() -> None:
    s = _settings(database_url="postgresql://u:p@localhost:5432/db")

    assert s.database_url.startswith("postgresql+psycopg://")


def test_demo_mode_overrides_a_present_sarvam_key() -> None:
    """DEMO_MODE must win, so the demo is never at the mercy of venue Wi-Fi."""
    assert _settings(sarvam_api_key="k", demo_mode=False).sarvam_configured is True
    assert _settings(sarvam_api_key="k", demo_mode=True).sarvam_configured is False
    assert _settings(sarvam_api_key="", demo_mode=False).sarvam_configured is False


def test_demo_auth_header_is_refused_outside_dev() -> None:
    """`X-Demo-User` is a dev-only bypass; prod must never honour it."""
    assert _settings(demo_auth=True, app_env="dev").demo_auth_allowed is True
    assert _settings(demo_auth=True, app_env="prod").demo_auth_allowed is False
    assert _settings(demo_auth=False, app_env="dev").demo_auth_allowed is False


def test_comma_separated_lists_are_parsed_and_normalised() -> None:
    s = _settings(
        cors_origins="http://localhost:5173, https://demo.example ",
        dashboard_admin_emails="A@Example.com ,b@example.com",
    )

    assert s.cors_origin_list == ["http://localhost:5173", "https://demo.example"]
    assert s.admin_email_list == ["a@example.com", "b@example.com"]


def test_signing_key_path_resolves_against_the_backend_dir() -> None:
    s = _settings(signing_key_path="./secrets/ed25519_private.key")

    assert s.signing_key_file.is_absolute()
    assert s.signing_key_file.parts[-2:] == ("secrets", "ed25519_private.key")
