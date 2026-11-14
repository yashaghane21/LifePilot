from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().sqlalchemy_database_url,
    # Neon suspends idle compute and drops connections; check before reuse.
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"timeout": 10},  # seconds; covers Neon cold starts
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    async with SessionLocal() as session:
        yield session


# Use in endpoint signatures: `db: DbSession`.
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
