import contextlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import (
    CurrentUser,
    IEventBus,
    IPasswordHasher,
    IUnitOfWork,
    SystemRole,
    UserAlreadyExistsException,
    default_password_hasher,
    get_db_session,
    get_redis_client,
    settings,
)
from src.core.events import get_event_bus
from src.modules.users.application.dto import UserCredentialsDTO
from src.modules.users.domain import (
    IRoleRepository,
    IUserRepository,
    RoleNotFoundError,
    User,
    UserCreatedEvent,
)
from src.modules.users.infrastructure.repositories import (
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRepository,
)
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
        role_repo: IRoleRepository | None = None,
        event_bus: IEventBus | None = None,
        password_hasher: IPasswordHasher = default_password_hasher,
    ) -> None:
        self._query_service = query_service
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._event_bus = event_bus
        self._password_hasher = password_hasher

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

    async def register_public_user(
        self,
        username: str,
        name: str,
        password: str,
        *,
        external_uow: IUnitOfWork | None = None,
    ) -> UserCredentialsDTO:
        """
        Створення нового користувача з роллю за замовчуванням (user).
        УВАГА: Коміт транзакції виконує ТІЛЬКИ кореневий Use Case (через external_uow).
        """
        if not self._user_repo or not self._role_repo:
            raise RuntimeError("Репозиторії користувачів або ролей не ініціалізовано.")

        # 1. Перевірка зайнятості логіна
        if await self._user_repo.exists_by_username(username):
            raise UserAlreadyExistsException(f"Користувач з логіном '{username}' вже існує.")

        # 2. Отримання базової системної ролі user
        role = await self._role_repo.get_by_code(SystemRole.USER.value)
        if not role:
            raise RoleNotFoundError("Системну роль 'user' не знайдено.")

        # 3. Створення користувача через доменну фабрику
        pwd_hash = self._password_hasher.hash(password)
        user = User.register(
            username=username,
            name=name,
            password_hash=pwd_hash,
            role=role,
            custom_permissions=[],
        )

        await self._user_repo.save(user)

        # 4. Публікація доменної події
        if self._event_bus:
            await self._event_bus.publish(
                UserCreatedEvent(
                    entity_id=user.id,
                    username=user.username,
                    role_id=user.role_id,
                )
            )

        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=role.code,
            is_active=user.is_active,
        )


def get_users_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)] | None = None,
) -> UsersPublicGateway:
    redis: Redis[Any] | None = None
    with contextlib.suppress(Exception):
        redis = get_redis_client(settings.redis.databases.cache)
    query_service = UserQueryService(session=session, redis=redis)
    user_repo = SqlAlchemyUserRepository(session=session)
    role_repo = SqlAlchemyRoleRepository(session=session)
    if event_bus is None:
        with contextlib.suppress(Exception):
            event_bus = get_event_bus()
    return UsersPublicGateway(
        query_service=query_service,
        user_repo=user_repo,
        role_repo=role_repo,
        event_bus=event_bus,
    )


__all__ = [
    "UsersPublicGateway",
    "get_users_public_gateway",
]
