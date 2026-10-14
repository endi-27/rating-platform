from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.dto import SoftDeleteRoleDTO
from src.modules.users.domain import (
    IRoleRepository,
    RoleDeactivatedEvent,
    RoleNotFoundError,
    UserSecurityDomainService,
)
from src.utils import check_optimistic_lock


class SoftDeleteRoleUseCase:
    """Use Case деактивації (м'якого видалення) ролі."""

    def __init__(
        self,
        uow: IUnitOfWork,
        role_repo: IRoleRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._role_repo = role_repo
        self._event_bus = event_bus

    async def execute(
        self,
        role_id: UUID,
        dto: SoftDeleteRoleDTO,
        actor: CurrentUser,
    ) -> None:
        async with self._uow:
            # Заборона користувачам деактивувати власну призначену роль
            UserSecurityDomainService.ensure_not_self_role(
                actor_role_id=actor.role_id,
                target_role_id=role_id,
                action_title="деактивувати",
            )

            role = await self._role_repo.get_by_id(role_id)
            if not role:
                logger.warning("Спроба деактивації неіснуючої ролі ID: {role_id}", role_id=str(role_id))
                raise RoleNotFoundError("Роль не знайдено.")

            check_optimistic_lock(role.version, dto.version, "ролі")

            # Внутрішній захист SuperAdmin інкапсульовано в методі агрегата soft_delete
            role.soft_delete()

            await self._role_repo.save(role)
            await self._uow.commit()

            logger.info("Роль ID: {role_id} успішно деактивовано (Soft Delete)", role_id=str(role.id))

        await self._event_bus.publish(
            RoleDeactivatedEvent(
                entity_id=role.id,
                code=role.code,
            )
        )
