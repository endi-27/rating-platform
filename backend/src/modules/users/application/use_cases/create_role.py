from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.users.application.common import resolve_permissions
from src.modules.users.application.dto import CreateRoleDTO
from src.modules.users.domain import (
    IPermissionRepository,
    IRoleRepository,
    Role,
    RoleAlreadyExistsError,
    RoleCreatedEvent,
)


class CreateRoleUseCase:
    """Use Case створення нової ролі користувачів."""

    def __init__(
        self,
        uow: IUnitOfWork,
        role_repo: IRoleRepository,
        permission_repo: IPermissionRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._role_repo = role_repo
        self._permission_repo = permission_repo
        self._event_bus = event_bus

    async def execute(self, dto: CreateRoleDTO) -> UUID:
        async with self._uow:
            perms = await resolve_permissions(self._permission_repo, dto.permission_ids)

            # Створення агрегата через фабрику з валідацією доменних інваріантів
            role = Role.create(
                code=dto.code,
                name=dto.name,
                description=dto.description,
                permissions=perms,
            )

            # Перевірка унікальності коду ролі в БД
            if await self._role_repo.exists_by_code(role.code):
                logger.warning("Спроба створення дубліката ролі з кодом {code}", code=role.code)
                raise RoleAlreadyExistsError(f"Роль з кодом '{role.code}' вже існує.")

            await self._role_repo.save(role)
            await self._uow.commit()

            logger.info("Роль успішно створено: ID {role_id}, code={code}", role_id=str(role.id), code=role.code)

        await self._event_bus.publish(
            RoleCreatedEvent(
                entity_id=role.id,
                code=role.code,
                name=role.name,
            )
        )

        return role.id
