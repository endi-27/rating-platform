from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.domain import (
    IUserRepository,
    SuperAdminProtectionError,
    UserDeletedEvent,
    UserNotFoundError,
    UserSecurityDomainService,
)


class HardDeleteUserUseCase:
    """Use Case фізичного остаточного видалення користувача (HTTP DELETE)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._event_bus = event_bus

    async def execute(
        self,
        user_id: UUID,
        actor: CurrentUser,
    ) -> None:
        # Доменний сервіс: заборона самовидалення
        UserSecurityDomainService.ensure_not_self_action(
            actor_id=actor.id,
            target_id=user_id,
            action_title="видалити",
        )

        async with self._uow:
            user = await self._user_repo.get_by_id(user_id)
            if not user:
                logger.warning("Спроба видалення неіснуючого користувача ID: {user_id}", user_id=str(user_id))
                raise UserNotFoundError("Користувача не знайдено.")

            if user.is_super_admin:
                logger.warning("Спроба видалення SuperAdmin ID: {user_id}", user_id=str(user_id))
                raise SuperAdminProtectionError(
                    "Видалення облікового запису SuperAdmin заборонено системними правилами."
                )

            username = user.username

            # Фізичне видалення користувача (refresh_tokens видаляються каскадно на рівні БД)
            await self._user_repo.delete_by_id(user_id)
            await self._uow.commit()

            logger.info("Користувача ID: {user_id} остаточно видалено (Hard Delete)", user_id=str(user_id))

        await self._event_bus.publish(
            UserDeletedEvent(
                entity_id=user_id,
                actor_id=actor.id,
                username=username,
            )
        )
