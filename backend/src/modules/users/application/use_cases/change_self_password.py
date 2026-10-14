from src.core import (
    CurrentUser,
    IEventBus,
    InvalidCredentialsException,
    IPasswordHasher,
    IUnitOfWork,
    default_password_hasher,
    logger,
)
from src.modules.users.application.dto import ChangeSelfPasswordDTO
from src.modules.users.domain import (
    IAuthSessionGateway,
    IUserRepository,
    UserNotFoundError,
    UserPasswordChangedEvent,
)


class ChangeSelfPasswordUseCase:
    """Use Case зміни власного пароля автентифікованим користувачем."""

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

    async def execute(self, actor: CurrentUser, dto: ChangeSelfPasswordDTO) -> None:
        async with self._uow:
            user = await self._user_repo.get_by_id(actor.id)
            if not user or not user.is_active:
                logger.warning(
                    "Спроба зміни пароля для неактивного або неіснуючого користувача: {user_id}",
                    user_id=str(actor.id),
                )
                raise UserNotFoundError("Користувача не знайдено.")

            if not user.verify_password(dto.old_password, self._password_hasher):
                logger.warning(
                    "Невірний старий пароль при зміні пароля для користувача: {user_id}",
                    user_id=str(actor.id),
                )
                raise InvalidCredentialsException("Поточний пароль вказано невірно.")

            new_hash = self._password_hasher.hash(dto.new_password)
            user.change_password(new_hash)

            await self._user_repo.save(user)
            await self._auth_gateway.revoke_all_user_sessions(
                user.id,
                actor_id=actor.id,
                actor_username=actor.username,
                external_uow=self._uow,
            )
            await self._uow.commit()

            logger.info("Пароль успішно змінено для користувача ID: {user_id}", user_id=str(user.id))

        await self._event_bus.publish(
            UserPasswordChangedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
            )
        )
