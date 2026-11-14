from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.core.security import create_access_token
from app.db.session import DbSession
from app.modules.auth.cookies import clear_refresh_cookie, set_refresh_cookie
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.modules.auth.service import authenticate, register_user
from app.modules.auth.sessions import (
    REFRESH_COOKIE,
    InvalidRefreshTokenError,
    end_session,
    rotate_session,
    start_session,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserRead)
async def register(body: RegisterRequest, db: DbSession) -> User:
    return await register_user(db, body)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession, request: Request, response: Response) -> TokenResponse:
    user = await authenticate(db, body.email, body.password)
    refresh_token = await start_session(db, user.id, request.headers.get("user-agent"))
    set_refresh_cookie(response, refresh_token)
    access_token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    db: DbSession, request: Request, response: Response, refresh_token: RefreshCookie = None
) -> TokenResponse:
    """Swap the refresh cookie for a new access token and a new (rotated) refresh cookie."""
    if not refresh_token:
        raise InvalidRefreshTokenError()
    user_id, new_refresh_token = await rotate_session(db, refresh_token, request.headers.get("user-agent"))
    set_refresh_cookie(response, new_refresh_token)
    access_token, expires_in = create_access_token(user_id)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: DbSession, response: Response, refresh_token: RefreshCookie = None) -> None:
    """End the session on the server and delete the cookie. Safe to call when already logged out."""
    if refresh_token:
        await end_session(db, refresh_token)
    clear_refresh_cookie(response)
