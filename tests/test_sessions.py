"""Refresh-token sessions: cookie attributes, rotation, reuse detection, logout, races."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.security import hash_refresh_token
from app.db.session import SessionLocal
from app.modules.auth.models import RefreshSession
from app.modules.auth.sessions import REFRESH_COOKIE
from tests.test_auth import PASSWORD, bearer, register

pytestmark = pytest.mark.usefixtures("clean_db")


async def login_and_get_refresh_token(client: httpx.AsyncClient) -> str:
    await register(client)
    response = await client.post("/api/v1/auth/login", json={"email": "yash@example.com", "password": PASSWORD})
    assert response.status_code == 200
    return response.cookies[REFRESH_COOKIE]


async def refresh_with(client: httpx.AsyncClient, token: str) -> httpx.Response:
    """Send exactly this refresh token, ignoring whatever the client's cookie jar holds."""
    client.cookies.clear()
    return await client.post("/api/v1/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE}={token}"})


class TestLoginCookie:
    async def test_login_sets_a_locked_down_refresh_cookie(self, client: httpx.AsyncClient) -> None:
        await register(client)

        response = await client.post("/api/v1/auth/login", json={"email": "yash@example.com", "password": PASSWORD})

        set_cookie = response.headers["set-cookie"].lower()
        assert set_cookie.startswith(f"{REFRESH_COOKIE}=")
        for attribute in ("httponly", "secure", "samesite=strict", "path=/api/v1/auth", "max-age=2592000"):
            assert attribute in set_cookie

    async def test_only_the_hash_is_stored(self, client: httpx.AsyncClient) -> None:
        token = await login_and_get_refresh_token(client)

        async with SessionLocal() as db:
            stored = await db.scalar(select(RefreshSession))

        assert stored is not None
        assert stored.token_hash == hash_refresh_token(token)
        assert token not in stored.token_hash


class TestRefresh:
    async def test_returns_new_access_token_and_rotates_cookie(self, client: httpx.AsyncClient) -> None:
        old = await login_and_get_refresh_token(client)

        response = await refresh_with(client, old)

        assert response.status_code == 200
        new = response.cookies[REFRESH_COOKIE]
        assert new != old
        me = await client.get("/api/v1/users/me", headers=bearer(response.json()["access_token"]))
        assert me.json()["email"] == "yash@example.com"

    async def test_new_token_keeps_working_across_rotations(self, client: httpx.AsyncClient) -> None:
        token = await login_and_get_refresh_token(client)

        for _ in range(3):
            response = await refresh_with(client, token)
            assert response.status_code == 200
            token = response.cookies[REFRESH_COOKIE]

    async def test_missing_cookie_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_refresh_token"

    async def test_unknown_token_is_401(self, client: httpx.AsyncClient) -> None:
        assert (await refresh_with(client, "made-up-token")).status_code == 401

    async def test_expired_token_is_401(self, client: httpx.AsyncClient) -> None:
        token = await login_and_get_refresh_token(client)
        async with SessionLocal() as db:
            await db.execute(update(RefreshSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
            await db.commit()

        assert (await refresh_with(client, token)).status_code == 401


class TestReuseDetection:
    async def test_replaying_a_used_token_revokes_the_whole_family(self, client: httpx.AsyncClient) -> None:
        stolen = await login_and_get_refresh_token(client)
        # The legitimate user refreshes first, so `stolen` is now used up...
        current = (await refresh_with(client, stolen)).cookies[REFRESH_COOKIE]

        # ...then the thief replays it.
        replay = await refresh_with(client, stolen)

        assert replay.status_code == 401
        # The legitimate user's newer token dies too: we can't tell who the thief is.
        assert (await refresh_with(client, current)).status_code == 401

    async def test_concurrent_refreshes_with_one_token_let_exactly_one_through(
        self, client: httpx.AsyncClient
    ) -> None:
        token = await login_and_get_refresh_token(client)
        client.cookies.clear()
        cookie = {"Cookie": f"{REFRESH_COOKIE}={token}"}

        responses = await asyncio.gather(
            client.post("/api/v1/auth/refresh", headers=cookie),
            client.post("/api/v1/auth/refresh", headers=cookie),
        )

        assert sorted(r.status_code for r in responses) == [200, 401]
        async with SessionLocal() as db:
            claimed = await db.scalar(select(func.count()).where(RefreshSession.used_at.is_not(None)))
        assert claimed == 1


class TestLogout:
    async def test_logout_revokes_session_and_clears_cookie(self, client: httpx.AsyncClient) -> None:
        token = await login_and_get_refresh_token(client)

        client.cookies.clear()
        response = await client.post("/api/v1/auth/logout", headers={"Cookie": f"{REFRESH_COOKIE}={token}"})

        assert response.status_code == 204
        assert 'lp_refresh=""' in response.headers["set-cookie"] or "max-age=0" in response.headers["set-cookie"].lower()
        assert (await refresh_with(client, token)).status_code == 401

    async def test_logout_without_a_session_is_harmless(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/api/v1/auth/logout")).status_code == 204

    async def test_logout_ends_only_this_device(self, client: httpx.AsyncClient) -> None:
        laptop = await login_and_get_refresh_token(client)
        phone = (
            await client.post("/api/v1/auth/login", json={"email": "yash@example.com", "password": PASSWORD})
        ).cookies[REFRESH_COOKIE]

        client.cookies.clear()
        await client.post("/api/v1/auth/logout", headers={"Cookie": f"{REFRESH_COOKIE}={laptop}"})

        assert (await refresh_with(client, laptop)).status_code == 401
        assert (await refresh_with(client, phone)).status_code == 200
