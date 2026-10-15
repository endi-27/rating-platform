from datetime import UTC, datetime
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core import (
    CurrentUser,
    CurrentUserRole,
    InactiveEntityError,
    InvalidCredentialsException,
    OptimisticLockConflictException,
    SystemRole,
)
from src.modules.users.application.dto import (
    ChangeSelfPasswordDTO,
    ChangeSelfUsernameDTO,
    ResetUserPasswordDTO,
    UpdateSelfProfileDTO,
    UpdateUserDTO,
)
from src.modules.users.application.use_cases import (
    ChangeSelfPasswordUseCase,
    ChangeSelfUsernameUseCase,
    ResetUserPasswordUseCase,
    UpdateSelfProfileUseCase,
    UpdateUserUseCase,
)
from src.modules.users.domain import (
    InactiveRoleAssignmentError,
    PermissionNotFoundError,
    Role,
    RoleNotFoundError,
    SelfActionForbiddenError,
    SuperAdminProtectionError,
    User,
    UserAlreadyExistsError,
    UserCredentialsChangedEvent,
    UserNotFoundError,
    UserPasswordChangedEvent,
    UserUpdatedEvent,
    UserUsernameChangedEvent,
)
from tests.unit.fake_repositories import (
    FakePermissionRepository,
    FakeRoleRepository,
    FakeUserRepository,
)
from tests.unit.fakes import (
    FakeAuthSessionGateway,
    FakeEventBus,
    FakePasswordHasher,
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


def _make_role(code: str = SystemRole.USER.value, name: str = "Користувач", is_active: bool = True) -> Role:
    role = Role(id=uuid7(), code=code, name=name, permissions=set())
    if not is_active:
        role.soft_delete()
    return role


def _make_user(
    username: str = "target.user",
    password_hash: str = "hashed_OldPassword123!",
    role: Role | None = None,
    is_active: bool = True,
) -> User:
    r = role or _make_role()
    u = User(
        id=uuid7(),
        username=username,
        name="Target User",
        password_hash=password_hash,
        role_id=r.id,
        role=r,
    )
    if not is_active:
        u.soft_delete()
    return u


# ==========================================
# 1. ChangeSelfPasswordUseCase Tests
# ==========================================


async def test_change_self_password_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user(password_hash=hasher.hash("OldPassword123!"))
    await user_repo.save(user)

    actor = _make_actor(user_id=user.id, username=user.username)

    use_case = ChangeSelfPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfPasswordDTO(
        old_password="OldPassword123!",
        new_password="NewPassword456!",
    )

    await use_case.execute(actor, dto)

    assert uow.committed is True
    assert user.password_hash == hasher.hash("NewPassword456!")
    assert user.id in auth_gateway.revoked_user_ids

    events = event_bus.get_events_of_type(UserPasswordChangedEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id
    assert events[0].actor_id == actor.id


async def test_change_self_password_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = ChangeSelfPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ChangeSelfPasswordDTO(
        old_password="OldPassword123!",
        new_password="NewPassword456!",
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(actor, dto)

    assert uow.rolled_back is True


async def test_change_self_password_deactivated_user_raises() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user(password_hash=hasher.hash("OldPassword123!"), is_active=False)
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id)

    use_case = ChangeSelfPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfPasswordDTO(
        old_password="OldPassword123!",
        new_password="NewPassword456!",
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(actor, dto)


async def test_change_self_password_wrong_old_password() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user(password_hash=hasher.hash("CorrectOldPassword123!"))
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id)

    use_case = ChangeSelfPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfPasswordDTO(
        old_password="WrongOldPassword999!",
        new_password="NewPassword456!",
    )

    with pytest.raises(InvalidCredentialsException, match="Поточний пароль вказано невірно"):
        await use_case.execute(actor, dto)

    assert uow.rolled_back is True


# ==========================================
# 2. ChangeSelfUsernameUseCase Tests
# ==========================================


async def test_change_self_username_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user(username="old.username", password_hash=hasher.hash("Secret123!"))
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id, username="old.username")

    use_case = ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfUsernameDTO(
        current_password="Secret123!",
        new_username="new.username",
        version=user.version,
    )

    await use_case.execute(actor, dto)

    assert uow.committed is True
    assert user.username == "new.username"
    assert user.id in auth_gateway.revoked_user_ids

    updated_events = event_bus.get_events_of_type(UserUpdatedEvent)
    assert len(updated_events) == 1
    assert updated_events[0].username == "new.username"

    username_events = event_bus.get_events_of_type(UserUsernameChangedEvent)
    assert len(username_events) == 1
    assert username_events[0].old_username == "old.username"
    assert username_events[0].new_username == "new.username"


async def test_change_self_username_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ChangeSelfUsernameDTO(
        current_password="Secret123!",
        new_username="new.username",
        version=1,
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(actor, dto)


async def test_change_self_username_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    user = _make_user()
    user.version = 3
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id)

    use_case = ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ChangeSelfUsernameDTO(
        current_password="Secret123!",
        new_username="new.username",
        version=2,  # Stale version
    )

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(actor, dto)


async def test_change_self_username_wrong_password() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user(password_hash=hasher.hash("RealPassword123!"))
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id)

    use_case = ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfUsernameDTO(
        current_password="WrongPassword123!",
        new_username="new.username",
        version=user.version,
    )

    with pytest.raises(InvalidCredentialsException, match="Невірний пароль для підтвердження"):
        await use_case.execute(actor, dto)


