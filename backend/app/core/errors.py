"""Shared error format (PlaceChat Technical Design §7.2).

Shape: {"error": {"code": ..., "message": ..., ...extra}}.

Raise an AppError subclass anywhere in the backend; the handlers below turn it into the JSON
response, and the frontend shows `message` to the user.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"
    message = "The request could not be processed."

    def __init__(self, message: str | None = None, **extra: Any) -> None:
        self.message = message or type(self).message
        self.extra = extra
        super().__init__(self.message)


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Your session has expired. Refresh the page and try again."


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You are not allowed to do this."


class NotAMember(AppError):
    status_code = 403
    code = "NOT_A_MEMBER"
    message = "Join the room before sending messages."


class Blocked(AppError):
    status_code = 403
    code = "BLOCKED"
    message = "You are temporarily blocked from sending messages."

    def __init__(self, until: datetime, message: str | None = None) -> None:
        super().__init__(message, until=until.isoformat())


class CannotReportOwn(AppError):
    status_code = 403
    code = "CANNOT_REPORT_OWN"
    message = "You cannot report your own message."


class RoomNotFound(AppError):
    status_code = 404
    code = "ROOM_NOT_FOUND"
    message = "This room does not exist or has been closed."


class AlreadyReported(AppError):
    status_code = 409
    code = "ALREADY_REPORTED"
    message = "You already reported this message."


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "The request is not valid."


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        default = f"You are sending messages too fast. Try again in {retry_after} seconds."
        super().__init__(message or default, retry_after=retry_after)


def error_response(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, **exc.extra)


async def _handle_request_validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    message = ValidationFailed.message
    if errors:
        location = ".".join(str(part) for part in errors[0].get("loc", ()))
        message = f"{location}: {errors[0].get('msg', message)}"
    return error_response(422, ValidationFailed.code, message)


async def _handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "Something went wrong. Please try again.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
