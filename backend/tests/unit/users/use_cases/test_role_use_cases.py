from datetime import UTC, datetime
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core import (
    CurrentUser,
    CurrentUserRole,
    InactiveEntityError,
    OptimisticLockConflictException,
    PermissionCode,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
    ResourceLockedException,
    SystemRole,
)
from src.modules.users.application.dto import (
    CreateRoleDTO,
    RestoreRoleDTO,
    SoftDeleteRoleDTO,
    UpdateRoleDTO,
)
from src.modules.users.application.use_cases import (
    CreateRoleUseCase,
    HardDeleteRoleUseCase,
    RestoreRoleUseCase,
    SoftDeleteRoleUseCase,
    UpdateRoleUseCase,
)
from src.modules.users.domain import (
    Permission,
    PermissionNotFoundError,
    Role,
    RoleAlreadyExistsError,
    RoleCreatedEvent,
    RoleDeactivatedEvent,
    RoleDeletedEvent,
    RoleNotFoundError,
    RoleRestoredEvent,
    RoleUpdatedEvent,
    SelfActionForbiddenError,
    SuperAdminProtectionError,
)
from tests.unit.fake_repositories import (
    FakePermissionRepository,
    FakeRoleRepository,
)
from tests.unit.fakes import FakeEventBus, FakeUnitOfWork


def _make_perm(code: PermissionCode) -> Permission:
    return Permission(id=uuid7(), code=code, name=code.value)


def _make_actor(
    user_id: UUID | None = None,
    role_id: UUID | None = None,
    role_code: str = SystemRole.SUPER_ADMIN.value,
) -> CurrentUser:
    uid = user_id or uuid7()
    rid = role_id or uuid7()
    return CurrentUser(
        id=uid,
        username="actor.admin",
        name="Actor Admin",
        role_id=rid,
        role=CurrentUserRole(id=rid, code=role_code, name="Admin Role"),
        effective_permissions=frozenset(),
        created_at=datetime.now(UTC),
    )


def _make_role(
    code: str = "custom_role",
    name: str = "Кастомна роль",
    permissions: list[Permission] | None = None,
    is_active: bool = True,
) -> Role:
    role = Role(
        id=uuid7(),
        code=code,
        name=name,
        permissions=set(permissions or []),
    )
    if not is_active:
        role.soft_delete()
    return role


# ==========================================
# 1. CreateRoleUseCase Tests
# ==========================================


async def test_create_role_success() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    p1 = _make_perm(PermissionCode.USERS_READ)
    perm_repo.permissions[p1.id] = p1

    use_case = CreateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateRoleDTO(
        code="operator",
        name="Оператор",
        description="Оператор лінії",
        permission_ids=[p1.id],
    )

    role_id = await use_case.execute(dto)

    assert role_id is not None
    assert uow.committed is True

    saved_role = await role_repo.get_by_id(role_id)
    assert saved_role is not None
    assert saved_role.code == "operator"
    assert saved_role.name == "Оператор"
    assert saved_role.permissions == {p1}

    events = event_bus.get_events_of_type(RoleCreatedEvent)
    assert len(events) == 1
    assert events[0].entity_id == role_id
    assert events[0].code == "operator"


async def test_create_role_already_exists() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    existing_role = _make_role(code="analyst")
    await role_repo.save(existing_role)

    use_case = CreateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateRoleDTO(code="analyst", name="Аналітик")

    with pytest.raises(RoleAlreadyExistsError, match="вже існує"):
        await use_case.execute(dto)

    assert uow.rolled_back is True


async def test_create_role_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    use_case = CreateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateRoleDTO(code="super_admin", name="Super Admin")

    with pytest.raises(SuperAdminProtectionError, match="Створення системної ролі super_admin заборонено"):
        await use_case.execute(dto)

    assert uow.rolled_back is True


async def test_create_role_missing_permissions() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    use_case = CreateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = CreateRoleDTO(
        code="tester",
        name="Тестувальник",
        permission_ids=[uuid7()],
    )

    with pytest.raises(PermissionNotFoundError):
        await use_case.execute(dto)

    assert uow.rolled_back is True


# ==========================================
# 2. UpdateRoleUseCase Tests
# ==========================================


async def test_update_role_success() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    p1 = _make_perm(PermissionCode.USERS_READ)
    p2 = _make_perm(PermissionCode.ROLES_READ)
    perm_repo.permissions[p1.id] = p1
    perm_repo.permissions[p2.id] = p2

    role = _make_role(code="editor", name="Редактор", permissions=[p1])
    await role_repo.save(role)

    actor = _make_actor()  # Different role_id

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(
        name="Старший редактор",
        description="Новий опис",
        permission_ids=[p2.id],
        version=role.version,
    )

    await use_case.execute(role.id, dto, actor)

    assert uow.committed is True
    assert role.name == "Старший редактор"
    assert role.description == "Новий опис"
    assert role.permissions == {p2}

    events = event_bus.get_events_of_type(RoleUpdatedEvent)
    assert len(events) == 1
    assert events[0].entity_id == role.id


async def test_update_role_self_role_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role_id = uuid7()
    actor = _make_actor(role_id=role_id)

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(
        name="New Name",
        permission_ids=[],
        version=1,
    )

    with pytest.raises(SelfActionForbiddenError, match="власну призначену роль"):
        await use_case.execute(role_id, dto, actor)


async def test_update_role_not_found() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(name="Name", permission_ids=[], version=1)

    with pytest.raises(RoleNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_update_role_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    role.version = 3
    await role_repo.save(role)
    actor = _make_actor()

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(name="Name", permission_ids=[], version=2)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(role.id, dto, actor)


async def test_update_role_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    await role_repo.save(admin_role)
    actor = _make_actor()

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(name="New Admin Name", permission_ids=[], version=admin_role.version)

    with pytest.raises(SuperAdminProtectionError, match="SUPER_ADMIN заборонено редагувати"):
        await use_case.execute(admin_role.id, dto, actor)


async def test_update_role_deactivated_role_raises() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role = _make_role(is_active=False)
    await role_repo.save(role)
    actor = _make_actor()

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(name="New Name", permission_ids=[], version=role.version)

    with pytest.raises(InactiveEntityError, match="деактивовану роль"):
        await use_case.execute(role.id, dto, actor)


async def test_update_role_missing_permissions() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    perm_repo = FakePermissionRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)
    actor = _make_actor()

    use_case = UpdateRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        permission_repo=perm_repo,
        event_bus=event_bus,
    )

    dto = UpdateRoleDTO(name="New Name", permission_ids=[uuid7()], version=role.version)

    with pytest.raises(PermissionNotFoundError):
        await use_case.execute(role.id, dto, actor)


# ==========================================
# 3. SoftDeleteRoleUseCase Tests
# ==========================================


async def test_soft_delete_role_success() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)
    actor = _make_actor()

    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=role.version)
    await use_case.execute(role.id, dto, actor)

    assert role.is_active is False
    assert role.deleted_at is not None
    assert uow.committed is True

    events = event_bus.get_events_of_type(RoleDeactivatedEvent)
    assert len(events) == 1
    assert events[0].entity_id == role.id


async def test_soft_delete_role_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role_id = uuid7()
    actor = _make_actor(role_id=role_id)

    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=1)

    with pytest.raises(SelfActionForbiddenError, match="власну призначену роль"):
        await use_case.execute(role_id, dto, actor)


async def test_soft_delete_role_not_found() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=1)

    with pytest.raises(RoleNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_soft_delete_role_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    role.version = 5
    await role_repo.save(role)
    actor = _make_actor()

    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=4)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(role.id, dto, actor)


