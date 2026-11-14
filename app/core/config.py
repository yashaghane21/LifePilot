from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr
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

    @property
    def sqlalchemy_database_url(self) -> str:
        raw = self.database_url_unpooled or self.database_url
        return to_asyncpg_url(raw.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env
