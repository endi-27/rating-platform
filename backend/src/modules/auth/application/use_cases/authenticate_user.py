import hashlib
from datetime import UTC, datetime, timedelta

from src.core import (
    AccountDeactivatedException,
    IEventBus,
    InvalidCredentialsException,
    IPasswordHasher,
    IUnitOfWork,
    create_access_token,
    default_password_hasher,
    generate_opaque_token,
    logger,
    set_current_user_id,
    set_current_username,
    settings,
)
from src.modules.auth.application.dto import AuthResultDTO, LoginDTO
from src.modules.auth.domain import (
    IRefreshTokenRepository,
    IUserAuthGateway,
    LoginFailedEvent,
    LoginFailureReason,
    RefreshToken,
    UserLoggedInEvent,
)

_DUMMY_PASSWORD_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQG8.RMG"


class AuthenticateUserUseCase:
    """Use Case для входу користувача за логіном та паролем з cookie-only сесією."""

    def __init__(
        self,
        uow: IUnitOfWork,
        users_gateway: IUserAuthGateway,
        refresh_repo: IRefreshTokenRepository,
        event_bus: IEventBus,
        password_hasher: IPasswordHasher = default_password_hasher,
    ) -> None:
        self._uow = uow
        self._users_gateway = users_gateway
        self._refresh_repo = refresh_repo
        self._event_bus = event_bus
        self._password_hasher = password_hasher

    async def execute(self, dto: LoginDTO, *, ip_address: str | None = None) -> AuthResultDTO:
        async with self._uow:
            user = await self._users_gateway.get_credentials_by_username(dto.username)

            # Перевірка пароля із захистом від timing attacks
            password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
            is_valid = self._password_hasher.verify(dto.password, password_hash)

            if not user or not is_valid:
                logger.warning("Спроба входу з невірними даними для користувача: {username}", username=dto.username)
                await self._event_bus.publish(
                    LoginFailedEvent(
                        username=dto.username,
                        reason=LoginFailureReason.INVALID_CREDENTIALS,
                        ip_address=ip_address,
                    )
                )
                raise InvalidCredentialsException("Неправильний логін або пароль.")

            if not user.is_active:
                logger.warning("Спроба входу в деактивований акаунт: {username}", username=dto.username)
                await self._event_bus.publish(
                    LoginFailedEvent(
                        entity_id=user.id,
                        username=dto.username,
                        reason=LoginFailureReason.ACCOUNT_DEACTIVATED,
                        ip_address=ip_address,
                    )
                )
                raise AccountDeactivatedException("Обліковий запис користувача деактивовано.")

            # Встановлюємо ідентичність користувача в асинхронний контекст запиту для коректного аудиту та подій
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

            # Генерація токенів
            access_token = create_access_token(
                data={"sub": str(user.id), "username": user.username, "role": user.role_code},
                expires_delta=timedelta(minutes=settings.auth.access_token_expire_minutes),
            )

            plain_refresh_token = generate_opaque_token(32)
            token_hash = hashlib.sha256(plain_refresh_token.encode("utf-8")).hexdigest()

            # Анулюємо старі сесії
            await self._refresh_repo.bulk_revoke_for_users({user.id})

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

            logger.info("Успішна автентифікація користувача ID: {user_id}", user_id=str(user.id))
            return AuthResultDTO(
                access_token=access_token,
                refresh_token=plain_refresh_token,
                is_remember_me=dto.is_remember_me,
                user_id=user.id,
            )
