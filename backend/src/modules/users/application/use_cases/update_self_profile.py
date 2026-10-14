from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.dto import UpdateSelfProfileDTO
from src.modules.users.domain import (
    IUserRepository,
    UserNotFoundError,
    UserUpdatedEvent,
)
from src.utils import check_optimistic_lock


class UpdateSelfProfileUseCase:
    """Use Case оновлення власного профілю поточним автентифікованим користувачем."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._event_bus = event_bus

    async def execute(self, actor: CurrentUser, dto: UpdateSelfProfileDTO) -> None:
        async with self._uow:
            user = await self._user_repo.get_by_id(actor.id)
            if not user or not user.is_active:
                logger.warning(
                    "Спроба оновлення профілю неактивного або неіснуючого користувача: {user_id}",
                    user_id=str(actor.id),
                )
                raise UserNotFoundError("Користувача не знайдено.")

            check_optimistic_lock(user.version, dto.version, "профілю")

            user.update_profile(name=dto.name)

            await self._user_repo.save(user)
            await self._uow.commit()

            logger.info("Власний профіль користувача ID: {user_id} успішно оновлено", user_id=str(user.id))

        await self._event_bus.publish(
            UserUpdatedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
                role_id=user.role_id,
            )
        )
