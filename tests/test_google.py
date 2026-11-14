"""Google sign-in against a fake Google that signs real RS256 ID tokens.

Only the two network calls (token exchange, key download) are replaced; signature, audience,
issuer, expiry, nonce, state and PKCE checks all run for real.
"""

import base64
import hashlib
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.auth import google
from app.modules.auth.models import OAuthIdentity
from app.modules.auth.sessions import REFRESH_COOKIE
from app.modules.users.models import User
from tests.test_auth import PASSWORD, login, register
from tests.test_sessions import refresh_with

pytestmark = pytest.mark.usefixtures("clean_db")

START = "/api/v1/auth/google/start"
CALLBACK = "/api/v1/auth/google/callback"


class FakeGoogle:
    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.next_id_token: str | None = None
        self.exchanged: list[tuple[str, str]] = []

    # `/` makes `nonce` positional-only, so a test can still override the claim via **overrides.
    def id_token(self, nonce: str, /, *, key: Any = None, **overrides: Any) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": get_settings().google_client_id,
            "sub": "google-sub-123",
            "email": "yash@gmail.com",
            "email_verified": True,
            "name": "Yash Aghane",
            "nonce": nonce,
            "iat": now,
            "exp": now + 300,
        } | overrides
        return jwt.encode(claims, key or self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    async def exchange_code(self, code: str, code_verifier: str) -> str:
        self.exchanged.append((code, code_verifier))
        assert self.next_id_token is not None
        return self.next_id_token


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    fake = FakeGoogle()
    public_key = fake.private_key.public_key()
    monkeypatch.setattr(google, "exchange_code", fake.exchange_code)
    monkeypatch.setattr(
        google,
        "_jwks_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)),
    )
    return fake


def web(path: str) -> str:
    return f"{get_settings().web_app_url}{path}"


async def start_flow(client: httpx.AsyncClient, next_path: str | None = None) -> dict[str, str]:
    response = await client.get(START, params={"next": next_path} if next_path else None)
    assert response.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}


async def google_sign_in(
    client: httpx.AsyncClient, fake: FakeGoogle, next_path: str | None = None, **claims: Any
) -> httpx.Response:
    params = await start_flow(client, next_path)
    fake.next_id_token = fake.id_token(params["nonce"], **claims)
    return await client.get(CALLBACK, params={"code": "auth-code", "state": params["state"]})


async def load_user(email: str) -> User | None:
    async with SessionLocal() as db:
        return await db.scalar(select(User).where(User.email == email))


