from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError
from app.core.security import TokenError, decode_access_token
from app.db.session import DbSession
from app.modules.auth.service import BEARER_CHALLENGE
from app.modules.users.models import User
from app.modules.users.service import get_user_by_id

# auto_error=False: we raise our own errors so they use the standard error format.
_bearer = HTTPBearer(auto_error=False, description="Access token from POST /api/v1/auth/login")


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"
    headers = BEARER_CHALLENGE


class InvalidTokenError(AppError):
    status_code = 401
    code = "invalid_token"
    headers = BEARER_CHALLENGE


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    """Resolve the bearer token to an active user, or stop the request with 401."""
    if credentials is None:
        raise NotAuthenticatedError("Authentication required")

    try:
        user_id = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise InvalidTokenError("Invalid or expired token") from exc

    # A valid signature isn't enough: the account may have been deleted or deactivated
    # after the token was issued.
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("Invalid or expired token")
    return user


# Use in endpoint signatures: `user: CurrentUser`. Every user-owned query filters on user.id.
CurrentUser = Annotated[User, Depends(get_current_user)]
