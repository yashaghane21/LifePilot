"""Password hashing (Argon2id) and access tokens (JWT). Pure functions: no DB, no HTTP."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# argon2-cffi defaults to Argon2id with the RFC 9106 "low memory" profile (64 MiB, 3 passes).
_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """The token is missing claims, expired, tampered with, or not an access token."""


def hash_password(password: str) -> str:
    """Return an encoded Argon2id hash; the salt and parameters are stored inside it."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        # A corrupt or unsupported hash must never be treated as a match.
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker parameters than the current ones."""
    return _hasher.check_needs_rehash(password_hash)


@cache
def _dummy_hash() -> str:
    return _hasher.hash("timing-equaliser-not-a-real-password")


def burn_password_check() -> None:
    """Spend the same time as a real verification, for logins with an unknown email.

    Without it, "no such user" answers measurably faster than "wrong password",
    which reveals which emails have accounts.
    """
    verify_password(_dummy_hash(), "wrong-password")


def generate_refresh_token() -> str:
    """256 random bits, URL-safe. Opaque: it means nothing without the database row."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 is enough here (unlike passwords): 256 random bits cannot be guessed,
    so a slow hash adds nothing. Only the hash is stored, so a DB leak exposes no sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID, *, now: datetime | None = None) -> tuple[str, int]:
    """Return (signed token, lifetime in seconds)."""
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + lifetime,
        "jti": uuid.uuid4().hex,  # unique per token; enables revocation lists later
    }
    token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> uuid.UUID:
    """Verify signature, expiry and type; return the user id. Raises TokenError otherwise."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            # Pinned: never let the token's own header choose the algorithm ("alg": "none" attack).
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload["type"] != ACCESS_TOKEN_TYPE:
        raise TokenError("not an access token")
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed subject") from exc
