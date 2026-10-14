import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.core import (
    AccountDeactivatedException,
    IEventBus,
    InvalidTokenException,
    IUnitOfWork,
    create_access_token,
    generate_opaque_token,
    logger,
    set_current_user_id,
    set_current_username,
    settings,
)
from src.modules.auth.application.dto import AuthResultDTO, RefreshTokenDTO
from src.modules.auth.domain import (
    IRefreshTokenRepository,
    IUserAuthGateway,
    SessionExpiredEvent,
    TokenCompromisedEvent,
    TokenRefreshFailedEvent,
    TokenRefreshFailureReason,
)


class RefreshTokenUseCase:
    """Use Case для ротації Refresh токена та оновлення Access токена."""

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

    async def execute(
        self,
        dto: RefreshTokenDTO,
        *,
        ip_address: str | None = None,
        user_id: UUID | None = None,
        username: str | None = None,
    ) -> AuthResultDTO:
        raw_hash = hashlib.sha256(dto.refresh_token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)

        async with self._uow:
            exist_token = await self._refresh_repo.get_by_token_hash(raw_hash)

            if not exist_token:
                logger.warning("Спроба оновлення токена: токен не знайдено в БД.")
                await self._event_bus.publish(
                    TokenRefreshFailedEvent(
                        entity_id=user_id,
                        username=username,
                        reason=TokenRefreshFailureReason.TOKEN_NOT_FOUND,
                        ip_address=ip_address,
                    )
                )
                raise InvalidTokenException("Refresh токен недійсний. Потрібна повторна автентифікація.")

            # Безпека (RFC 6819 Token Reuse Detection): повторне використання вже анульованого токена
            # свідчить про можливу компрометацію або перехоплення. Анулюємо ВСІ сесії користувача!
            if exist_token.is_revoked:
                target_user_id = exist_token.user_id
                logger.warning(
                    "Виявлено спробу повторного використання анульованого токена (Token Reuse)! "
                    "Можлива компрометація сесії користувача ID: {user_id}. Анулюємо всі сесії.",
                    user_id=str(target_user_id),
                )
                await self._refresh_repo.bulk_revoke_for_users({target_user_id})
                user_obj = await self._users_gateway.get_credentials_by_id(target_user_id)
                username_val = user_obj.username if user_obj else username

                set_current_user_id(user_id or target_user_id)
                set_current_username(username_val)

                await self._uow.commit()

                await self._event_bus.publish(
                    TokenCompromisedEvent(
                        entity_id=target_user_id,
                        username=username_val,
                        ip_address=ip_address,
                    )
                )
                raise InvalidTokenException("Виявлено спробу повторного використання токена. Усі сесії анульовано.")

            if not exist_token.is_valid(now):
                target_user_id = exist_token.user_id
                logger.warning(
                    "Спроба оновлення недійсного токена (expired={expired}, session_expired={sess_exp})",
                    expired=exist_token.is_expired(now),
                    sess_exp=exist_token.is_session_expired(now),
                )
                user_obj = await self._users_gateway.get_credentials_by_id(target_user_id)
                username_val = user_obj.username if user_obj else username

                set_current_user_id(user_id or target_user_id)
                set_current_username(username_val)

                exist_token.revoke()
                await self._refresh_repo.save(exist_token)
                await self._uow.commit()

                await self._event_bus.publish(
                    SessionExpiredEvent(
                        entity_id=target_user_id,
                        username=username_val,
                        ip_address=ip_address,
                    )
                )
                raise InvalidTokenException("Термін дії сесії вичерпано або токен недійсний.")

            user = await self._users_gateway.get_credentials_by_id(exist_token.user_id)
            if not user or not user.is_active:
                logger.warning(
                    "Оновлення токена відхилено: користувач неактивний або не існує (ID: {uid})",
                    uid=str(exist_token.user_id),
                )
                await self._event_bus.publish(
                    TokenRefreshFailedEvent(
                        entity_id=exist_token.user_id,
                        username=user.username if user else username,
                        reason=TokenRefreshFailureReason.ACCOUNT_DEACTIVATED,
                        ip_address=ip_address,
                    )
                )
                raise AccountDeactivatedException("Обліковий запис користувача деактивовано.")

            # Встановлюємо ідентичність користувача в асинхронний контекст запиту для аудиту нової пари токенів
            set_current_user_id(user.id)
            set_current_username(user.username)

            # Генеруємо нову пару токенів
            refresh_days = (
                settings.auth.refresh_token_remember_me_expire_days
                if exist_token.is_remember_me
                else settings.auth.refresh_token_expire_days
            )
            refresh_expires = now + timedelta(days=refresh_days)

            new_access_token = create_access_token(
                data={"sub": str(user.id), "username": user.username, "role": user.role_code},
                expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
            )

            new_plain_refresh = generate_opaque_token(32)
            new_token_hash = hashlib.sha256(new_plain_refresh.encode("utf-8")).hexdigest()

            # Доменна ротація: анулює поточний токен і створює новий з гарантованим збереженням інваріантів
            new_refresh_entity = exist_token.rotate(
                new_token_hash=new_token_hash,
                new_expires_at=refresh_expires,
                rotated_at=now,
            )
            await self._refresh_repo.save(exist_token)
            await self._refresh_repo.create(new_refresh_entity)
            await self._uow.commit()

            logger.info("Успішна ротація токенів для користувача ID: {user_id}", user_id=str(user.id))
            return AuthResultDTO(
                access_token=new_access_token,
                refresh_token=new_plain_refresh,
                is_remember_me=exist_token.is_remember_me,
                user_id=user.id,
            )
