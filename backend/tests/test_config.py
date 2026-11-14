"""Unit tests: no database, no network."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, to_asyncpg_url

NEON_POOLED = "postgresql://u:s3cret@ep-a-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
NEON_DIRECT = "postgresql://u:s3cret@ep-a.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
NEON_TEST = "postgresql://u:s3cret@ep-b.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"


def make_settings(**overrides: object) -> Settings:
    # _env_file=None: ignore the developer's real .env so tests are deterministic.
    values: dict[str, object] = {
        "app_env": "development",
        "database_url": NEON_POOLED,
        "jwt_secret_key": "k" * 32,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


class TestToAsyncpgUrl:
    def test_converts_neon_url(self) -> None:
        assert to_asyncpg_url(NEON_POOLED) == (
            "postgresql+asyncpg://u:s3cret@ep-a-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
        )

    def test_accepts_postgres_scheme_alias(self) -> None:
        assert to_asyncpg_url("postgres://u:p@h/db").startswith("postgresql+asyncpg://")

    def test_explicit_ssl_wins_over_sslmode(self) -> None:
        assert to_asyncpg_url("postgresql://u:p@h/db?ssl=verify-full&sslmode=require").endswith(
            "?ssl=verify-full"
        )

    def test_rejects_non_postgres_scheme(self) -> None:
        with pytest.raises(ValueError, match="Unsupported database URL scheme"):
            to_asyncpg_url("mysql://u:p@h/db")


class TestDatabaseUrlSelection:
    def test_prefers_unpooled_url(self) -> None:
        settings = make_settings(database_url_unpooled=NEON_DIRECT)
        assert "ep-a.ap-southeast-1" in settings.sqlalchemy_database_url
        assert "-pooler" not in settings.sqlalchemy_database_url

    def test_falls_back_to_pooled_url(self) -> None:
        assert "-pooler" in make_settings().sqlalchemy_database_url

    def test_test_env_uses_test_url(self) -> None:
        settings = make_settings(app_env="test", test_database_url=NEON_TEST)
        assert "ep-b." in settings.sqlalchemy_database_url

    def test_test_env_without_test_url_refuses(self) -> None:
        with pytest.raises(RuntimeError, match="requires TEST_DATABASE_URL"):
            _ = make_settings(app_env="test").sqlalchemy_database_url

    def test_test_env_pointing_at_main_database_refuses(self) -> None:
        settings = make_settings(
            app_env="test", database_url_unpooled=NEON_DIRECT, test_database_url=NEON_DIRECT
        )
        with pytest.raises(RuntimeError, match="different database"):
            _ = settings.sqlalchemy_database_url


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_settings(jwt_secret_key="CHANGE_ME")


def test_secrets_are_hidden_from_repr() -> None:
    settings = make_settings(database_url_unpooled=NEON_DIRECT, test_database_url=NEON_TEST)
    assert "s3cret" not in repr(settings)
    assert "s3cret" not in str(settings.model_dump())
