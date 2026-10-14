from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.dto import RestoreUserDTO
from src.modules.users.domain import (
    IUserRepository,
    UserNotFoundError,
    UserRestoredEvent,
    UserSecurityDomainService,
)
from src.utils import check_optimistic_lock


class RestoreUserUseCase:
    """Use Case відновлення користувача з неактивного стану (Restore)."""

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
        dto: RestoreUserDTO,
        actor: CurrentUser,
    ) -> None:
        # Доменний сервіс: заборона самовідновлення
        UserSecurityDomainService.ensure_not_self_action(
            actor_id=actor.id,
            target_id=user_id,
            action_title="відновити",
        )

        async with self._uow:
            user = await self._user_repo.get_by_id(user_id)
            if not user:
                logger.warning("Спроба відновлення неіснуючого користувача ID: {user_id}", user_id=str(user_id))
                raise UserNotFoundError("Користувача не знайдено.")

            check_optimistic_lock(user.version, dto.version, "користувача")

            user.restore()

            await self._user_repo.save(user)
            await self._uow.commit()

            logger.info("Користувача ID: {user_id} успішно відновлено", user_id=str(user.id))

        await self._event_bus.publish(
            UserRestoredEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
            )
        )
