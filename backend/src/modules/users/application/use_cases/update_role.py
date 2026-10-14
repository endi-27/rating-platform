from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.common import resolve_permissions
from src.modules.users.application.dto import UpdateRoleDTO
from src.modules.users.domain import (
    IPermissionRepository,
    IRoleRepository,
    RoleNotFoundError,
    RoleUpdatedEvent,
    UserSecurityDomainService,
)
from src.utils import check_optimistic_lock


class UpdateRoleUseCase:
    """Use Case повного оновлення ролі (Full PUT)."""

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

    async def execute(
        self,
        role_id: UUID,
        dto: UpdateRoleDTO,
        actor: CurrentUser,
    ) -> None:
        async with self._uow:
            # Заборона користувачам редагувати власну призначену роль
            UserSecurityDomainService.ensure_not_self_role(
                actor_role_id=actor.role_id,
                target_role_id=role_id,
                action_title="редагувати",
            )

            role = await self._role_repo.get_by_id(role_id)
            if not role:
                logger.warning("Спроба оновлення неіснуючої ролі ID: {role_id}", role_id=str(role_id))
                raise RoleNotFoundError("Роль не знайдено.")

            check_optimistic_lock(role.version, dto.version, "ролі")

            perms = await resolve_permissions(self._permission_repo, dto.permission_ids)

            # Внутрішній захист SuperAdmin інкапсульовано в методі агрегата update_details
            role.update_details(
                name=dto.name,
                description=dto.description,
                permissions=perms,
            )

            await self._role_repo.save(role)
            await self._uow.commit()

            logger.info("Роль ID: {role_id} успішно оновлено", role_id=str(role.id))

        await self._event_bus.publish(
            RoleUpdatedEvent(
                entity_id=role.id,
                code=role.code,
                name=role.name,
            )
        )
