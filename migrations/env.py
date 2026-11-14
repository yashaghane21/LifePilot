import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    # Without disable_existing_loggers=False, running migrations in-process (e.g. from
    # tests) would silently disable every logger the app had already created.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# The URL comes from app settings (.env), never from alembic.ini, so there is one
# source of truth and no credentials in a committed file. It is deliberately not
# passed through config.set_main_option(): ConfigParser treats '%' in a password
# as interpolation syntax and fails.
DATABASE_URL = get_settings().sqlalchemy_database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # NullPool: a migration is a one-off process; no point keeping connections around.
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
