"""The one error shape every client decodes (build plan section 8.1).

Every failure - ours or FastAPI's - leaves the backend as:

    {"error": {"code": "...", "message": "...", "requestId": "..."}}

The iOS app and the website both decode exactly this, so a route that raises a
bare `HTTPException` with a dict detail would break them. `ApiError` is the only
thing application code should raise; the handlers here translate everything else.

Messages are written for a person to read and must never carry a stack trace, a
SQL fragment or anything personal: `internal_error` is deliberately opaque.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Literal

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.security.request_id import REQUEST_ID_HEADER, get_request_id

log = logging.getLogger(__name__)

# The full code list from section 8.1. Keeping it as a Literal means a typo in a
# route is a type error rather than an undocumented code reaching a client.
ErrorCode = Literal[
    "unauthorized",
    "forbidden",
    "not_found",
    "validation_error",
    "consent_locked",
    "version_conflict",
    "upload_too_large",
    "unsupported_media",
    "rate_limited",
    "sarvam_unavailable",
    "internal_error",
]

# Fallback mapping for HTTPExceptions raised by FastAPI itself (404 on an unknown
# route, 405, the HTTPBearer 403, ...), which carry a status but no code.
_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    409: "version_conflict",
    413: "upload_too_large",
    415: "unsupported_media",
    422: "validation_error",
    429: "rate_limited",
    503: "sarvam_unavailable",
}


class ApiError(Exception):
    """A failure that is safe to describe to the caller.

    @param code     One of the documented `ErrorCode` values.
    @param message  Human-readable and free of internals.
    @param status_code  Overrides the default for the code.
    @param headers  Extra response headers, e.g. `Retry-After` on a 429.
    """

    _DEFAULT_STATUS: ClassVar[dict[str, int]] = {
        "unauthorized": status.HTTP_401_UNAUTHORIZED,
        "forbidden": status.HTTP_403_FORBIDDEN,
        "not_found": status.HTTP_404_NOT_FOUND,
        "validation_error": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "consent_locked": status.HTTP_409_CONFLICT,
        "version_conflict": status.HTTP_409_CONFLICT,
        "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
        "unsupported_media": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
        "sarvam_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.status_code = status_code or self._DEFAULT_STATUS[code]
        self.headers = headers or {}


# --- convenience constructors for the cases routes raise most often ----------


def unauthorized(message: str = "Not authenticated") -> ApiError:
    """401. The reason is intentionally vague: a precise one is a probing oracle."""
    return ApiError("unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "Admin access required") -> ApiError:
    """403. The caller is authenticated but not permitted."""
    return ApiError("forbidden", message)


def not_found(message: str = "Not found") -> ApiError:
    """404, also used for another user's resource (section 13.2).

    Returning 403 there would confirm the resource exists, so ownership failures
    are deliberately indistinguishable from a wrong id.
    """
    return ApiError("not_found", message)


def rate_limited(retry_after_seconds: int) -> ApiError:
    """429 with the `Retry-After` the client should honour."""
    return ApiError(
        "rate_limited",
        "Too many requests. Please slow down.",
        headers={"Retry-After": str(max(1, retry_after_seconds))},
    )


# --- rendering ---------------------------------------------------------------


def error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render the standard envelope, echoing the request id in body and header."""
    merged = {REQUEST_ID_HEADER: request_id, **(headers or {})}
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "requestId": request_id}},
        headers=merged,
    )


def _first_validation_message(errors: list[dict[str, Any]]) -> str:
    """Summarise a Pydantic error list into one readable sentence.

    Only the field path and Pydantic's own message are used. The rejected input
    is never echoed: it may be a transcript or another piece of personal data.
    """
    if not errors:
        return "Invalid request."
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    detail = str(first.get("msg", "is invalid"))
    extra = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
    return f"{loc or 'request'}: {detail}{extra}"


def install_error_handlers(app: FastAPI) -> None:
    """Attach handlers so every error path produces the standard envelope."""

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        # 5xx is our bug and deserves a stack trace in the log; 4xx is the
        # caller's and would just be noise at warning level.
        log.log(
            logging.ERROR if exc.status_code >= 500 else logging.INFO,
            "api error",
            extra={
                "code": exc.code,
                "status": exc.status_code,
                "path": request.url.path,
                "request_id": get_request_id(),
            },
            exc_info=exc.status_code >= 500,
        )
        return error_response(exc.code, exc.message, exc.status_code, get_request_id(), exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, "internal_error")
        detail = (
            exc.detail if isinstance(exc.detail, str) and exc.detail else code.replace("_", " ")
        )
        headers = dict(exc.headers or {})
        return error_response(code, detail, exc.status_code, get_request_id(), headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: list[dict[str, Any]] = jsonable_encoder(exc.errors())
        return error_response(
            "validation_error",
            _first_validation_message(errors),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            get_request_id(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The request id is the only thing the caller gets; the detail stays in
        # the log, where the redaction filter has already scrubbed it.
        log.exception(
            "unhandled exception",
            extra={"path": request.url.path, "request_id": get_request_id()},
        )
        return error_response(
            "internal_error",
            "Something went wrong. Please try again.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            get_request_id(),
        )