async def test_change_self_username_already_taken() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user1 = _make_user(username="user.one", password_hash=hasher.hash("Secret123!"))
    user2 = _make_user(username="user.two")
    await user_repo.save(user1)
    await user_repo.save(user2)

    actor = _make_actor(user_id=user1.id)

    use_case = ChangeSelfUsernameUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ChangeSelfUsernameDTO(
        current_password="Secret123!",
        new_username="user.two",  # Taken by user2
        version=user1.version,
    )

    with pytest.raises(UserAlreadyExistsError, match="вже існує"):
        await use_case.execute(actor, dto)


# ==========================================
# 3. UpdateSelfProfileUseCase Tests
# ==========================================


async def test_update_self_profile_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user(username="self.user")
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id, username="self.user")

    use_case = UpdateSelfProfileUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = UpdateSelfProfileDTO(
        name="Updated Name",
        version=user.version,
    )

    await use_case.execute(actor, dto)

    assert uow.committed is True
    assert user.name == "Updated Name"

    events = event_bus.get_events_of_type(UserUpdatedEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id


async def test_update_self_profile_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = UpdateSelfProfileUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = UpdateSelfProfileDTO(name="Name", version=1)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(actor, dto)


async def test_update_self_profile_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    event_bus = FakeEventBus()

    user = _make_user()
    user.version = 5
    await user_repo.save(user)
    actor = _make_actor(user_id=user.id)

    use_case = UpdateSelfProfileUseCase(
        uow=uow,
        user_repo=user_repo,
        event_bus=event_bus,
    )

    dto = UpdateSelfProfileDTO(name="Name", version=4)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(actor, dto)


# ==========================================
# 4. UpdateUserUseCase Tests
# ==========================================


async def test_update_user_credentials_changed_revokes_sessions() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    role1 = _make_role(name="Role 1")
    role2 = _make_role(name="Role 2")
    await role_repo.save(role1)
    await role_repo.save(role2)

    user = _make_user(username="target.user", role=role1)
    await user_repo.save(user)

    actor = _make_actor()  # Different ID

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="target.updated",
        name="Updated Target Name",
        role_id=role2.id,
        version=user.version,
    )

    await use_case.execute(user.id, dto, actor)

    assert uow.committed is True
    assert user.username == "target.updated"
    assert user.name == "Updated Target Name"
    assert user.role_id == role2.id
    assert user.id in auth_gateway.revoked_user_ids

    updated_events = event_bus.get_events_of_type(UserUpdatedEvent)
    assert len(updated_events) == 1

    cred_events = event_bus.get_events_of_type(UserCredentialsChangedEvent)
    assert len(cred_events) == 1


async def test_update_user_only_name_changed_no_session_revocation() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    role = _make_role()
    await role_repo.save(role)

    user = _make_user(username="target.user", role=role)
    await user_repo.save(user)

    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username=user.username,
        name="Only Name Changed",
        role_id=role.id,
        custom_permission_ids=None,
        version=user.version,
    )

    await use_case.execute(user.id, dto, actor)

    assert uow.committed is True
    assert user.name == "Only Name Changed"
    assert len(auth_gateway.revoked_user_ids) == 0

    assert len(event_bus.get_events_of_type(UserUpdatedEvent)) == 1
    assert len(event_bus.get_events_of_type(UserCredentialsChangedEvent)) == 0


async def test_update_user_self_action_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    user_id = uuid7()
    actor = _make_actor(user_id=user_id)

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="self.name",
        name="Self Name",
        role_id=uuid7(),
        version=1,
    )

    with pytest.raises(SelfActionForbiddenError, match="власний обліковий запис"):
        await use_case.execute(user_id, dto, actor)


async def test_update_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    actor = _make_actor()
    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="some.user",
        name="Some User",
        role_id=uuid7(),
        version=1,
    )

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid7(), dto, actor)

    assert uow.rolled_back is True


