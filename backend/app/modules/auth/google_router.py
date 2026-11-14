import asyncio
import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import DbSession
from app.modules.auth import google
from app.modules.auth.cookies import set_refresh_cookie
from app.modules.auth.google import STATE_COOKIE, STATE_COOKIE_PATH, STATE_TTL, GoogleSignInError, PendingSignIn
from app.modules.auth.service import sign_in_with_google
from app.modules.auth.sessions import start_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth"])


class GoogleNotConfiguredError(AppError):
    status_code = 404
    code = "google_not_configured"


def _web_redirect(path: str) -> RedirectResponse:
    response = RedirectResponse(f"{get_settings().web_app_url}{path}", status_code=302)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)  # single use, success or not
    return response


@router.get("/start")
async def start(next_path: Annotated[str | None, Query(alias="next")] = None) -> RedirectResponse:
    """Begin Google sign-in: remember state/PKCE/nonce in a signed cookie, then go to Google."""
    if not google.is_configured():
        raise GoogleNotConfiguredError("Google sign-in is not configured on this server")

    pending = PendingSignIn.new(google.safe_next_path(next_path))
    response = RedirectResponse(google.build_authorization_url(pending), status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        google.encode_pending(pending),
        max_age=int(STATE_TTL.total_seconds()),
        path=STATE_COOKIE_PATH,
        httponly=True,
        secure=get_settings().cookie_secure,
        # Lax, not Strict: the callback is a navigation from accounts.google.com (another
        # site), and Strict cookies are not sent on cross-site navigations.
        samesite="lax",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    pending_cookie: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> RedirectResponse:
    """Google sends the browser here. Every failure lands on /login with a short error code."""
    try:
        if error:
            raise GoogleSignInError("google_cancelled" if error == "access_denied" else "google_failed", error)
        if not pending_cookie or not code or not state:
            raise GoogleSignInError("google_failed", "missing state cookie, code or state")

        pending = google.decode_pending(pending_cookie)
        google.check_state(pending, state)
        id_token = await google.exchange_code(code, pending.code_verifier)
        claims = await asyncio.to_thread(google.verify_id_token, id_token, pending.nonce)
        user = await sign_in_with_google(db, claims)
    except GoogleSignInError as exc:
        logger.warning("google_sign_in_failed", extra={"reason": exc.code, "detail": exc.detail})
        return _web_redirect(f"/login?{urlencode({'error': exc.code})}")

    refresh_token = await start_session(db, user.id, request.headers.get("user-agent"))
    response = _web_redirect(pending.next_path)
    set_refresh_cookie(response, refresh_token)
    return response
