from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import get_read_db_session, get_uow
from src.core import IEventBus, IUnitOfWork, get_db_session, get_redis_client, settings
from src.core.events import get_event_bus
from src.modules.auth import get_auth_public_gateway
from src.modules.users.application.use_cases import (
    ChangeSelfPasswordUseCase,
    ChangeSelfUsernameUseCase,
    CreateRoleUseCase,
    HardDeleteRoleUseCase,
    HardDeleteUserUseCase,
    RegisterUserUseCase,
    ResetUserPasswordUseCase,
    RestoreRoleUseCase,
    RestoreUserUseCase,
    SoftDeleteRoleUseCase,
    SoftDeleteUserUseCase,
    UpdateRoleUseCase,
    UpdateSelfProfileUseCase,
    UpdateUserUseCase,
)
from src.modules.users.domain import (
    IAuthSessionGateway,
    IPermissionRepository,
    IRoleRepository,
    IUserRepository,
)
from src.modules.users.infrastructure.repositories import (
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRepository,
)
from src.modules.users.queries import (
    PermissionQueryService,
    RoleQueryService,
    UserQueryService,
)

# =====================================================================
# 1. Repositories (створюються рівно один раз на сесію запиту)
# =====================================================================


def get_permission_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IPermissionRepository:
    return SqlAlchemyPermissionRepository(session=session)


def get_role_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IRoleRepository:
    return SqlAlchemyRoleRepository(session=session)


def get_user_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IUserRepository:
    return SqlAlchemyUserRepository(session=session)


# =====================================================================
# 2. Query Services (Read-Side CQRS)
# =====================================================================


def get_permission_query_service(
    session: Annotated[AsyncSession, Depends(get_read_db_session)],
) -> PermissionQueryService:
    return PermissionQueryService(session=session)


def get_role_query_service(
    session: Annotated[AsyncSession, Depends(get_read_db_session)],
) -> RoleQueryService:
    return RoleQueryService(session=session)


def get_user_query_service(
    session: Annotated[AsyncSession, Depends(get_read_db_session)],
) -> UserQueryService:
    redis: Redis[Any] | None = None
    with contextlib.suppress(Exception):
        redis = get_redis_client(settings.redis.databases.cache)
    return UserQueryService(session=session, redis=redis)


# =====================================================================
# 3. Use Cases: Roles
# =====================================================================


def get_create_role_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> CreateRoleUseCase:
    return CreateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=permission_repo,
        event_bus=event_bus,
    )


def get_update_role_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> UpdateRoleUseCase:
    return UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=permission_repo,
        event_bus=event_bus,
    )


def get_soft_delete_role_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> SoftDeleteRoleUseCase:
    return SoftDeleteRoleUseCase(uow=uow, role_repo=role_repo, event_bus=event_bus)


def get_restore_role_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> RestoreRoleUseCase:
    return RestoreRoleUseCase(uow=uow, role_repo=role_repo, event_bus=event_bus)


def get_hard_delete_role_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> HardDeleteRoleUseCase:
    return HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )


# =====================================================================
# 4. Use Cases: Users
# =====================================================================


def get_register_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> RegisterUserUseCase:
    return RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=permission_repo,
        event_bus=event_bus,
    )


def get_update_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    role_repo: Annotated[IRoleRepository, Depends(get_role_repo)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
    auth_gateway: Annotated[IAuthSessionGateway, Depends(get_auth_public_gateway)],
) -> UpdateUserUseCase:
    return UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=permission_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )


def get_update_self_profile_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> UpdateSelfProfileUseCase:
    return UpdateSelfProfileUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )


def get_change_self_password_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    auth_gateway: Annotated[IAuthSessionGateway, Depends(get_auth_public_gateway)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> ChangeSelfPasswordUseCase:
    return ChangeSelfPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )


def get_change_self_username_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    auth_gateway: Annotated[IAuthSessionGateway, Depends(get_auth_public_gateway)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> ChangeSelfUsernameUseCase:
    return ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )


def get_reset_user_password_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    auth_gateway: Annotated[IAuthSessionGateway, Depends(get_auth_public_gateway)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> ResetUserPasswordUseCase:
    return ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )


def get_soft_delete_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
    auth_gateway: Annotated[IAuthSessionGateway, Depends(get_auth_public_gateway)],
) -> SoftDeleteUserUseCase:
    return SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )


def get_restore_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> RestoreUserUseCase:
    return RestoreUserUseCase(uow=uow, user_repo=user_repo, event_bus=event_bus)


def get_hard_delete_user_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> HardDeleteUserUseCase:
    return HardDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )
