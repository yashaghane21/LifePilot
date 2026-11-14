import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import burn_password_check, hash_password, password_needs_rehash, verify_password
from app.modules.auth.google import GoogleClaims, GoogleSignInError
from app.modules.auth.models import OAuthIdentity, RefreshSession
from app.modules.auth.schemas import RegisterRequest
from app.modules.users.models import User
from app.modules.users.service import get_user_by_email, get_user_by_id

logger = logging.getLogger(__name__)

BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


class EmailAlreadyRegisteredError(AppError):
    status_code = 409
    code = "email_taken"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    headers = BEARER_CHALLENGE

    def __init__(self) -> None:
        # One message for every failure reason, so responses don't reveal which emails exist.
        super().__init__("Incorrect email or password")


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    # Argon2 is ~50 ms of CPU; in a thread it doesn't freeze every other request.
    password_hash = await asyncio.to_thread(hash_password, data.password)
    user = User(email=data.email, full_name=data.full_name, password_hash=password_hash)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # The UNIQUE constraint is the real guard: a "check first" lookup races with
        # a concurrent registration of the same email.
        if "uq_users_email" in str(exc.orig):
            raise EmailAlreadyRegisteredError("An account with this email already exists") from exc
        raise

    logger.info("user_registered", extra={"user_id": str(user.id)})
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)

    if user is None:
        await asyncio.to_thread(burn_password_check)
        logger.info("login_failed", extra={"reason": "unknown_email"})
        raise InvalidCredentialsError()

    if user.password_hash is None:
        # A Google-only account: no password can match. Same error and timing as above.
        await asyncio.to_thread(burn_password_check)
        logger.info("login_failed", extra={"reason": "no_password", "user_id": str(user.id)})
        raise InvalidCredentialsError()

    if not await asyncio.to_thread(verify_password, user.password_hash, password):
        logger.info("login_failed", extra={"reason": "wrong_password", "user_id": str(user.id)})
        raise InvalidCredentialsError()

    if not user.is_active:
        logger.info("login_failed", extra={"reason": "inactive", "user_id": str(user.id)})
        raise InvalidCredentialsError()

    # Upgrade old hashes transparently when the hashing parameters are strengthened.
    if password_needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, password)
        await db.commit()

    logger.info("login_succeeded", extra={"user_id": str(user.id)})
    return user


async def sign_in_with_google(db: AsyncSession, claims: GoogleClaims) -> User:
    """Find, link or create the user for a verified Google identity."""
    now = datetime.now(UTC)

    identity = await db.scalar(
        select(OAuthIdentity).where(OAuthIdentity.provider == "google", OAuthIdentity.subject == claims.subject)
    )
    if identity is not None:
        user = await get_user_by_id(db, identity.user_id)
        if user is None or not user.is_active:
            raise GoogleSignInError("account_disabled", "linked user missing or inactive")
        logger.info("login_succeeded", extra={"user_id": str(user.id), "method": "google"})
        return user

    # Linking by email is only safe when Google vouches that this person owns the address.
    if not claims.email_verified:
        raise GoogleSignInError("google_email_unverified", "google reported email_verified=false")

    user = await get_user_by_email(db, claims.email)
    if user is None:
        user = User(
            email=claims.email,
            full_name=claims.name or claims.email.split("@")[0],
            password_hash=None,
            email_verified_at=now,
        )
        db.add(user)
        await db.flush()  # assigns user.id for the identity row
        logger.info("user_registered", extra={"user_id": str(user.id), "method": "google"})
    else:
        if not user.is_active:
            raise GoogleSignInError("account_disabled", "existing user inactive")
        if user.email_verified_at is None:
            # Pre-account hijacking defence: whoever registered this unverified account may not
            # be the email's owner. Google just proved ownership, so the owner takes it over:
            # the old password and every existing session stop working.
            user.password_hash = None
            user.email_verified_at = now
            await db.execute(
                update(RefreshSession)
                .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            logger.warning("unverified_account_claimed_via_google", extra={"user_id": str(user.id)})

    db.add(OAuthIdentity(user_id=user.id, provider="google", subject=claims.subject, email=claims.email))
    try:
        await db.commit()
    except IntegrityError as exc:
        # Two simultaneous first sign-ins for the same Google account or email.
        await db.rollback()
        raise GoogleSignInError("google_failed", "concurrent sign-in") from exc

    logger.info("google_identity_linked", extra={"user_id": str(user.id)})
    return user
