from uuid import UUID

from src.core import (
    CurrentUser,
    IEventBus,
    IUnitOfWork,
    logger,
)
from src.modules.users.domain import (
    IRoleRepository,
    RoleDeletedEvent,
    RoleNotFoundError,
    SuperAdminProtectionError,
    UserSecurityDomainService,
)


class HardDeleteRoleUseCase:
    """Use Case остаточного фізичного видалення ролі (HTTP DELETE)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        role_repo: IRoleRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._role_repo = role_repo
        self._event_bus = event_bus

    async def execute(self, role_id: UUID, actor: CurrentUser) -> None:
        async with self._uow:
            # Заборона користувачам фізично видаляти власну призначену роль
            UserSecurityDomainService.ensure_not_self_role(
                actor_role_id=actor.role_id,
                target_role_id=role_id,
                action_title="видалити",
            )

            role = await self._role_repo.get_by_id(role_id)
            if not role:
                logger.warning("Спроба видалення неіснуючої ролі ID: {role_id}", role_id=str(role_id))
                raise RoleNotFoundError("Роль не знайдено.")

            if role.is_super_admin:
                raise SuperAdminProtectionError("Неможливо видалити системну роль super_admin.")

            code = role.code

            await self._role_repo.delete_by_id(role_id)
            await self._uow.commit()

            logger.info("Роль ID: {role_id} остаточно видалено (Hard Delete)", role_id=str(role_id))

        await self._event_bus.publish(
            RoleDeletedEvent(
                entity_id=role_id,
                code=code,
            )
        )
