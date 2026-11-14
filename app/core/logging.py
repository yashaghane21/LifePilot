import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set per request by the request-context middleware; read by every log line.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra=` and is logged as a field.
# `color_message` is uvicorn's ANSI-coloured duplicate of the message.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (request_id := request_id_var.get()) is not None:
            payload["request_id"] = request_id
        payload.update(
            {key: value for key, value in vars(record).items() if key not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Send all logs (ours and uvicorn's) to stdout as one JSON object per line."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # Replaced by our own request log, which carries request_id and duration.
    logging.getLogger("uvicorn.access").disabled = True
    # Chatty third-party loggers: per-request INFO lines are noise and can leak URLs.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
