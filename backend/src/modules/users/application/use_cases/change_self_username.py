from src.core import (
    CurrentUser,
    IEventBus,
    InvalidCredentialsException,
    IPasswordHasher,
    IUnitOfWork,
    default_password_hasher,
    logger,
)
from src.modules.users.application.dto import ChangeSelfUsernameDTO
from src.modules.users.domain import (
    IAuthSessionGateway,
    IUserRepository,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserUpdatedEvent,
    UserUsernameChangedEvent,
)
from src.utils import check_optimistic_lock


class ChangeSelfUsernameUseCase:
    """Use Case зміни власного логіна автентифікованим користувачем з підтвердженням паролем."""

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

    async def execute(self, actor: CurrentUser, dto: ChangeSelfUsernameDTO) -> None:
        async with self._uow:
            user = await self._user_repo.get_by_id(actor.id)
            if not user or not user.is_active:
                logger.warning(
                    "Спроба зміни логіна для неактивного або неіснуючого користувача: {user_id}",
                    user_id=str(actor.id),
                )
                raise UserNotFoundError("Користувача не знайдено.")

            check_optimistic_lock(user.version, dto.version, "користувача")

            if not user.verify_password(dto.current_password, self._password_hasher):
                logger.warning(
                    "Невірний пароль при зміні логіна для користувача: {user_id}",
                    user_id=str(actor.id),
                )
                raise InvalidCredentialsException("Невірний пароль для підтвердження зміни логіна.")

            if dto.new_username.lower() != user.username.lower() and await self._user_repo.exists_by_username(
                dto.new_username, exclude_user_id=user.id
            ):
                logger.warning(
                    "Спроба зміни логіна на вже зайнятий: username={username}",
                    username=dto.new_username,
                )
                raise UserAlreadyExistsError(f"Користувач з логіном '{dto.new_username}' вже існує.")

            old_username = user.username
            user.change_username(dto.new_username)

            await self._user_repo.save(user)
            await self._auth_gateway.revoke_all_user_sessions(
                user.id,
                actor_id=actor.id,
                actor_username=actor.username,
                external_uow=self._uow,
            )
            await self._uow.commit()

            logger.info("Логін успішно змінено для користувача ID: {user_id}", user_id=str(user.id))

        await self._event_bus.publish(
            UserUpdatedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
                role_id=user.role_id,
            ),
            UserUsernameChangedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                old_username=old_username,
                new_username=user.username,
            ),
        )
