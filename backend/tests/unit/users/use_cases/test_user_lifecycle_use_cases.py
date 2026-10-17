from datetime import UTC, datetime
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core import (
    CurrentUser,
    CurrentUserRole,
    OptimisticLockConflictException,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
    SystemRole,
)
from src.modules.users.application.dto import (
    RestoreUserDTO,
    SoftDeleteUserDTO,
)
from src.modules.users.application.use_cases import (
    HardDeleteUserUseCase,
    RestoreUserUseCase,
    SoftDeleteUserUseCase,
)
from src.modules.users.domain import (
    Role,
    SelfActionForbiddenError,
    SuperAdminProtectionError,
    User,
    UserDeactivatedEvent,
    UserDeletedEvent,
    UserNotFoundError,
    UserRestoredEvent,
)
from tests.unit.fake_repositories import FakeUserRepository
from tests.unit.fakes import (
    FakeAuthSessionGateway,
    FakeEventBus,
    FakeUnitOfWork,
)


def _make_actor(
    user_id: UUID | None = None,
    role_code: str = SystemRole.SUPER_ADMIN.value,
    username: str = "actor.admin",
) -> CurrentUser:
    uid = user_id or uuid7()
    rid = uuid7()
    return CurrentUser(
        id=uid,
        username=username,
        name="Actor Admin",
        role_id=rid,
        role=CurrentUserRole(id=rid, code=role_code, name="Admin Role"),
        effective_permissions=frozenset(),
        created_at=datetime.now(UTC),
    )


def _make_role(code: str = SystemRole.USER.value, name: str = "Користувач") -> Role:
    return Role(id=uuid7(), code=code, name=name, permissions=set())


def _make_user(
    username: str = "target.user",
    role: Role | None = None,
    is_active: bool = True,
) -> User:
    r = role or _make_role()
    u = User(
        id=uuid7(),
        username=username,
        name="Target User",
        password_hash="pw",
        role_id=r.id,
        role=r,
    )
    if not is_active:
        u.soft_delete()
    return u


# ==========================================
# 1. SoftDeleteUserUseCase Tests
# ==========================================


async def test_soft_delete_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    user = _make_user()
    await user_repo.save(user)
    actor = _make_actor()

    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = SoftDeleteUserDTO(version=user.version)
    await use_case.execute(user.id, dto, actor)

    assert user.is_active is False
    assert user.deleted_at is not None
    assert uow.committed is True
    assert user.id in auth_gateway.revoked_user_ids

    events = event_bus.get_events_of_type(UserDeactivatedEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id
    assert events[0].actor_id == actor.id


async def test_soft_delete_user_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user_id = uuid7()
    actor = _make_actor(user_id=user_id)

    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteUserDTO(version=1)

    with pytest.raises(SelfActionForbiddenError, match="власний обліковий запис"):
        await use_case.execute(user_id, dto, actor)


async def test_soft_delete_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteUserDTO(version=1)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_soft_delete_user_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user()
    user.version = 5
    await user_repo.save(user)
    actor = _make_actor()

    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteUserDTO(version=4)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(user.id, dto, actor)


async def test_soft_delete_user_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    target_admin = _make_user(role=admin_role)
    await user_repo.save(target_admin)
    actor = _make_actor()

    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteUserDTO(version=target_admin.version)

    with pytest.raises(SuperAdminProtectionError, match="SuperAdmin заборонено деактивовувати"):
        await use_case.execute(target_admin.id, dto, actor)


async def test_soft_delete_user_already_inactive() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user(is_active=False)
    await user_repo.save(user)
    actor = _make_actor()

    use_case = SoftDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteUserDTO(version=user.version)

    with pytest.raises(ResourceAlreadyInactiveException):
        await use_case.execute(user.id, dto, actor)


# ==========================================
# 2. RestoreUserUseCase Tests
# ==========================================


async def test_restore_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user(is_active=False)
    await user_repo.save(user)
    actor = _make_actor()

    use_case = RestoreUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = RestoreUserDTO(version=user.version)
    await use_case.execute(user.id, dto, actor)

    assert user.is_active is True
    assert user.deleted_at is None
    assert uow.committed is True

    events = event_bus.get_events_of_type(UserRestoredEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id
    assert events[0].actor_id == actor.id


async def test_restore_user_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user_id = uuid7()
    actor = _make_actor(user_id=user_id)

    use_case = RestoreUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = RestoreUserDTO(version=1)

    with pytest.raises(SelfActionForbiddenError, match="власний обліковий запис"):
        await use_case.execute(user_id, dto, actor)


async def test_restore_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = RestoreUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = RestoreUserDTO(version=1)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_restore_user_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user(is_active=False)
    user.version = 3
    await user_repo.save(user)
    actor = _make_actor()

    use_case = RestoreUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = RestoreUserDTO(version=2)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(user.id, dto, actor)


async def test_restore_user_already_active() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user(is_active=True)
    await user_repo.save(user)
    actor = _make_actor()

    use_case = RestoreUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = RestoreUserDTO(version=user.version)

    with pytest.raises(ResourceAlreadyActiveException):
        await use_case.execute(user.id, dto, actor)


# ==========================================
# 3. HardDeleteUserUseCase Tests
# ==========================================


async def test_hard_delete_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user()
    await user_repo.save(user)
    actor = _make_actor()

    use_case = HardDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    await use_case.execute(user.id, actor)

    assert uow.committed is True
    assert await user_repo.get_by_id(user.id) is None

    events = event_bus.get_events_of_type(UserDeletedEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id
    assert events[0].actor_id == actor.id


async def test_hard_delete_user_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user_id = uuid7()
    actor = _make_actor(user_id=user_id)

    use_case = HardDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    with pytest.raises(SelfActionForbiddenError, match="власний обліковий запис"):
        await use_case.execute(user_id, actor)


async def test_hard_delete_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = HardDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid7(), actor)


async def test_hard_delete_user_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    target_admin = _make_user(role=admin_role)
    await user_repo.save(target_admin)
    actor = _make_actor()

    use_case = HardDeleteUserUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    with pytest.raises(SuperAdminProtectionError, match="SuperAdmin заборонено"):
        await use_case.execute(target_admin.id, actor)