async def test_update_user_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    role = _make_role()
    await role_repo.save(role)

    user = _make_user(role=role)
    user.version = 5
    await user_repo.save(user)

    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="updated.username",
        name="Updated Name",
        role_id=role.id,
        version=4,  # Stale version
    )

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(user.id, dto, actor)

    assert uow.rolled_back is True


async def test_update_user_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    target_admin = _make_user(role=admin_role)
    await user_repo.save(target_admin)

    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="target.admin",
        name="New Name",
        role_id=admin_role.id,
        version=target_admin.version,
    )

    with pytest.raises(SuperAdminProtectionError, match="SuperAdmin заборонено"):
        await use_case.execute(target_admin.id, dto, actor)


async def test_update_user_username_already_exists() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    role = _make_role()
    await role_repo.save(role)

    user1 = _make_user(username="first.user", role=role)
    user2 = _make_user(username="second.user", role=role)
    await user_repo.save(user1)
    await user_repo.save(user2)

    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username="second.user",  # Taken by user2
        name="First User",
        role_id=role.id,
        version=user1.version,
    )

    with pytest.raises(UserAlreadyExistsError, match="вже існує"):
        await use_case.execute(user1.id, dto, actor)


async def test_update_user_role_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    user = _make_user()
    await user_repo.save(user)
    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username=user.username,
        name="New Name",
        role_id=uuid7(),  # Nonexistent
        version=user.version,
    )

    with pytest.raises(RoleNotFoundError):
        await use_case.execute(user.id, dto, actor)


async def test_update_user_inactive_role_raises() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    inactive_role = _make_role(is_active=False)
    await role_repo.save(inactive_role)

    user = _make_user()
    await user_repo.save(user)
    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username=user.username,
        name="New Name",
        role_id=inactive_role.id,
        version=user.version,
    )

    with pytest.raises(InactiveRoleAssignmentError):
        await use_case.execute(user.id, dto, actor)


async def test_update_user_missing_permissions_raises() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    auth_gateway = FakeAuthSessionGateway()

    role = _make_role()
    await role_repo.save(role)

    user = _make_user(role=role)
    await user_repo.save(user)
    actor = _make_actor()

    use_case = UpdateUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        auth_gateway=auth_gateway,
    )

    dto = UpdateUserDTO(
        username=user.username,
        name="New Name",
        role_id=role.id,
        custom_permission_ids=[uuid7()],  # Nonexistent
        version=user.version,
    )

    with pytest.raises(PermissionNotFoundError):
        await use_case.execute(user.id, dto, actor)


# ==========================================
# 5. ResetUserPasswordUseCase Tests
# ==========================================


async def test_reset_user_password_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _make_user()
    await user_repo.save(user)
    actor = _make_actor()

    use_case = ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = ResetUserPasswordDTO(new_password="AdminResetPassword123!")
    await use_case.execute(user.id, dto, actor)

    assert uow.committed is True
    assert user.password_hash == hasher.hash("AdminResetPassword123!")
    assert user.id in auth_gateway.revoked_user_ids

    events = event_bus.get_events_of_type(UserPasswordChangedEvent)
    assert len(events) == 1
    assert events[0].entity_id == user.id
    assert events[0].actor_id == actor.id


async def test_reset_user_password_self_action_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    user_id = uuid7()
    actor = _make_actor(user_id=user_id)

    use_case = ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ResetUserPasswordDTO(new_password="NewPassword123!")

    with pytest.raises(SelfActionForbiddenError, match="власний обліковий запис"):
        await use_case.execute(user_id, dto, actor)


async def test_reset_user_password_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ResetUserPasswordDTO(new_password="NewPassword123!")

    with pytest.raises(UserNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_reset_user_password_inactive_user_raises() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    user = _make_user(is_active=False)
    await user_repo.save(user)
    actor = _make_actor()

    use_case = ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ResetUserPasswordDTO(new_password="NewPassword123!")

    with pytest.raises(InactiveEntityError, match="деактивованого користувача"):
        await use_case.execute(user.id, dto, actor)


async def test_reset_user_password_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    auth_gateway = FakeAuthSessionGateway()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    target_admin = _make_user(role=admin_role)
    await user_repo.save(target_admin)
    actor = _make_actor()

    use_case = ResetUserPasswordUseCase(
        uow=uow,
        user_repo=user_repo,
        auth_gateway=auth_gateway,
        event_bus=event_bus,
    )

    dto = ResetUserPasswordDTO(new_password="NewPassword123!")

    with pytest.raises(SuperAdminProtectionError, match="SuperAdmin заборонено"):
        await use_case.execute(target_admin.id, dto, actor)
