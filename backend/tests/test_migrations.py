import asyncio

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from tests.conftest import alembic_config


async def _db_state() -> tuple[str | None, str | None]:
    """(alembic version, installed pgvector version) read on a fresh connection."""
    engine = create_async_engine(get_settings().sqlalchemy_database_url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
        vector = (
            await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        ).scalar_one_or_none()
    await engine.dispose()
    return version, vector


def test_database_is_at_head_with_pgvector() -> None:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()

    version, vector = asyncio.run(_db_state())

    assert version == head
    assert vector is not None


def test_single_migration_head() -> None:
    # Two heads means two migrations claim the same parent: a merge is needed.
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


async def _execute(*statements: str) -> None:
    engine = create_async_engine(get_settings().sqlalchemy_database_url, poolclass=pool.NullPool)
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    await engine.dispose()


def _empty_all_tables() -> None:
    # Schema round trips must not depend on rows other tests left behind.
    asyncio.run(_execute("TRUNCATE users RESTART IDENTITY CASCADE"))


def test_downgrade_to_base_and_upgrade_again() -> None:
    config = alembic_config()
    _empty_all_tables()

    command.downgrade(config, "base")
    assert asyncio.run(_db_state()) == (None, None)

    command.upgrade(config, "head")
    version, vector = asyncio.run(_db_state())
    assert version is not None
    assert vector is not None


def test_downgrade_refuses_while_google_only_users_exist() -> None:
    config = alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    _empty_all_tables()
    asyncio.run(
        _execute(
            "INSERT INTO users (id, email, full_name, password_hash) "
            "VALUES (gen_random_uuid(), 'google-only@example.com', 'Google Only', NULL)"
        )
    )

    with pytest.raises(Exception, match="Cannot downgrade: users without a password exist"):
        command.downgrade(config, "24a123ab9662")

    # Nothing was changed: the schema is still at head and the user still exists.
    assert asyncio.run(_db_state())[0] == head
    _empty_all_tables()
