"""Environment configuration. Secrets stay on the server."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Stoxs8"
    secret_key: str = "dev-only-change-me"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'bazaar.db').as_posix()}"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    access_token_minutes: int = 720
    scheduler_enabled: bool = True
    scan_interval_minutes: int = 15
    data_mode: str = "live"
    admin_email: str | None = None
    admin_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Live broker execution stays off until a separate reviewed module exists.
    live_trading_enabled: bool = False
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/api/v1/upstox/callback"
    upstox_pin: str = ""
    upstox_totp_secret: str = ""
    # None follows the environment: closed in production, open in development.
    registration_enabled: bool | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def demo_mode(self) -> bool:
        return self.data_mode.lower() == "demo"

    @property
    def allow_registration(self) -> bool:
        if self.registration_enabled is not None:
            return self.registration_enabled
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.secret_key == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY must be set to a unique value in production")
    if settings.live_trading_enabled:
        raise RuntimeError(
            "LIVE_TRADING_ENABLED cannot be turned on in this release. "
            "Broker execution needs a separate implementation and review."
        )
    return settings
