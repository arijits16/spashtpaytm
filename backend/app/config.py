"""Application settings, loaded from the environment (see backend/.env.example).

Every value has a safe local default so the app boots with no .env at all. Secrets
default to empty and the code degrades (DEMO_MODE, no Sarvam, no Firebase) rather
than crashing - the demo must never die because a key is missing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

AppEnv = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    """Typed view of the backend environment."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_env: AppEnv = "dev"
    app_version: str = "0.1.0"

    # --- database ---
    database_url: str = "postgresql+psycopg://spasht:spasht@localhost:5433/spasht"

    # --- web ---
    cors_origins: str = "http://localhost:5173"

    # --- Sarvam AI (phases 6, 7, 10) ---
    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_fallback_model: str = "bulbul:v3"
    sarvam_llm_live_model: str = "sarvam-105b-conversations"
    sarvam_llm_offline_model: str = "sarvam-105b"

    # --- Firebase auth (phase 1) ---
    firebase_project_id: str = ""
    google_application_credentials: str = ""
    dashboard_admin_emails: str = ""

    # --- trust layer (phase 5) ---
    signing_key_path: str = "./secrets/ed25519_private.key"
    signing_key_id: str = "spasht-07"
    transcript_key: str = ""
    customer_ref_pepper: str = ""
    tts_cache_secret: str = ""

    # --- demo switches ---
    demo_mode: bool = False
    demo_auth: bool = False
    otp_demo: bool = True

    # --- rescue agent (phase 9) ---
    rescue_idle_seconds: int = 60
    contact_window: str = "09:00-18:00"

    @field_validator("database_url")
    @classmethod
    def _require_psycopg_driver(cls, value: str) -> str:
        """Normalise a bare `postgresql://` URL, which would otherwise pick psycopg2."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    # --- derived helpers ---

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.dashboard_admin_emails.split(",") if e.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def sarvam_configured(self) -> bool:
        """True when live Sarvam calls are possible. DEMO_MODE always wins."""
        return bool(self.sarvam_api_key) and not self.demo_mode

    @property
    def signing_key_file(self) -> Path:
        path = Path(self.signing_key_path)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def demo_auth_allowed(self) -> bool:
        """`X-Demo-User` is only honoured in dev, and only when explicitly enabled."""
        return self.demo_auth and self.is_dev


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Call `get_settings.cache_clear()` in tests."""
    return Settings()


settings: Settings = get_settings()
