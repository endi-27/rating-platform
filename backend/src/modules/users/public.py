import contextlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import CurrentUser, get_db_session, get_redis_client, settings
from src.modules.users.application.dto import UserCredentialsDTO
from src.modules.users.domain import IUserRepository
from src.modules.users.infrastructure.repositories.user_repository import SqlAlchemyUserRepository
from src.modules.users.queries.dto import (
    UserResponseDTO,
    UserShortDTO,
)
from src.modules.users.queries.user_queries import UserQueryService


class UsersPublicGateway:
    """
    Публічний шлюз модуля users для синхронної міжмодульної взаємодії.
    Єдиний фасад модуля для звернення з інших доменних модулів (auth тощо).
    Реалізує IUserAuthGateway для модуля Auth.
    """

    def __init__(
        self,
        query_service: UserQueryService,
        user_repo: IUserRepository | None = None,
    ) -> None:
        self._query_service = query_service
        self._user_repo = user_repo

    # --- 1. Read-Side запити для доменних модулів платформи ---

    async def get_user_by_id(self, user_id: UUID) -> UserResponseDTO | None:
        """Отримання повної інформації про профіль користувача за id (без хешу пароля)."""
        return await self._query_service.get_by_id(user_id)

    async def get_user_short(self, user_id: UUID) -> UserShortDTO | None:
        """Отримання коротких даних користувача (id, username, name) для селектів та таблиць."""
        res = await self._query_service.get_by_id(user_id)
        if res:
            return UserShortDTO(id=res.id, username=res.username, name=res.name)
        return None

    async def user_exists(self, user_id: UUID) -> bool:
        """Перевірка чи існує активний користувач з таким id."""
        res = await self._query_service.get_by_id(user_id)
        return res is not None and res.deleted_at is None

    async def get_user_permissions(self, user_id: UUID) -> set[str]:
        """Отримання фактичних дозволів користувача."""
        res = await self._query_service.get_detail_by_id(user_id)
        if res:
            return res.effective_permissions
        return set()

    # --- 2. Реалізація контракту IUserAuthGateway для модуля Auth ---

    async def get_credentials_by_username(self, username: str) -> UserCredentialsDTO | None:
        """Отримання облікових даних (credentials) користувача за логіном для автентифікації."""
        if not self._user_repo:
            return None
        user = await self._user_repo.get_by_username(username)
        if not user:
            return None
        role_code = user.role.code if user.role else ""
        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=role_code,
            is_active=user.is_active,
        )

    async def get_credentials_by_id(self, user_id: UUID) -> UserCredentialsDTO | None:
        """Отримання облікових даних (credentials) користувача за ID для ротації токенів."""
        if not self._user_repo:
            return None
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            return None
        role_code = user.role.code if user.role else ""
        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=role_code,
            is_active=user.is_active,
        )

    async def get_cached_current_user(self, user_id: UUID) -> CurrentUser | None:
        """Отримання кешованого профілю поточного користувача для валідації токена."""
        return await self._query_service.get_cached_current_user(user_id)


def get_users_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UsersPublicGateway:
    redis: Redis[Any] | None = None
    with contextlib.suppress(Exception):
        redis = get_redis_client(settings.redis.databases.cache)
    query_service = UserQueryService(session=session, redis=redis)
    user_repo = SqlAlchemyUserRepository(session=session)
    return UsersPublicGateway(query_service=query_service, user_repo=user_repo)


__all__ = [
    "UsersPublicGateway",
    "get_users_public_gateway",
]
