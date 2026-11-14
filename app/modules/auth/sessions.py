"""Refresh-token sessions: start on login, rotate on refresh, revoke on logout or theft."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import generate_refresh_token, hash_refresh_token
from app.modules.auth.models import RefreshSession
from app.modules.users.service import get_user_by_id

logger = logging.getLogger(__name__)

REFRESH_COOKIE = "lp_refresh"


class InvalidRefreshTokenError(AppError):
    status_code = 401
    code = "invalid_refresh_token"

    def __init__(self) -> None:
        super().__init__("Your session has ended. Please sign in again.")


def _new_session_row(user_id: uuid.UUID, family_id: uuid.UUID, user_agent: str | None) -> tuple[RefreshSession, str]:
    token = generate_refresh_token()
    row = RefreshSession(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_refresh_token(token),
        user_agent=user_agent[:200] if user_agent else None,
        expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days),
    )
    return row, token


async def start_session(db: AsyncSession, user_id: uuid.UUID, user_agent: str | None) -> str:
    """Begin a new session family at login. Returns the raw refresh token for the cookie."""
    row, token = _new_session_row(user_id, uuid.uuid7(), user_agent)
    db.add(row)
    await db.commit()
    return token


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await db.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def rotate_session(db: AsyncSession, token: str, user_agent: str | None) -> tuple[uuid.UUID, str]:
    """Exchange a refresh token for its successor. Returns (user_id, new raw token)."""
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(token)

    # Atomic compare-and-set: of two concurrent requests with the same token, exactly one
    # gets a row back. A read-then-write ("is it unused? then mark it") would let both pass.
    claimed = (
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash == token_hash,
                RefreshSession.used_at.is_(None),
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            )
            .values(used_at=now)
            .returning(RefreshSession.user_id, RefreshSession.family_id)
        )
    ).one_or_none()

    if claimed is None:
        await _handle_rejected_token(db, token_hash, now)
        raise InvalidRefreshTokenError()

    user_id, family_id = claimed
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        await _revoke_family(db, family_id, now)
        await db.commit()
        raise InvalidRefreshTokenError()

    row, new_token = _new_session_row(user_id, family_id, user_agent)
    db.add(row)
    await db.commit()
    return user_id, new_token


async def _handle_rejected_token(db: AsyncSession, token_hash: str, now: datetime) -> None:
    """A token that was already used is being replayed: assume theft, end the whole family."""
    existing = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash))
    if existing is not None and existing.used_at is not None and existing.revoked_at is None:
        await _revoke_family(db, existing.family_id, now)
        await db.commit()
        logger.warning(
            "refresh_token_reuse_detected",
            extra={"user_id": str(existing.user_id), "family_id": str(existing.family_id)},
        )


async def end_session(db: AsyncSession, token: str) -> None:
    """Logout: revoke the token's whole family. Unknown tokens are ignored (idempotent)."""
    existing = await db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(token))
    )
    if existing is not None:
        await _revoke_family(db, existing.family_id, datetime.now(UTC))
        await db.commit()
        logger.info("logout", extra={"user_id": str(existing.user_id)})
