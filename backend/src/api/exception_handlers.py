from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core import (
    MASKED_VALUE,
    AppException,
    is_sensitive_key,
    logger,
)


def _sanitize_pydantic_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Маскує поле 'input' у помилках валідації Pydantic v2 для чутливих полів (паролі, токени, секрети),
    щоб унеможливити витік відкритих облікових даних у відповідях API та системних журналах.
    """
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        err_copy = err.copy()
        loc = err_copy.get("loc", ())
        has_sensitive_key = any(isinstance(part, str) and is_sensitive_key(part) for part in loc)
        if has_sensitive_key and "input" in err_copy:
            err_copy["input"] = MASKED_VALUE
        sanitized.append(err_copy)
    return sanitized


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Обробник кастомних архітектурних винятків AppException."""
    if exc.status_code >= 500:
        logger.opt(exception=exc).error(
            "AppException 5xx ({code}) на {path}: {msg}",
            code=exc.error_code,
            path=request.url.path,
            msg=exc.message,
        )
    else:
        logger.warning(
            "AppException {status} ({code}) на {path}: {msg}",
            status=exc.status_code,
            code=exc.error_code,
            path=request.url.path,
            msg=exc.message,
        )

    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Обробник стандартних HTTPException Starlette/FastAPI (404 Not Found, 405 Method Not Allowed тощо)."""
    error_code_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        408: "REQUEST_TIMEOUT",
        409: "CONFLICT",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "UNPROCESSABLE_ENTITY",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    if isinstance(exc.detail, dict):
        error_code = exc.detail.get("error_code") or error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(exc.detail.get("message") or "Сталася помилка обробки запиту.")
        details: dict[str, Any] = {k: v for k, v in exc.detail.items() if k not in ("error_code", "message")}
    else:
        error_code = error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        details = {}

    if exc.status_code >= 500:
        logger.error(
            "HTTPException {status} ({code}) на {path}: {detail}",
            status=exc.status_code,
            code=error_code,
            path=request.url.path,
            detail=message,
        )
    else:
        logger.warning(
            "HTTPException {status} ({code}) на {path}: {detail}",
            status=exc.status_code,
            code=error_code,
            path=request.url.path,
            detail=message,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": error_code,
            "message": message,
            "details": details,
        },
        headers=exc.headers,
    )


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Обробник перевищення ліміту частоти запитів (429 Too Many Requests)."""
    client_ip = request.client.host if request.client else "unknown"
    logger.warning(
        "429 Too Many Requests | Path: {path} | IP: {ip} | Limit: {detail}",
        path=request.url.path,
        ip=client_ip,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=429,
        content={
            "error_code": "TOO_MANY_REQUESTS",
            "message": "Перевищено допустимий ліміт запитів. Будь ласка, зачекайте перед повторною спробою.",
            "details": {"limit": exc.detail},
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Обробник помилок валідації Pydantic v2 із маскуванням паролів та секретів у логах та відповідях."""
    raw_errors: list[dict[str, Any]] = jsonable_encoder(exc.errors())
    sanitized_errors = _sanitize_pydantic_errors(raw_errors)

    logger.warning(
        "422 Validation Error | Path: {path} | Errors: {errors}",
        path=request.url.path,
        errors=sanitized_errors,
    )
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Помилка валідації вхідних даних.",
            "details": {"errors": sanitized_errors},
        },
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Обробник помилок цілісності даних реляційної бази даних PostgreSQL."""
    orig = exc.orig
    pgcode = getattr(orig, "sqlstate", getattr(orig, "pgcode", None))
    logger.warning(
        "IntegrityError ({code}) на {path}: {msg}",
        code=pgcode,
        path=request.url.path,
        msg=str(orig or exc),
    )

    if pgcode == "23505":
        status_code = 409
        error_code = "UNIQUE_VIOLATION"
        message = "Порушення унікальності: запис із такими ключовими даними вже існує."
    elif pgcode == "23503":
        orig_msg = str(orig or exc).lower()
        if request.method == "DELETE" or "is still referenced from" in orig_msg:
            status_code = 409
            error_code = "RESOURCE_LOCKED"
            message = "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."
        else:
            status_code = 400
            error_code = "FOREIGN_KEY_VIOLATION"
            message = "Помилка зв'язку даних: вказаний пов'язаний об'єкт не знайдено."
    elif pgcode == "23502":
        status_code = 400
        error_code = "NOT_NULL_VIOLATION"
        message = "Помилка цілісності: обов'язкове поле не може бути порожнім."
    elif pgcode == "23514":
        status_code = 400
        error_code = "CHECK_VIOLATION"
        message = "Порушення бізнес-правил перевірки констрейнту бази даних."
    else:
        status_code = 400
        error_code = "INTEGRITY_ERROR"
        message = "Помилка цілісності даних при збереженні в базу."

    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "details": {"pgcode": pgcode},
        },
    )


async def stale_data_error_handler(request: Request, exc: StaleDataError) -> JSONResponse:
    """Обробник конфліктів оптимістичного блокування SQLAlchemy (OCC)."""
    logger.warning(
        "OCC Conflict (StaleDataError) на {path}: {err}",
        path=request.url.path,
        err=str(exc),
    )
    return JSONResponse(
        status_code=409,
        content={
            "error_code": "OPTIMISTIC_LOCK_CONFLICT",
            "message": "Дані було змінено іншим користувачем. Будь ласка, оновіть сторінку перед внесенням змін.",
            "details": {"reason": "concurrent_modification"},
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обробник непередбачених помилок 500 з обов'язковим логуванням через Loguru."""
    logger.opt(exception=exc).error(
        "Неперехоплена системна помилка 500 на {method} {path}: {err}",
        method=request.method,
        path=request.url.path,
        err=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "Сталася неочікувана внутрішня помилка сервера.",
            "details": {},
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Реєстрація всіх глобальних обробників винятків додатку."""
    app.add_exception_handler(AppException, cast(Any, app_exception_handler))
    app.add_exception_handler(StarletteHTTPException, cast(Any, http_exception_handler))
    app.add_exception_handler(RateLimitExceeded, cast(Any, rate_limit_exceeded_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(IntegrityError, cast(Any, integrity_error_handler))
    app.add_exception_handler(StaleDataError, cast(Any, stale_data_error_handler))
    app.add_exception_handler(Exception, unhandled_exception_handler)
