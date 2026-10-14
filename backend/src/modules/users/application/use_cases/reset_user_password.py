from uuid import UUID

from src.core import (
    CurrentUser,
    IEventBus,
    InactiveEntityError,
    IPasswordHasher,
    IUnitOfWork,
    default_password_hasher,
    logger,
)
from src.modules.users.application.dto import ResetUserPasswordDTO
from src.modules.users.domain import (
    IAuthSessionGateway,
    IUserRepository,
    SuperAdminProtectionError,
    UserNotFoundError,
    UserPasswordChangedEvent,
    UserSecurityDomainService,
)


class ResetUserPasswordUseCase:
    """Use Case примусового скидання пароля користувача адміністратором."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        auth_gateway: IAuthSessionGateway,
        event_bus: IEventBus,
        password_hasher: IPasswordHasher = default_password_hasher,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._auth_gateway = auth_gateway
        self._event_bus = event_bus
        self._password_hasher = password_hasher

    async def execute(
        self,
        user_id: UUID,
        dto: ResetUserPasswordDTO,
        actor: CurrentUser,
    ) -> None:
        async with self._uow:
            # Заборона скидання власного пароля через адміністративний ендпоінт
            UserSecurityDomainService.ensure_not_self_action(
                actor_id=actor.id,
                target_id=user_id,
                action_title="скидати пароль для",
            )

            target_user = await self._user_repo.get_by_id(user_id)
            if not target_user:
                logger.warning(
                    "Спроба скидання пароля неіснуючого користувача ID: {user_id}",
                    user_id=str(user_id),
                )
                raise UserNotFoundError("Користувача не знайдено.")

            if not target_user.is_active:
                logger.warning(
                    "Спроба скидання пароля неактивного користувача ID: {user_id}",
                    user_id=str(user_id),
                )
                raise InactiveEntityError(
                    "Неможливо скинути пароль для деактивованого користувача. Спочатку відновіть його."
                )

            # Абсолютний захист SuperAdmin: скидання пароля заборонено системними правилами
            if target_user.is_super_admin:
                logger.warning("Спроба скидання пароля SuperAdmin ID: {user_id}", user_id=str(user_id))
                raise SuperAdminProtectionError("Скидання пароля для SuperAdmin заборонено системними правилами.")

            new_hash = self._password_hasher.hash(dto.new_password)
            target_user.change_password(new_hash)

            await self._user_repo.save(target_user)
            await self._auth_gateway.revoke_all_user_sessions(
                target_user.id,
                actor_id=actor.id,
                actor_username=actor.username,
                external_uow=self._uow,
            )
            await self._uow.commit()

            logger.info("Пароль користувача ID: {user_id} успішно скинуто адміністратором", user_id=str(target_user.id))

        await self._event_bus.publish(
            UserPasswordChangedEvent(
                entity_id=target_user.id,
                actor_id=actor.id,
                username=target_user.username,
            )
        )
