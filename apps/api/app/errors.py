"""Domain exceptions and the single handler that maps them to the API error shape (docs/04 §1)."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()


class AppError(Exception):
    code = "internal"
    status = 500
    message = "Something went wrong."

    def __init__(self, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}


class Unauthorized(AppError):
    code, status, message = "unauthorized", 401, "Sign in to continue."


class Forbidden(AppError):
    code, status, message = "forbidden", 403, "You don't have access to this."


class NotFound(AppError):
    code, status, message = "not_found", 404, "Not found."


class Invalid(AppError):
    code, status, message = "validation_error", 422, "Some fields are invalid."


class RateLimited(AppError):
    code, status, message = "rate_limited", 429, "Too many requests. Slow down a little."


class Conflict(AppError):
    code, status, message = "conflict", 409, "This conflicts with existing data."


class ServiceUnavailable(AppError):
    code, status, message = "provider_unavailable", 503, "A required service is unavailable."


_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "validation_error",
    409: "conflict",
    429: "rate_limited",
}


def _body(request: Request, code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None)
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(_body(request, exc.code, exc.message, exc.details), exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            _body(request, "validation_error", "Some fields are invalid.", {"errors": errors}), 422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        code = _HTTP_CODES.get(exc.status_code, "internal")
        return JSONResponse(_body(request, code, str(exc.detail), {}), exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(_body(request, "internal", AppError.message, {}), 500)
