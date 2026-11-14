import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.errors import error_response
from app.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# Client-supplied IDs are accepted only if they are short and plain, to prevent log injection.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

logger = logging.getLogger("app.request")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, log one line per request, and turn crashes into a safe 500."""
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Full traceback goes to the logs; the client gets no internals.
            logger.exception(
                "unhandled_exception",
                extra={"method": request.method, "path": request.url.path},
            )
            response = error_response(500, "internal_error", "Internal server error")

        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        request_id_var.reset(token)
