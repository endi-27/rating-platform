import hashlib
from uuid import UUID

from src.core import (
    IEventBus,
    IUnitOfWork,
    logger,
    set_current_user_id,
    set_current_username,
)
from src.modules.auth.application.dto import LogoutDTO
from src.modules.auth.domain import IRefreshTokenRepository, UserLoggedOutEvent


class LogoutUseCase:
    """Use Case для виходу користувача з анулюванням сесійного refresh токена."""

    def __init__(
        self,
        uow: IUnitOfWork,
        refresh_repo: IRefreshTokenRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._refresh_repo = refresh_repo
        self._event_bus = event_bus

    async def execute(
        self,
        dto: LogoutDTO,
        *,
        ip_address: str | None = None,
        user_id: UUID | None = None,
        username: str | None = None,
    ) -> None:
        target_user_id: UUID | None = user_id
        target_session_id: UUID | None = None

        if dto.refresh_token:
            raw_hash = hashlib.sha256(dto.refresh_token.encode("utf-8")).hexdigest()

            async with self._uow:
                token_obj = await self._refresh_repo.get_by_token_hash(raw_hash)
                if token_obj:
                    target_user_id = token_obj.user_id
                    target_session_id = token_obj.id
                    set_current_user_id(user_id or target_user_id)
                    set_current_username(username)
                    token_obj.revoke()
                    await self._refresh_repo.save(token_obj)
                    await self._uow.commit()
                    logger.info(
                        "Сесію користувача ID: {user_id} успішно завершено (Logout).",
                        user_id=str(token_obj.user_id),
                    )
                else:
                    logger.info("Спроба виходу з неіснуючим або вже анульованим токеном.")

        if target_user_id is not None:
            await self._event_bus.publish(
                UserLoggedOutEvent(
                    entity_id=target_user_id,
                    session_id=target_session_id,
                    username=username,
                    ip_address=ip_address,
                )
            )
