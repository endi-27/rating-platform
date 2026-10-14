from uuid import UUID

from src.core import CurrentUser, IEventBus, IUnitOfWork, logger
from src.modules.users.application.common import resolve_permissions
from src.modules.users.application.dto import UpdateUserDTO
from src.modules.users.domain import (
    IAuthSessionGateway,
    IPermissionRepository,
    IRoleRepository,
    IUserRepository,
    RoleNotFoundError,
    SuperAdminProtectionError,
    UserAlreadyExistsError,
    UserCredentialsChangedEvent,
    UserNotFoundError,
    UserSecurityDomainService,
    UserUpdatedEvent,
)
from src.utils import check_optimistic_lock


class UpdateUserUseCase:
    """Use Case повного оновлення профілю користувача (Full PUT)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        user_repo: IUserRepository,
        role_repo: IRoleRepository,
        permission_repo: IPermissionRepository,
        event_bus: IEventBus,
        auth_gateway: IAuthSessionGateway,
    ) -> None:
        self._uow = uow
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._permission_repo = permission_repo
        self._event_bus = event_bus
        self._auth_gateway = auth_gateway

    async def execute(
        self,
        user_id: UUID,
        dto: UpdateUserDTO,
        actor: CurrentUser,
    ) -> None:
        async with self._uow:
            # Адміністративний маршрут заборонено застосовувати до самого себе
            UserSecurityDomainService.ensure_not_self_action(
                actor_id=actor.id,
                target_id=user_id,
                action_title="редагувати",
            )

            user = await self._user_repo.get_by_id(user_id)
            if not user:
                logger.warning("Спроба оновлення неіснуючого користувача ID: {user_id}", user_id=str(user_id))
                raise UserNotFoundError("Користувача не знайдено.")

            # Перевірка версії (OCC) через спільний хелпер
            check_optimistic_lock(user.version, dto.version, "користувача")

            # Абсолютний захист SuperAdmin: редагування заборонено системними правилами
            if user.is_super_admin:
                logger.warning(
                    "Спроба оновлення SuperAdmin через адміністративний маршрут: {user_id}",
                    user_id=str(user_id),
                )
                raise SuperAdminProtectionError("Редагування облікового запису SuperAdmin заборонено.")

            # Перевірка унікальності нового логіна при його зміні
            username_changed = dto.username.lower() != user.username.lower()
            if username_changed and await self._user_repo.exists_by_username(dto.username, exclude_user_id=user.id):
                logger.warning(
                    "Спроба оновлення логіна на вже зайнятий: username={username}",
                    username=dto.username,
                )
                raise UserAlreadyExistsError(f"Користувач з логіном '{dto.username}' вже існує.")

            # Завантаження призначеної ролі при її зміні або відсутності в агрегаті
            role_changed = user.role_id != dto.role_id
            if role_changed or user.role is None:
                target_role = await self._role_repo.get_by_id(dto.role_id)
                if not target_role:
                    raise RoleNotFoundError("Призначену роль не знайдено.")
            else:
                target_role = user.role

            # Атомарна валідація оновлених персональних дозволів
            custom_perms = await resolve_permissions(self._permission_repo, dto.custom_permission_ids)
            perms_changed = {p.id for p in custom_perms} != user.custom_permission_ids

            user.update_profile(
                name=dto.name,
                username=dto.username,
                role=target_role,
                custom_permissions=custom_perms,
            )

            await self._user_repo.save(user)

            # При зміні облікових даних (логін, роль, персональні права) анулюємо сесії цільового користувача
            credentials_changed = username_changed or role_changed or perms_changed
            if credentials_changed:
                await self._auth_gateway.revoke_all_user_sessions(
                    user.id,
                    actor_id=actor.id,
                    actor_username=actor.username,
                    external_uow=self._uow,
                )

            await self._uow.commit()

            logger.info("Профіль користувача ID: {user_id} успішно оновлено", user_id=str(user.id))

        await self._event_bus.publish(
            UserUpdatedEvent(
                entity_id=user.id,
                actor_id=actor.id,
                username=user.username,
                role_id=user.role_id,
            )
        )
        if credentials_changed:
            await self._event_bus.publish(
                UserCredentialsChangedEvent(
                    entity_id=user.id,
                    actor_id=actor.id,
                    username=user.username,
                    role_id=user.role_id,
                )
            )
