import pytest
from uuid6 import uuid7

from src.core import PermissionCode, SystemRole
from src.modules.users.application.dto import CreateUserDTO
from src.modules.users.application.use_cases import RegisterUserUseCase
from src.modules.users.domain import (
    InactiveRoleAssignmentError,
    Permission,
    PermissionNotFoundError,
    Role,
    RoleNotFoundError,
    SuperAdminProtectionError,
    UserAlreadyExistsError,
    UserCreatedEvent,
)
from tests.unit.fake_repositories import (
    FakePermissionRepository,
    FakeRoleRepository,
    FakeUserRepository,
)
from tests.unit.fakes import FakeEventBus, FakePasswordHasher, FakeUnitOfWork


def _make_perm(code: PermissionCode) -> Permission:
    return Permission(id=uuid7(), code=code, name=code.value)


def _make_role(
    code: str = SystemRole.USER.value,
    name: str = "Користувач",
    is_active: bool = True,
) -> Role:
    role = Role(
        id=uuid7(),
        code=code,
        name=name,
        permissions=set(),
    )
    if not is_active:
        role.soft_delete()
    return role


async def test_register_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    role = _make_role()
    await role_repo.save(role)

    p1 = _make_perm(PermissionCode.USERS_READ)
    perm_repo.permissions[p1.id] = p1

    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = CreateUserDTO(
        username="new.user",
        name="New User",
        password="StrongPassword123!",
        role_id=role.id,
        custom_permission_ids=[p1.id],
    )

    created_id = await use_case.execute(dto)

    assert created_id is not None
    assert uow.committed is True
    assert uow.rolled_back is False

    # Check user in repo
    saved_user = await user_repo.get_by_id(created_id)
    assert saved_user is not None
    assert saved_user.username == "new.user"
    assert saved_user.name == "New User"
    assert saved_user.role_id == role.id
    assert saved_user.custom_permission_ids == {p1.id}
    assert saved_user.password_hash == "hashed_StrongPassword123!"

    # Check event published
    created_events = event_bus.get_events_of_type(UserCreatedEvent)
    assert len(created_events) == 1
    assert created_events[0].entity_id == created_id
    assert created_events[0].username == "new.user"
    assert created_events[0].role_id == role.id


async def test_register_user_already_exists() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)

    # Pre-populate existing user
    dto_first = CreateUserDTO(
        username="existing.user",
        name="First User",
        password="Password123!",
        role_id=role.id,
    )
    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )
    await use_case.execute(dto_first)

    # Attempt duplicate registration
    dto_duplicate = CreateUserDTO(
        username="existing.user",
        name="Second User",
        password="Password123!",
        role_id=role.id,
    )

    with pytest.raises(UserAlreadyExistsError, match="вже існує"):
        await use_case.execute(dto_duplicate)

    assert uow.rolled_back is True


async def test_register_user_role_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateUserDTO(
        username="john.doe",
        name="John Doe",
        password="Password123!",
        role_id=uuid7(),
    )

    with pytest.raises(RoleNotFoundError, match="Призначену роль не знайдено"):
        await use_case.execute(dto)

    assert uow.rolled_back is True


async def test_register_user_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    await role_repo.save(admin_role)

    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateUserDTO(
        username="admin.new",
        name="Admin New",
        password="Password123!",
        role_id=admin_role.id,
    )

    with pytest.raises(SuperAdminProtectionError, match="Створення SuperAdmin користувачів заборонено"):
        await use_case.execute(dto)

    assert uow.rolled_back is True


async def test_register_user_inactive_role_forbidden() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    inactive_role = _make_role(is_active=False)
    await role_repo.save(inactive_role)

    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateUserDTO(
        username="john.doe",
        name="John Doe",
        password="Password123!",
        role_id=inactive_role.id,
    )

    with pytest.raises(InactiveRoleAssignmentError, match="деактивованою роллю"):
        await use_case.execute(dto)

    assert uow.rolled_back is True


async def test_register_user_missing_permissions_raises() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)

    missing_perm_id = uuid7()

    use_case = RegisterUserUseCase(
        uow=uow,
        user_repo=user_repo,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateUserDTO(
        username="john.doe",
        name="John Doe",
        password="Password123!",
        role_id=role.id,
        custom_permission_ids=[missing_perm_id],
    )

    with pytest.raises(PermissionNotFoundError, match="Дозволи з наступними ID не знайдено"):
        await use_case.execute(dto)

    assert uow.rolled_back is True
