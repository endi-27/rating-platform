from typing import Any

from fastapi import Request, Response

from src.core import settings


def is_secure_request(request: Request) -> bool:
    """Визначає, чи є запит захищеним (HTTPS або production/staging)."""
    return request.url.scheme == "https" or settings.environment.lower() not in ("local", "test")


def set_access_cookie(
    response: Response,
    token: str,
    is_remember_me: bool,
    secure: bool = False,
) -> None:
    """Встановлює cookie access_token."""
    kwargs: dict[str, Any] = {
        "key": "access_token",
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
    }
    if is_remember_me:
        kwargs["max_age"] = settings.auth.access_token_expire_minutes * 60
    response.set_cookie(**kwargs)


def set_refresh_cookie(
    response: Response,
    token: str,
    is_remember_me: bool,
    secure: bool = False,
) -> None:
    """Встановлює cookie refresh_token."""
    kwargs: dict[str, Any] = {
        "key": "refresh_token",
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": f"{settings.api.v1_prefix}/auth",
    }
    if is_remember_me:
        kwargs["max_age"] = settings.auth.refresh_token_remember_me_expire_days * 24 * 60 * 60
    response.set_cookie(**kwargs)


def clear_auth_cookies(response: Response, secure: bool = False) -> None:
    """Очищення cookies авторизації при виході."""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="lax",
        secure=secure,
        path=f"{settings.api.v1_prefix}/auth",
    )
