"""The refresh-token cookie, set identically by password login and Google sign-in."""

from fastapi import Response

from app.core.config import get_settings
from app.modules.auth.sessions import REFRESH_COOKIE

# The refresh cookie is only ever sent to the auth endpoints, never to the rest of the API.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,  # JavaScript can never read it, so XSS cannot steal it
        secure=settings.cookie_secure,
        samesite="strict",  # never sent on requests started by other sites (CSRF)
    )


def clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )
