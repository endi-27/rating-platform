from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.dto import SoftDeleteUserDTO
from src.modules.users.domain import (
    IAuthSessionGateway,
    IUserRepository,
    UserDeactivatedEvent,
    UserNotFoundError,
    UserSecurityDomainService,
)
from src.utils import check_optimistic_lock


class SoftDeleteUserUseCase:
    """Use Case деактивації (м'якого видалення) користувача."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        event_bus: IEventBus,
        auth_gateway: IAuthSessionGateway | None = None,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._event_bus = event_bus
        self._auth_gateway = auth_gateway

    async def execute(
        self,
        user_id: UUID,
        dto: SoftDeleteUserDTO,
        actor: CurrentUser,
    ) -> None:
        # Доменний сервіс: заборона самодеактивації
        UserSecurityDomainService.ensure_not_self_action(
            actor_id=actor.id,
            target_id=user_id,
            action_title="деактивувати",
        )

        async with self._uow:
            user = await self._user_repo.get_by_id(user_id)
            if not user:
                logger.warning("Спроба деактивації неіснуючого користувача ID: {user_id}", user_id=str(user_id))
                raise UserNotFoundError("Користувача не знайдено.")

            check_optimistic_lock(user.version, dto.version, "користувача")

            # Внутрішній захист SuperAdmin інкапсульовано в методі агрегата soft_delete
            user.soft_delete()

            await self._user_repo.save(user)

            # Синхронне анулювання активних сесій через шлюз модуля Auth
            if self._auth_gateway:
                await self._auth_gateway.revoke_all_user_sessions(
                    user.id,
                    actor_id=actor.id,
                    actor_username=actor.username,
                    external_uow=self._uow,
                )

            await self._uow.commit()

            logger.info("Користувача ID: {user_id} успішно деактивовано (Soft Delete)", user_id=str(user.id))

        await self._event_bus.publish(
            UserDeactivatedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
            )
        )
