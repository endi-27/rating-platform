from uuid import UUID

from src.core import (
    IEventBus,
    IPasswordHasher,
    IUnitOfWork,
    default_password_hasher,
    logger,
)
from src.modules.users.application.common import resolve_permissions
from src.modules.users.application.dto import CreateUserDTO
from src.modules.users.domain import (
    IPermissionRepository,
    IRoleRepository,
    IUserRepository,
    RoleNotFoundError,
    User,
    UserAlreadyExistsError,
    UserCreatedEvent,
)


class RegisterUserUseCase:
    """Use Case створення (реєстрації) нового користувача."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        role_repo: IRoleRepository,
        permission_repo: IPermissionRepository,
        event_bus: IEventBus,
        password_hasher: IPasswordHasher = default_password_hasher,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._permission_repo = permission_repo
        self._event_bus = event_bus
        self._password_hasher = password_hasher

    async def execute(self, dto: CreateUserDTO) -> UUID:
        async with self._uow:
            # Перевірка унікальності логіна
            if await self._user_repo.exists_by_username(dto.username):
                logger.warning("Спроба створення дубліката користувача з username={username}", username=dto.username)
                raise UserAlreadyExistsError(f"Користувач з логіном '{dto.username}' вже існує.")

            # Перевірка наявності ролі (валідація активності та системних обмежень делегується домену User.register)
            role = await self._role_repo.get_by_id(dto.role_id)
            if not role:
                logger.warning("Призначення неіснуючої ролі ID: {role_id}", role_id=str(dto.role_id))
                raise RoleNotFoundError("Призначену роль не знайдено.")

            # Атомарна валідація та завантаження персональних дозволів
            custom_perms = await resolve_permissions(self._permission_repo, dto.custom_permission_ids)

            # Хешування пароля та створення агрегата через доменну фабрику
            pwd_hash = self._password_hasher.hash(dto.password)
            user = User.register(
                username=dto.username,
                name=dto.name,
                password_hash=pwd_hash,
                role=role,
                custom_permissions=custom_perms,
            )

            await self._user_repo.save(user)
            await self._uow.commit()

            logger.info(
                "Користувача успішно зареєстровано: ID {user_id}, username={username}",
                user_id=str(user.id),
                username=user.username,
            )

        await self._event_bus.publish(
            UserCreatedEvent(
                entity_id=user.id,
                username=user.username,
                role_id=user.role_id,
            )
        )

        return user.id
