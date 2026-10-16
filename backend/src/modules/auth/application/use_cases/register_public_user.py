from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from src.core import (
    IEventBus,
    IUnitOfWork,
    create_access_token,
    generate_opaque_token,
    logger,
    set_current_user_id,
    set_current_username,
    settings,
)
from src.modules.auth.application.dto import AuthResultDTO, RegisterDTO
from src.modules.auth.domain import (
    IRefreshTokenRepository,
    IUserAuthGateway,
    RefreshToken,
    UserLoggedInEvent,
)


class RegisterPublicUserUseCase:
    """Use Case для публічної реєстрації нового користувача з автоматичною видачею сесії."""

    def __init__(
        self,
        uow: IUnitOfWork,
        users_gateway: IUserAuthGateway,
        refresh_repo: IRefreshTokenRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._users_gateway = users_gateway
        self._refresh_repo = refresh_repo
        self._event_bus = event_bus

    async def execute(self, dto: RegisterDTO, *, ip_address: str | None = None) -> AuthResultDTO:
        async with self._uow:
            user = await self._users_gateway.register_public_user(
                username=dto.username,
                name=dto.name,
                password=dto.password,
                external_uow=self._uow,
            )

            # Встановлюємо контекст користувача для аудиту та генерації токенів
            set_current_user_id(user.id)
            set_current_username(user.username)

            now = datetime.now(UTC)
            refresh_days = (
                settings.auth.refresh_token_remember_me_expire_days
                if dto.is_remember_me
                else settings.auth.refresh_token_expire_days
            )
            refresh_expires = now + timedelta(days=refresh_days)
            max_session_expiration = now + timedelta(days=settings.auth.max_session_expiration_days)

            # Генерація JWT access token
            access_token = create_access_token(
                data={"sub": str(user.id), "username": user.username, "role": user.role_code},
                expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
            )

            # Генерація opaque refresh token
            plain_refresh_token = generate_opaque_token(32)
            token_hash = hashlib.sha256(plain_refresh_token.encode("utf-8")).hexdigest()

            refresh_entity = RefreshToken.create(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=refresh_expires,
                max_session_expiration=max_session_expiration,
                is_remember_me=dto.is_remember_me,
                issued_at=now,
            )
            await self._refresh_repo.create(refresh_entity)
            await self._uow.commit()

        await self._event_bus.publish(
            UserLoggedInEvent(
                entity_id=user.id,
                actor_id=user.id,
                username=user.username,
                ip_address=ip_address,
            )
        )

        logger.info("Успішна публічна реєстрація користувача ID: {user_id}", user_id=str(user.id))
        return AuthResultDTO(
            access_token=access_token,
            refresh_token=plain_refresh_token,
            is_remember_me=dto.is_remember_me,
            user_id=user.id,
        )