async def test_soft_delete_role_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    await role_repo.save(admin_role)
    actor = _make_actor()

    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=admin_role.version)

    with pytest.raises(SuperAdminProtectionError, match="SUPER_ADMIN заборонено деактивовувати"):
        await use_case.execute(admin_role.id, dto, actor)


async def test_soft_delete_role_already_inactive() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role(is_active=False)
    await role_repo.save(role)
    actor = _make_actor()

    use_case = SoftDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = SoftDeleteRoleDTO(version=role.version)

    with pytest.raises(ResourceAlreadyInactiveException):
        await use_case.execute(role.id, dto, actor)


# ==========================================
# 4. RestoreRoleUseCase Tests
# ==========================================


async def test_restore_role_success() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role(is_active=False)
    await role_repo.save(role)
    actor = _make_actor()

    use_case = RestoreRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = RestoreRoleDTO(version=role.version)
    await use_case.execute(role.id, dto, actor)

    assert role.is_active is True
    assert role.deleted_at is None
    assert uow.committed is True

    events = event_bus.get_events_of_type(RoleRestoredEvent)
    assert len(events) == 1
    assert events[0].entity_id == role.id


async def test_restore_role_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role_id = uuid7()
    actor = _make_actor(role_id=role_id)

    use_case = RestoreRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = RestoreRoleDTO(version=1)

    with pytest.raises(SelfActionForbiddenError, match="власну призначену роль"):
        await use_case.execute(role_id, dto, actor)


async def test_restore_role_not_found() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = RestoreRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = RestoreRoleDTO(version=1)

    with pytest.raises(RoleNotFoundError):
        await use_case.execute(uuid7(), dto, actor)


async def test_restore_role_occ_conflict() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role(is_active=False)
    role.version = 5
    await role_repo.save(role)
    actor = _make_actor()

    use_case = RestoreRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = RestoreRoleDTO(version=4)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(role.id, dto, actor)


async def test_restore_role_already_active() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role(is_active=True)
    await role_repo.save(role)
    actor = _make_actor()

    use_case = RestoreRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    dto = RestoreRoleDTO(version=role.version)

    with pytest.raises(ResourceAlreadyActiveException):
        await use_case.execute(role.id, dto, actor)


# ==========================================
# 5. HardDeleteRoleUseCase Tests
# ==========================================


async def test_hard_delete_role_success() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)
    actor = _make_actor()

    use_case = HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    await use_case.execute(role.id, actor)

    assert uow.committed is True
    assert await role_repo.get_by_id(role.id) is None

    events = event_bus.get_events_of_type(RoleDeletedEvent)
    assert len(events) == 1
    assert events[0].entity_id == role.id


async def test_hard_delete_role_self_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role_id = uuid7()
    actor = _make_actor(role_id=role_id)

    use_case = HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    with pytest.raises(SelfActionForbiddenError, match="власну призначену роль"):
        await use_case.execute(role_id, actor)


async def test_hard_delete_role_not_found() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    actor = _make_actor()
    use_case = HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    with pytest.raises(RoleNotFoundError):
        await use_case.execute(uuid7(), actor)


async def test_hard_delete_role_super_admin_forbidden() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    await role_repo.save(admin_role)
    actor = _make_actor()

    use_case = HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    with pytest.raises(SuperAdminProtectionError, match="super_admin"):
        await use_case.execute(admin_role.id, actor)


async def test_hard_delete_role_locked_in_use_raises() -> None:
    uow = FakeUnitOfWork()
    role_repo = FakeRoleRepository()
    event_bus = FakeEventBus()

    role = _make_role()
    await role_repo.save(role)
    role_repo.locked_role_ids.add(role.id)  # Role is assigned to users in db
    actor = _make_actor()

    use_case = HardDeleteRoleUseCase(
        uow=uow,
        role_repo=role_repo,
        event_bus=event_bus,
    )

    with pytest.raises(ResourceLockedException, match="використовується в пов'язаних даних"):
        await use_case.execute(role.id, actor)