class TestStart:
    async def test_redirects_to_google_with_state_nonce_and_pkce(self, client: httpx.AsyncClient) -> None:
        response = await client.get(START)

        assert response.status_code == 302
        location = urlsplit(response.headers["location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == get_settings().google_authorize_url
        params = {k: v[0] for k, v in parse_qs(location.query).items()}
        assert params["client_id"] == get_settings().google_client_id
        assert params["redirect_uri"] == get_settings().google_redirect_uri
        assert params["scope"] == "openid email profile"
        assert params["code_challenge_method"] == "S256"
        assert len(params["state"]) >= 40 and len(params["nonce"]) >= 40

    async def test_sets_a_lax_httponly_state_cookie_scoped_to_the_callback(self, client: httpx.AsyncClient) -> None:
        response = await client.get(START)

        set_cookie = response.headers["set-cookie"].lower()
        for attribute in ("lp_oauth=", "httponly", "secure", "samesite=lax", "path=/api/v1/auth/google", "max-age=600"):
            assert attribute in set_cookie

    async def test_pkce_verifier_sent_to_google_matches_the_challenge(
        self, client: httpx.AsyncClient, fake_google: FakeGoogle
    ) -> None:
        params = await start_flow(client)
        fake_google.next_id_token = fake_google.id_token(params["nonce"])

        await client.get(CALLBACK, params={"code": "auth-code", "state": params["state"]})

        [(_code, verifier)] = fake_google.exchanged
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        assert challenge == params["code_challenge"]


class TestNewUser:
    async def test_creates_verified_passwordless_user_and_signs_in(
        self, client: httpx.AsyncClient, fake_google: FakeGoogle
    ) -> None:
        response = await google_sign_in(client, fake_google)

        assert response.status_code == 302
        assert response.headers["location"] == web("/")
        assert REFRESH_COOKIE in response.cookies
        user = await load_user("yash@gmail.com")
        assert user is not None
        assert user.full_name == "Yash Aghane"
        assert user.password_hash is None
        assert user.email_verified_at is not None

    async def test_the_new_session_works(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        response = await google_sign_in(client, fake_google)

        refreshed = await refresh_with(client, response.cookies[REFRESH_COOKIE])

        assert refreshed.status_code == 200

    async def test_returns_to_the_requested_page(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        response = await google_sign_in(client, fake_google, next_path="/finance")

        assert response.headers["location"] == web("/finance")

    @pytest.mark.parametrize("evil", ["//evil.com", "https://evil.com", "/\\evil.com"])
    async def test_never_redirects_off_site(
        self, client: httpx.AsyncClient, fake_google: FakeGoogle, evil: str
    ) -> None:
        response = await google_sign_in(client, fake_google, next_path=evil)

        assert response.headers["location"] == web("/")

    async def test_password_login_is_impossible_for_google_only_user(
        self, client: httpx.AsyncClient, fake_google: FakeGoogle
    ) -> None:
        await google_sign_in(client, fake_google)

        response = await login(client, email="yash@gmail.com", password=PASSWORD)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"


class TestReturningUser:
    async def test_same_google_account_reuses_the_user(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        await google_sign_in(client, fake_google)
        await google_sign_in(client, fake_google, email="changed-address@gmail.com")

        async with SessionLocal() as db:
            users = (await db.scalars(select(User))).all()
            identities = (await db.scalars(select(OAuthIdentity))).all()
        # Matched on Google's permanent `sub`, not on the (changed) email.
        assert len(users) == 1 and len(identities) == 1


class TestPreAccountHijacking:
    async def test_google_owner_takes_over_an_unverified_password_account(
        self, client: httpx.AsyncClient, fake_google: FakeGoogle
    ) -> None:
        # Someone registered the address first, with a password the real owner doesn't know.
        await register(client, email="yash@gmail.com")
        attacker_session = (await login(client, email="yash@gmail.com")).cookies[REFRESH_COOKIE]

        await google_sign_in(client, fake_google)

        assert (await login(client, email="yash@gmail.com")).status_code == 401
        assert (await refresh_with(client, attacker_session)).status_code == 401
        user = await load_user("yash@gmail.com")
        assert user is not None and user.password_hash is None and user.email_verified_at is not None

    async def test_unverified_google_email_is_refused(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        response = await google_sign_in(client, fake_google, email_verified=False)

        assert response.headers["location"] == web("/login?error=google_email_unverified")
        assert await load_user("yash@gmail.com") is None


class TestRejectedCallbacks:
    async def assert_failed(self, response: httpx.Response, code: str = "google_failed") -> None:
        assert response.status_code == 302
        assert response.headers["location"] == web(f"/login?error={code}")
        assert REFRESH_COOKIE not in response.cookies
        assert await load_user("yash@gmail.com") is None

    async def test_state_mismatch(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        params = await start_flow(client)
        fake_google.next_id_token = fake_google.id_token(params["nonce"])

        response = await client.get(CALLBACK, params={"code": "auth-code", "state": "attacker-state"})

        await self.assert_failed(response)

    async def test_missing_state_cookie(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        params = await start_flow(client)
        fake_google.next_id_token = fake_google.id_token(params["nonce"])
        client.cookies.clear()  # e.g. a callback link sent to the victim by an attacker

        response = await client.get(CALLBACK, params={"code": "auth-code", "state": params["state"]})

        await self.assert_failed(response)

    async def test_user_cancelled_at_google(self, client: httpx.AsyncClient) -> None:
        params = await start_flow(client)

        response = await client.get(CALLBACK, params={"error": "access_denied", "state": params["state"]})

        await self.assert_failed(response, "google_cancelled")

    @pytest.mark.parametrize(
        "claims",
        [
            {"aud": "some-other-apps-client-id"},
            {"iss": "https://evil.example.com"},
            {"nonce": "replayed-old-nonce"},
            {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        ],
        ids=["wrong-audience", "wrong-issuer", "wrong-nonce", "expired"],
    )
    async def test_bad_id_token(self, client: httpx.AsyncClient, fake_google: FakeGoogle, claims: dict[str, Any]) -> None:
        await self.assert_failed(await google_sign_in(client, fake_google, **claims))

    async def test_id_token_signed_by_another_key(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        params = await start_flow(client)
        forger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        fake_google.next_id_token = fake_google.id_token(params["nonce"], key=forger)

        response = await client.get(CALLBACK, params={"code": "auth-code", "state": params["state"]})

        await self.assert_failed(response)

    async def test_state_cookie_is_single_use(self, client: httpx.AsyncClient, fake_google: FakeGoogle) -> None:
        response = await google_sign_in(client, fake_google)

        state_cookie = [c for c in response.headers.get_list("set-cookie") if c.startswith("lp_oauth=")]
        assert len(state_cookie) == 1
        assert "max-age=0" in state_cookie[0].lower()
