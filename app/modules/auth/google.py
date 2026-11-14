"""Google sign-in (OpenID Connect authorization-code flow with PKCE).

The security-critical step, verifying the ID token's RS256 signature against Google's
published keys, is done by PyJWT. This module wires the protocol steps together.
"""

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = "openid email profile"
STATE_COOKIE = "lp_oauth"
# Only the callback needs the state cookie.
STATE_COOKIE_PATH = "/api/v1/auth/google"
STATE_TTL = timedelta(minutes=10)
_STATE_TOKEN_TYPE = "oauth_state"


class GoogleSignInError(Exception):
    """Sign-in could not complete. `code` is safe to show the user; `detail` is for logs only."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class GoogleClaims(BaseModel):
    subject: str
    email: str
    email_verified: bool
    name: str | None


@dataclass(frozen=True)
class PendingSignIn:
    """What the callback needs to check that it belongs to the sign-in this browser started."""

    state: str
    code_verifier: str
    nonce: str
    next_path: str

    @classmethod
    def new(cls, next_path: str) -> "PendingSignIn":
        return cls(
            state=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            nonce=secrets.token_urlsafe(32),
            next_path=next_path,
        )


def safe_next_path(value: str | None) -> str:
    """Only in-app paths. "//evil.com" and "/\\evil.com" are both read by browsers as other sites."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(pending: PendingSignIn) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": pending.state,
        "nonce": pending.nonce,
        "code_challenge": _pkce_challenge(pending.code_verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{settings.google_authorize_url}?{urlencode(params)}"


def encode_pending(pending: PendingSignIn) -> str:
    """Sign the pending sign-in into the state cookie, so it cannot be forged or edited."""
    now = datetime.now(UTC)
    payload = {
        "type": _STATE_TOKEN_TYPE,
        "state": pending.state,
        "verifier": pending.code_verifier,
        "nonce": pending.nonce,
        "next": pending.next_path,
        "iat": now,
        "exp": now + STATE_TTL,
    }
    return jwt.encode(payload, get_settings().jwt_secret_key.get_secret_value(), algorithm="HS256")


def decode_pending(token: str) -> PendingSignIn:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "type", "state", "verifier", "nonce", "next"]},
        )
    except jwt.PyJWTError as exc:
        raise GoogleSignInError("google_failed", f"bad state cookie: {exc}") from exc
    if payload["type"] != _STATE_TOKEN_TYPE:
        raise GoogleSignInError("google_failed", "state cookie has the wrong type")
    return PendingSignIn(
        state=payload["state"],
        code_verifier=payload["verifier"],
        nonce=payload["nonce"],
        next_path=safe_next_path(payload["next"]),
    )


def check_state(pending: PendingSignIn, returned_state: str) -> None:
    # Constant-time comparison: no timing hints about how much of the state matched.
    if not hmac.compare_digest(pending.state, returned_state):
        raise GoogleSignInError("google_failed", "state mismatch")


async def exchange_code(code: str, code_verifier: str) -> str:
    """Server-to-server: trade the authorization code for tokens. Returns the ID token."""
    settings = get_settings()
    assert settings.google_client_id and settings.google_client_secret
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret.get_secret_value(),
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(settings.google_token_url, data=data)
    except httpx.HTTPError as exc:
        raise GoogleSignInError("google_failed", f"token endpoint unreachable: {exc!r}") from exc

    if response.status_code != 200:
        # Google's error body names the problem (e.g. invalid_grant) without secrets.
        raise GoogleSignInError("google_failed", f"token endpoint {response.status_code}: {response.text[:200]}")
    id_token = response.json().get("id_token")
    if not isinstance(id_token, str):
        raise GoogleSignInError("google_failed", "token response had no id_token")
    return id_token


@cache
def _jwks_client() -> jwt.PyJWKClient:
    # Caches Google's public keys; refetches when a token names a key id it hasn't seen.
    return jwt.PyJWKClient(get_settings().google_jwks_url, cache_keys=True, lifespan=3600, timeout=10)


def verify_id_token(id_token: str, expected_nonce: str) -> GoogleClaims:
    """Check signature, audience, issuer, expiry and nonce. Blocking (may fetch keys): run in a thread."""
    settings = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.google_client_id,  # issued for US, not for some other app
            issuer=settings.google_issuers,
            options={"require": ["sub", "aud", "iss", "exp", "iat"]},
            leeway=30,  # tolerate small clock differences between servers
        )
    except jwt.PyJWTError as exc:
        raise GoogleSignInError("google_failed", f"invalid id_token: {exc}") from exc

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
        raise GoogleSignInError("google_failed", "nonce mismatch")

    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise GoogleSignInError("google_failed", "id_token has no email")

    name = claims.get("name")
    return GoogleClaims(
        subject=str(claims["sub"]),
        email=email.lower(),
        # Google sends a real boolean; anything else is treated as unverified.
        email_verified=claims.get("email_verified") is True,
        name=name.strip()[:100] if isinstance(name, str) and name.strip() else None,
    )
