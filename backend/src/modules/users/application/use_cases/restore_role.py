from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.dto import RestoreRoleDTO
from src.modules.users.domain import (
    IRoleRepository,
    RoleNotFoundError,
    RoleRestoredEvent,
    UserSecurityDomainService,
)
from src.utils import check_optimistic_lock


class RestoreRoleUseCase:
    """Use Case відновлення ролі з неактивного стану (Restore)."""

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
        dto: RestoreRoleDTO,
        actor: CurrentUser,
    ) -> None:
        async with self._uow:
            # Заборона користувачам відновлювати власну призначену роль
            UserSecurityDomainService.ensure_not_self_role(
                actor_role_id=actor.role_id,
                target_role_id=role_id,
                action_title="відновити",
            )

            role = await self._role_repo.get_by_id(role_id)
            if not role:
                logger.warning("Спроба відновлення неіснуючої ролі ID: {role_id}", role_id=str(role_id))
                raise RoleNotFoundError("Роль не знайдено.")

            check_optimistic_lock(role.version, dto.version, "ролі")

            role.restore()

            await self._role_repo.save(role)
            await self._uow.commit()

            logger.info("Роль ID: {role_id} успішно відновлено", role_id=str(role.id))

        await self._event_bus.publish(
            RoleRestoredEvent(
                entity_id=role.id,
                code=role.code,
            )
        )
