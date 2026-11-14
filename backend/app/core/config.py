from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


def to_asyncpg_url(url: str) -> str:
    """Normalise a libpq-style Postgres URL (as Neon provides it) for SQLAlchemy + asyncpg.

    - scheme becomes `postgresql+asyncpg`
    - `sslmode=X` becomes `ssl=X` (asyncpg's spelling)
    - `channel_binding` is dropped (asyncpg does not accept it)
    """
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError(f"Unsupported database URL scheme: {parts.scheme!r}")

    query = dict(parse_qsl(parts.query))
    query.pop("channel_binding", None)
    sslmode = query.pop("sslmode", None)
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode

    return urlunsplit(
        ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _database_identity(url: str) -> tuple[str | None, int | None, str]:
    """(host, port, database name): two URLs with the same identity hit the same database."""
    parts = urlsplit(url)
    return parts.hostname, parts.port, parts.path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds Neon vars we don't use
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # SecretStr keeps credentials out of repr(), logs and tracebacks.
    database_url: SecretStr
    # Neon's direct (non-PgBouncer) connection; preferred for asyncpg and migrations.
    database_url_unpooled: SecretStr | None = None
    # Used only when app_env == "test". Must point at a disposable database.
    test_database_url: SecretStr | None = None

    # Signs access tokens (HS256). Anyone holding it can mint a token for any user.
    jwt_secret_key: SecretStr
    access_token_expire_minutes: int = Field(default=30, ge=1, le=24 * 60)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=90)
    # Secure cookies need HTTPS; browsers exempt http://localhost. Set false only for
    # browsers without that exemption (e.g. Safari) in local development.
    cookie_secure: bool = True

    # LLM access. "fake" needs no key and makes no network calls (tests, offline work).
    llm_provider: Literal["openrouter", "fake"] = "openrouter"
    # Any OpenRouter model slug. Changing models is a config change, never a code change.
    llm_model: str = "anthropic/claude-opus-5.5"
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    openrouter_api_key: SecretStr | None = None

    # Where the browser is sent after Google sign-in (the web app's origin, no trailing slash).
    web_app_url: str = "http://localhost:5173"

    # Google sign-in. Without a client id the Google endpoints answer 404.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # Must exactly match an "Authorised redirect URI" on the Google OAuth client.
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Provider endpoints are settings only so tests can point them at a fake provider.
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    google_issuers: list[str] = ["https://accounts.google.com", "accounts.google.com"]

    @field_validator("jwt_secret_key")
    @classmethod
    def _jwt_secret_is_strong(cls, value: SecretStr) -> SecretStr:
        # 32+ characters: short HMAC keys can be brute-forced offline from a single token.
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return value

    @property
    def sqlalchemy_database_url(self) -> str:
        main = to_asyncpg_url((self.database_url_unpooled or self.database_url).get_secret_value())
        if self.app_env != "test":
            return main

        # Never fall back to the real database in tests: tests create and destroy data.
        if self.test_database_url is None:
            raise RuntimeError("APP_ENV=test requires TEST_DATABASE_URL to be set")
        test = to_asyncpg_url(self.test_database_url.get_secret_value())
        if _database_identity(test) == _database_identity(main):
            raise RuntimeError("TEST_DATABASE_URL must point at a different database than DATABASE_URL")
        return test


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env
