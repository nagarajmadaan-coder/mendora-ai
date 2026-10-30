"""
App settings, read from environment variables (or a `backend/.env` file).

Most variable names start with MENDORA_ (e.g. MENDORA_DATABASE_URL).
AI keys also accept the provider's usual name (ANTHROPIC_API_KEY, OPENAI_API_KEY).
See `.env.example` for the full list. Never commit a real `.env` file.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "mendora.db"

log = logging.getLogger("mendora.config")

# Default model per provider. OpenAI has no default here: set MENDORA_AI_MODEL explicitly.
# Nebius: a model from the Nebius docs' JSON-mode examples. Any Token Factory model with the "JSON mode" tag works.
DEFAULT_AI_MODELS: dict[str, str] = {"anthropic": "claude-sonnet-5-5", "nebius": "openai/gpt-oss-120b", "tavily": "tavily-search"}

# Values from .env.example that must never be used as real secrets.
_PLACEHOLDER_MARKERS = ("replace-with", "your-", "changeme", "change-me", "placeholder")


def is_placeholder(value: str | None) -> bool:
    return not value or not value.strip() or any(m in value.strip().lower() for m in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="MENDORA_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "MENDORA API"
    app_version: str = "0.5.0"
    environment: Literal["development", "test", "production"] = "development"

    # ---------- CORS ----------
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    # ---------- Database ----------
    # SQLite file next to the backend code by default. Any SQLAlchemy URL works.
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

    # ---------- Authentication ----------
    # Secret used to sign login tokens (JWT). REQUIRED in production.
    # Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(64))"
    jwt_secret: SecretStr | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_minutes: int = Field(default=60, ge=5, le=60 * 24 * 7)
    login_max_failures: int = Field(default=5, ge=1)  # per email, per window
    login_window_minutes: int = Field(default=15, ge=1)

    # ---------- AI diagnosis ----------
    # "anthropic" (default), "openai" (or any OpenAI-compatible API via MENDORA_AI_BASE_URL),
    # "nebius" (Nebius Token Factory), "tavily" (TRIAL only: a web-search summary, uses TAVILY_API_KEY),
    # or "none" to switch AI off.
    ai_provider: Literal["anthropic", "openai", "nebius", "tavily", "none"] = "anthropic"
    ai_model: str | None = None  # None = provider default (see DEFAULT_AI_MODELS)
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MENDORA_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MENDORA_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    nebius_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MENDORA_NEBIUS_API_KEY", "NEBIUS_API_KEY")
    )
    # AI web research (Tavily search + AI summary). Separate from the AI diagnosis; off when no key is set.
    tavily_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MENDORA_TAVILY_API_KEY", "TAVILY_API_KEY")
    )
    # Optional: point a provider at a different (compatible) API address.
    ai_base_url: str | None = None
    ai_timeout_seconds: float = Field(default=45, gt=0, le=300)
    ai_max_output_tokens: int = Field(default=1500, ge=256, le=8000)
    diagnoses_per_user_per_hour: int = Field(default=20, ge=1)

    # ---------- Technicians & bookings (Steps 8–9) ----------
    # Local time zone used for working hours and booking slots (times are stored in UTC).
    timezone: str = "Asia/Kolkata"
    currency: str = Field(default="INR", min_length=3, max_length=3)
    # Demo mode shows clearly-labelled SAMPLE technicians (created with `python -m app.cli seed-demo`).
    # None = on in development/test, off in production.
    demo_mode: bool | None = None
    working_hours_start: int = Field(default=9, ge=0, le=23)  # local hour, inclusive
    working_hours_end: int = Field(default=18, ge=1, le=24)  # local hour, exclusive
    booking_max_days_ahead: int = Field(default=60, ge=1, le=365)
    booking_min_notice_minutes: int = Field(default=60, ge=0)
    bookings_per_user_per_hour: int = Field(default=20, ge=1)

    # ---------- Payments (Step 10) ----------
    # Only "sandbox" exists: a SIMULATED provider — no real money, no card details. "none" turns payments off.
    payment_provider: Literal["sandbox", "none"] = "sandbox"
    payments_per_user_per_hour: int = Field(default=30, ge=1)
    # Photo attachments (merged feature). Stored on disk, never sent to the AI.
    upload_dir: Path = BACKEND_DIR / "uploads"
    photo_max_mb: int = Field(default=10, ge=1, le=25)
    photos_per_request: int = Field(default=3, ge=1, le=10)

    # Platform fee shown in the price breakdown (sandbox — nothing is actually collected). Charged on visit + labour.
    platform_commission_percent: float = Field(default=10.0, ge=0, le=50)

    # Interactive API docs at /docs. None = on in development/test, off in production (set true to allow admins to use them).
    api_docs: bool | None = None

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.environment == "production" and (
            self.usable_jwt_secret is None or len(self.usable_jwt_secret) < 32
        ):
            raise ValueError("MENDORA_JWT_SECRET must be set (32+ characters) when MENDORA_ENVIRONMENT=production.")
        if self.working_hours_end <= self.working_hours_start:
            raise ValueError("MENDORA_WORKING_HOURS_END must be later than MENDORA_WORKING_HOURS_START.")
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(self.timezone)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Unknown MENDORA_TIMEZONE '{self.timezone}'.") from exc
        return self

    @property
    def api_docs_enabled(self) -> bool:
        return self.api_docs if self.api_docs is not None else self.environment != "production"

    @property
    def demo_mode_enabled(self) -> bool:
        return self.demo_mode if self.demo_mode is not None else self.environment != "production"

    @property
    def usable_jwt_secret(self) -> str | None:
        """The JWT secret, or None if it's missing or still the .env.example placeholder."""
        value = self.jwt_secret.get_secret_value() if self.jwt_secret else None
        return None if is_placeholder(value) else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_ai_model(self) -> str | None:
        if self.ai_provider == "none":
            return None
        return self.ai_model or DEFAULT_AI_MODELS.get(self.ai_provider)

    @property
    def tavily_key(self) -> str | None:
        value = self.tavily_api_key.get_secret_value().strip() if self.tavily_api_key else ""
        return None if is_placeholder(value) else value

    @property
    def ai_api_key(self) -> str | None:
        if self.ai_provider == "tavily":
            return self.tavily_key
        key = {"anthropic": self.anthropic_api_key, "openai": self.openai_api_key, "nebius": self.nebius_api_key}.get(self.ai_provider)
        value = key.get_secret_value().strip() if key else ""
        return None if is_placeholder(value) else value


def env_file_path() -> Path:
    """
    Which settings file to read. Default: backend/.env.
    Set MENDORA_ENV_FILE to use another one (e.g. a test copy):  MENDORA_ENV_FILE=.env.tavily-test
    A relative name is looked up in the backend folder.
    """
    chosen = os.environ.get("MENDORA_ENV_FILE", "").strip()
    if not chosen:
        return BACKEND_DIR / ".env"
    path = Path(chosen)
    return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    path = env_file_path()
    if os.environ.get("MENDORA_ENV_FILE") and not path.is_file():
        raise RuntimeError(f"MENDORA_ENV_FILE points to '{path}', which doesn't exist.")
    return Settings(_env_file=path)
