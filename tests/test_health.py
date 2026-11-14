from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI

from app.db.session import get_db_session


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_with_real_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


class _UnreachableSession:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise OSError("connection refused")


async def test_readiness_returns_503_when_database_is_down(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    async def unreachable_db() -> AsyncIterator[_UnreachableSession]:
        yield _UnreachableSession()

    # Swap the real DB dependency for one that fails, without touching the network.
    app.dependency_overrides[get_db_session] = unreachable_db

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
