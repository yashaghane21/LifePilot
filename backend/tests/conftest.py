import os

# Must be set before anything imports app settings: selects TEST_DATABASE_URL.
os.environ["APP_ENV"] = "test"
# Fixed test-only values, so tests never depend on (or use) the developer's real credentials.
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-" + "x" * 32
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-only-google-secret"
# Tests never call a real LLM: no cost, no network, deterministic.
os.environ["LLM_PROVIDER"] = "fake"
os.environ.pop("OPENROUTER_API_KEY", None)

import asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy import pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db import models  # noqa: E402, F401  (registers all tables on Base.metadata)
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


async def _reset_schema() -> None:
    settings = get_settings()
    # Defence in depth: config.py already refuses a non-test URL in test mode.
    assert settings.app_env == "test", "refusing to wipe a non-test database"

    reset_engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=pool.NullPool)
    async with reset_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await reset_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Rebuild the test database from an empty schema using migrations, once per run."""
    asyncio.run(_reset_schema())
    command.upgrade(alembic_config(), "head")


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    yield
    await engine.dispose()


@pytest.fixture
async def clean_db() -> None:
    """Empty every application table before a test that writes data.

    Runs before (not after) the test, so a failing test leaves its data behind to inspect.
    """
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app() -> FastAPI:
    """A fresh app per test, so tests can add routes or dependency overrides safely."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    # https: the refresh cookie is Secure, and a cookie jar never sends Secure cookies over http.
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client
