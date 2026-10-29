"""JSON logging with a PII-redaction filter.

Rule from the build plan (section 13): never let a phone number, PAN, Aadhaar-like
digit run, OTP or raw transcript reach the logs. The filter is applied to the whole
logging tree, so a careless `logger.info(user_text)` anywhere is still scrubbed.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

# --- redaction patterns -------------------------------------------------------
# Ordered most-specific first: PAN before the generic 10-digit run, etc.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # PAN: 5 letters, 4 digits, 1 letter
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN]"),
    # Aadhaar-like: 12 digits, optionally grouped in 4s
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[AADHAAR]"),
    # Indian mobile, with or without +91 / 0 prefix
    (re.compile(r"(?:\+?91[ -]?|\b0)?[6-9]\d{9}\b"), "[MOBILE]"),
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # Bearer tokens / long opaque secrets
    (re.compile(r"\bBearer\s+[\w\-._~+/]+=*", re.IGNORECASE), "Bearer [TOKEN]"),
    # A bare 6-digit run is treated as an OTP
    (re.compile(r"(?<!\d)\d{6}(?!\d)"), "[OTP]"),
)

# Log record attributes that are not part of our structured payload.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "stacklevel",
        "thread",
        "threadName",
        "taskName",
    }
)


def redact(text: str) -> str:
    """Replace anything that looks like personal data with a placeholder."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class PiiRedactionFilter(logging.Filter):
    """Scrub the formatted message and every string value in `extra`."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
        except Exception:  # noqa: BLE001 - logging must never raise
            record.msg = "[unformattable log record]"
        record.args = ()

        for key, value in list(record.__dict__.items()):
            if key not in _RESERVED and isinstance(value, str):
                record.__dict__[key] = redact(value)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line - greppable in a noisy demo hall."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter and the redaction filter on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiRedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn ships its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # SQLAlchemy's engine logger is chatty and can echo parameter values.
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")
