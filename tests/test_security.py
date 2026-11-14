"""Unit tests for password hashing and access tokens. No database, no HTTP."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

PASSWORD = "correct horse battery staple"


class TestPasswordHashing:
    def test_hash_is_argon2id_and_not_the_password(self) -> None:
        hashed = hash_password(PASSWORD)

        assert hashed.startswith("$argon2id$")
        assert PASSWORD not in hashed

    def test_same_password_gets_a_different_salt_each_time(self) -> None:
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_verify_accepts_correct_and_rejects_wrong_password(self) -> None:
        hashed = hash_password(PASSWORD)

        assert verify_password(hashed, PASSWORD) is True
        assert verify_password(hashed, PASSWORD + "!") is False

    def test_corrupt_hash_never_matches(self) -> None:
        assert verify_password("not-a-real-hash", PASSWORD) is False


def _b64url(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class TestAccessTokens:
    def test_round_trip_returns_the_user_id(self) -> None:
        user_id = uuid.uuid7()

        token, expires_in = create_access_token(user_id)

        assert decode_access_token(token) == user_id
        assert expires_in == get_settings().access_token_expire_minutes * 60

    def test_expired_token_is_rejected(self) -> None:
        long_ago = datetime.now(UTC) - timedelta(days=1)
        token, _ = create_access_token(uuid.uuid7(), now=long_ago)

        with pytest.raises(TokenError, match="expired"):
            decode_access_token(token)

    def test_tampered_payload_is_rejected(self) -> None:
        token, _ = create_access_token(uuid.uuid7())
        header, _, signature = token.split(".")
        # Swap in a different user id but keep the original signature.
        forged_payload = _b64url({"sub": str(uuid.uuid7()), "type": "access", "iat": 0, "exp": 9_999_999_999})

        with pytest.raises(TokenError):
            decode_access_token(f"{header}.{forged_payload}.{signature}")

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        payload = {"sub": str(uuid.uuid7()), "type": "access", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)}
        token = jwt.encode(payload, "an-attackers-own-secret-key-that-is-long-enough", algorithm="HS256")

        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_unsigned_alg_none_token_is_rejected(self) -> None:
        header = _b64url({"alg": "none", "typ": "JWT"})
        payload = _b64url({"sub": str(uuid.uuid7()), "type": "access", "iat": 0, "exp": 9_999_999_999})

        with pytest.raises(TokenError):
            decode_access_token(f"{header}.{payload}.")

    def test_token_of_another_type_is_rejected(self) -> None:
        now = datetime.now(UTC)
        payload = {"sub": str(uuid.uuid7()), "type": "refresh", "iat": now, "exp": now + timedelta(minutes=5)}
        token = jwt.encode(payload, get_settings().jwt_secret_key.get_secret_value(), algorithm="HS256")

        with pytest.raises(TokenError, match="not an access token"):
            decode_access_token(token)

    def test_token_missing_required_claims_is_rejected(self) -> None:
        token = jwt.encode({"sub": str(uuid.uuid7())}, get_settings().jwt_secret_key.get_secret_value(), algorithm="HS256")

        with pytest.raises(TokenError):
            decode_access_token(token)
