"""Structured JSON logging for production observability."""

import json
import logging
import sys
from datetime import datetime, timezone

from app.observability.middleware import get_request_id


class JSONFormatter(logging.Formatter):
    """Format each log record as a single JSON line.

    Fields emitted:
        timestamp   — ISO-8601 UTC
        level       — DEBUG / INFO / WARNING / ERROR / CRITICAL
        logger      — dot-separated module path (e.g. app.api.routes.chat)
        message     — human-readable log message
        request_id  — correlation ID from the current request (if available)
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            entry["request_id"] = request_id
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(*, level: str = "INFO") -> None:
    """Set up structured JSON logging for the entire application.

    Call once at startup, before any loggers are used. All ``app.*``
    loggers inherit this configuration automatically.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger("app")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(handler)
    root_logger.propagate = False

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "qdrant_client", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
