from __future__ import annotations

import enum
from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import get_uow
from src.core import (
    CurrentUser,
    ForbiddenException,
    IEventBus,
    IUnitOfWork,
    UnauthorizedException,
    decode_token,
    get_db_session,
    logger,
    set_current_user_id,
    set_current_username,
)
from src.core.events import get_event_bus
from src.modules.auth.application.use_cases import (
    AuthenticateUserUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
    RegisterPublicUserUseCase,
)
from src.modules.auth.domain import (
    IRefreshTokenRepository,
    IUserAuthGateway,
)
from src.modules.auth.infrastructure import (
    SqlAlchemyRefreshTokenRepository,
)
from src.modules.users import get_users_public_gateway


def get_users_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IUserAuthGateway:
    return get_users_public_gateway(session)


def get_refresh_token_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IRefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(session=session)


# --- DI Use Cases ---


def get_register_public_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    users_gateway: Annotated[IUserAuthGateway, Depends(get_users_gateway)],
    refresh_repo: Annotated[IRefreshTokenRepository, Depends(get_refresh_token_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> RegisterPublicUserUseCase:
    return RegisterPublicUserUseCase(
        uow=uow,
        users_gateway=users_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )


def get_authenticate_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    users_gateway: Annotated[IUserAuthGateway, Depends(get_users_gateway)],
    refresh_repo: Annotated[IRefreshTokenRepository, Depends(get_refresh_token_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        uow=uow,
        users_gateway=users_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )


def get_refresh_token_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    users_gateway: Annotated[IUserAuthGateway, Depends(get_users_gateway)],
    refresh_repo: Annotated[IRefreshTokenRepository, Depends(get_refresh_token_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        uow=uow,
        users_gateway=users_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )


def get_logout_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    refresh_repo: Annotated[IRefreshTokenRepository, Depends(get_refresh_token_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> LogoutUseCase:
    return LogoutUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )


# --- Security / Current User Dependencies ---


async def get_current_user_optional(
    request: Request,
    users_gateway: Annotated[IUserAuthGateway, Depends(get_users_gateway)],
) -> CurrentUser | None:
    """Витягує користувача з HttpOnly cookie або Bearer токена, повертає None якщо запит анонімний."""
    token = request.cookies.get("access_token")

    # Fallback на Authorization header (наприклад, для API тестування або Swagger)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    try:
        payload = decode_token(token)
    except jwt.PyJWTError as e:
        logger.debug("Помилка декодування access_token: {err}", err=str(e))
        return None

    if payload.get("type") != "access":
        logger.warning(
            "Відхилено токен невірного типу: {token_type}",
            token_type=payload.get("type"),
        )
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None

    user = await users_gateway.get_cached_current_user(user_id)
    if not user:
        return None

    request.state.user_id = user.id
    request.state.username = user.username
    set_current_user_id(user.id)
    set_current_username(user.username)
    return user


async def get_current_user(
    request: Request,
    current_user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> CurrentUser:
    """Вимагає обов'язкової автентифікації. Викидає HTTP 401 Unauthorized."""
    if not current_user:
        raise UnauthorizedException("Потрібна автентифікація для доступу до цього ресурсу.")
    request.state.user_id = current_user.id
    request.state.username = current_user.username
    set_current_user_id(current_user.id)
    set_current_username(current_user.username)
    return current_user


def require_permission(
    permission: str | enum.Enum,
) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """FastAPI Depends guard для перевірки наявності дозволу (RBAC)."""
    expected_code = permission.value if isinstance(permission, enum.Enum) else permission

    async def _permission_guard(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if expected_code not in current_user.effective_permissions:
            logger.warning(
                "Відхилено доступ для користувача {username} (ID: {uid}): відсутній дозвіл '{perm}'",
                username=current_user.username,
                uid=str(current_user.id),
                perm=expected_code,
            )
            raise ForbiddenException(f"Недостатньо прав: потрібен дозвіл '{expected_code}'.")
        return current_user

    _permission_guard.required_permission = expected_code  # type: ignore[attr-defined]
    return _permission_guard
