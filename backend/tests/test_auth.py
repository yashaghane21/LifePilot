"""Integration tests: register, login and the current-user dependency, against the test DB."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, select, update

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.modules.users.models import User

pytestmark = pytest.mark.usefixtures("clean_db")

PASSWORD = "correct horse battery staple"


async def register(
    client: httpx.AsyncClient, email: str = "yash@example.com", password: str = PASSWORD, full_name: str = "Yash"
) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "full_name": full_name}
    )


async def login(client: httpx.AsyncClient, email: str = "yash@example.com", password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def token_for(client: httpx.AsyncClient, email: str) -> str:
    await register(client, email=email)
    return (await login(client, email=email)).json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def load_user(email: str) -> User:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


class TestRegister:
    async def test_creates_user_and_returns_public_fields_only(self, client: httpx.AsyncClient) -> None:
        response = await register(client)

        assert response.status_code == 201
        body = response.json()
        assert set(body) == {"id", "email", "full_name", "created_at"}
        assert body["email"] == "yash@example.com"
        assert uuid.UUID(body["id"]).version == 7
        assert PASSWORD not in response.text

    async def test_password_is_stored_as_argon2id_hash(self, client: httpx.AsyncClient) -> None:
        await register(client)

        user = await load_user("yash@example.com")

        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash

    async def test_email_is_normalised_to_lowercase(self, client: httpx.AsyncClient) -> None:
        response = await register(client, email="Yash@Example.COM")

        assert response.json()["email"] == "yash@example.com"

    async def test_duplicate_email_is_rejected_case_insensitively(self, client: httpx.AsyncClient) -> None:
        await register(client, email="yash@example.com")

        response = await register(client, email="YASH@example.com")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_taken"

    async def test_short_password_is_rejected_without_echoing_it(self, client: httpx.AsyncClient) -> None:
        response = await register(client, password="short-pw")

        assert response.status_code == 422
        assert [d["loc"] for d in response.json()["error"]["details"]] == [["body", "password"]]
        assert "short-pw" not in response.text

    async def test_invalid_email_is_rejected(self, client: httpx.AsyncClient) -> None:
        response = await register(client, email="not-an-email")

        assert response.status_code == 422


class TestLogin:
    async def test_returns_bearer_token(self, client: httpx.AsyncClient) -> None:
        await register(client)

        response = await login(client)

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 30 * 60
        assert body["access_token"].count(".") == 2

    async def test_email_is_case_insensitive(self, client: httpx.AsyncClient) -> None:
        await register(client)

        assert (await login(client, email="YASH@EXAMPLE.COM")).status_code == 200

    async def test_wrong_password_and_unknown_email_look_identical(self, client: httpx.AsyncClient) -> None:
        await register(client)

        wrong_password = await login(client, password="not the right password")
        unknown_email = await login(client, email="nobody@example.com")

        for response in (wrong_password, unknown_email):
            assert response.status_code == 401
            assert response.headers["WWW-Authenticate"] == "Bearer"
        # Same code and message, so the response never reveals whether the account exists.
        strip_id = lambda r: {k: v for k, v in r.json()["error"].items() if k != "request_id"}  # noqa: E731
        assert strip_id(wrong_password) == strip_id(unknown_email)
        assert strip_id(wrong_password)["code"] == "invalid_credentials"

    async def test_inactive_user_cannot_log_in(self, client: httpx.AsyncClient) -> None:
        await register(client)
        async with SessionLocal() as db:
            await db.execute(update(User).values(is_active=False))
            await db.commit()

        assert (await login(client)).status_code == 401


class TestCurrentUser:
    async def test_returns_the_token_owner(self, client: httpx.AsyncClient) -> None:
        token = await token_for(client, "yash@example.com")

        response = await client.get("/api/v1/users/me", headers=bearer(token))

        assert response.status_code == 200
        assert response.json()["email"] == "yash@example.com"

    async def test_each_token_sees_only_its_own_user(self, client: httpx.AsyncClient) -> None:
        yash = await token_for(client, "yash@example.com")
        rutu = await token_for(client, "rutu@example.com")

        assert (await client.get("/api/v1/users/me", headers=bearer(yash))).json()["email"] == "yash@example.com"
        assert (await client.get("/api/v1/users/me", headers=bearer(rutu))).json()["email"] == "rutu@example.com"

    async def test_missing_token_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_garbage_token_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/users/me", headers=bearer("not.a.jwt"))

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_expired_token_is_401(self, client: httpx.AsyncClient) -> None:
        await register(client)
        user = await load_user("yash@example.com")
        token, _ = create_access_token(user.id, now=datetime.now(UTC) - timedelta(hours=2))

        response = await client.get("/api/v1/users/me", headers=bearer(token))

        assert response.status_code == 401

    async def test_token_stops_working_when_account_is_deactivated(self, client: httpx.AsyncClient) -> None:
        token = await token_for(client, "yash@example.com")
        async with SessionLocal() as db:
            await db.execute(update(User).values(is_active=False))
            await db.commit()

        response = await client.get("/api/v1/users/me", headers=bearer(token))

        assert response.status_code == 401

    async def test_token_of_deleted_user_is_401(self, client: httpx.AsyncClient) -> None:
        token = await token_for(client, "yash@example.com")
        async with SessionLocal() as db:
            await db.execute(delete(User))
            await db.commit()

        response = await client.get("/api/v1/users/me", headers=bearer(token))

        assert response.status_code == 401
