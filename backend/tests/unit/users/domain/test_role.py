from datetime import UTC

import pytest
from uuid6 import uuid7

from src.core import (
    InactiveEntityError,
    PermissionCode,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
    SystemRole,
)
from src.modules.users.domain import (
    Permission,
    Role,
    SuperAdminProtectionError,
)


def _make_permission(code: PermissionCode, name: str = "Test Perm") -> Permission:
    return Permission(
        id=uuid7(),
        code=code,
        name=name,
    )


def test_role_create_success() -> None:
    p1 = _make_permission(PermissionCode.USERS_READ)
    p2 = _make_permission(PermissionCode.USERS_CREATE)

    role = Role.create(
        code="MODERATOR",
        name="Модератор контенту",
        description="Перевірка відгуків",
        permissions=[p1, p2],
    )

    assert role.code == "moderator"  # Lowercase normalized
    assert role.name == "Модератор контенту"
    assert role.description == "Перевірка відгуків"
    assert role.permissions == {p1, p2}
    assert role.permission_ids == {p1.id, p2.id}
    assert role.is_active is True
    assert role.is_super_admin is False
    assert role.is_system_role is False
    assert role.version == 1


@pytest.mark.parametrize("super_admin_code", ["super_admin", "SUPER_ADMIN", "Super_Admin"])
def test_role_create_super_admin_forbidden(super_admin_code: str) -> None:
    with pytest.raises(SuperAdminProtectionError, match="Створення системної ролі super_admin заборонено"):
        Role.create(
            code=super_admin_code,
            name="Головний адмін",
        )


def test_role_is_super_admin_and_system_role() -> None:
    role_admin = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )
    assert role_admin.is_super_admin is True
    assert role_admin.is_system_role is True

    role_user = Role(
        id=uuid7(),
        code=SystemRole.USER.value,
        name="User",
    )
    assert role_user.is_super_admin is False
    assert role_user.is_system_role is False


def test_role_update_details_success() -> None:
    p1 = _make_permission(PermissionCode.USERS_READ)
    p2 = _make_permission(PermissionCode.USERS_UPDATE)

    role = Role.create(
        code="editor",
        name="Редактор",
        permissions=[p1],
    )

    role.update_details(
        name="Старший редактор",
        description="Оновлений опис",
        permissions=[p2],
    )

    assert role.name == "Старший редактор"
    assert role.description == "Оновлений опис"
    assert role.permissions == {p2}
    assert role.updated_at is not None
    assert role.updated_at.tzinfo == UTC


def test_role_update_details_deactivated_raises() -> None:
    role = Role.create(code="editor", name="Редактор")
    role.soft_delete()

    with pytest.raises(InactiveEntityError, match="Неможливо редагувати деактивовану роль"):
        role.update_details(name="New Name", description=None, permissions=[])


def test_role_update_details_super_admin_raises() -> None:
    admin_role = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )

    with pytest.raises(SuperAdminProtectionError, match="Системну роль SUPER_ADMIN заборонено редагувати"):
        admin_role.update_details(name="New Name", description=None, permissions=[])


def test_role_set_permissions_success() -> None:
    p1 = _make_permission(PermissionCode.USERS_READ)
    p2 = _make_permission(PermissionCode.USERS_CREATE)
    role = Role.create(code="analyst", name="Аналітик", permissions=[p1])

    role.set_permissions([p2])
    assert role.permissions == {p2}
    assert role.updated_at is not None


def test_role_set_permissions_super_admin_raises() -> None:
    admin_role = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )
    p = _make_permission(PermissionCode.USERS_READ)

    with pytest.raises(SuperAdminProtectionError, match="Права ролі SUPER_ADMIN не можуть бути змінені"):
        admin_role.set_permissions([p])


def test_role_grant_permissions_success() -> None:
    p1 = _make_permission(PermissionCode.USERS_READ)
    p2 = _make_permission(PermissionCode.USERS_CREATE)
    role = Role.create(code="analyst", name="Аналітик", permissions=[p1])

    # Grant p1 (duplicate) and p2 (new)
    role.grant_permissions([p1, p2])
    assert role.permissions == {p1, p2}
    assert len(role.permissions) == 2


def test_role_grant_permissions_deactivated_raises() -> None:
    role = Role.create(code="analyst", name="Аналітик")
    role.soft_delete()
    p = _make_permission(PermissionCode.USERS_READ)

    with pytest.raises(InactiveEntityError, match="Неможливо змінити дозволи деактивованої ролі"):
        role.grant_permissions([p])


def test_role_grant_permissions_super_admin_raises() -> None:
    admin_role = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )
    p = _make_permission(PermissionCode.USERS_READ)

    with pytest.raises(SuperAdminProtectionError, match="Права ролі SUPER_ADMIN не можуть бути змінені"):
        admin_role.grant_permissions([p])


def test_role_revoke_permissions_success() -> None:
    p1 = _make_permission(PermissionCode.USERS_READ)
    p2 = _make_permission(PermissionCode.USERS_CREATE)
    role = Role.create(code="analyst", name="Аналітик", permissions=[p1, p2])

    role.revoke_permissions([p1.id])
    assert role.permissions == {p2}


def test_role_revoke_permissions_deactivated_raises() -> None:
    role = Role.create(code="analyst", name="Аналітик")
    role.soft_delete()

    with pytest.raises(InactiveEntityError, match="Неможливо змінити дозволи деактивованої ролі"):
        role.revoke_permissions([uuid7()])


def test_role_revoke_permissions_super_admin_raises() -> None:
    admin_role = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )

    with pytest.raises(SuperAdminProtectionError, match="Права ролі SUPER_ADMIN не можуть бути змінені"):
        admin_role.revoke_permissions([uuid7()])


def test_role_soft_delete_success() -> None:
    role = Role.create(code="temporary", name="Тимчасова роль")
    assert role.is_active is True

    role.soft_delete()

    assert role.is_active is False
    assert role.deleted_at is not None


def test_role_soft_delete_super_admin_forbidden() -> None:
    admin_role = Role(
        id=uuid7(),
        code=SystemRole.SUPER_ADMIN.value,
        name="Super Admin",
    )

    with pytest.raises(
        SuperAdminProtectionError,
        match="Системну роль SUPER_ADMIN заборонено деактивовувати чи видаляти",
    ):
        admin_role.soft_delete()


def test_role_soft_delete_already_inactive_raises() -> None:
    role = Role.create(code="temporary", name="Тимчасова роль")
    role.soft_delete()

    with pytest.raises(ResourceAlreadyInactiveException):
        role.soft_delete()


def test_role_restore_success() -> None:
    role = Role.create(code="temporary", name="Тимчасова роль")
    role.soft_delete()
    assert role.is_active is False

    role.restore()
    assert role.is_active is True
    assert role.deleted_at is None


def test_role_restore_already_active_raises() -> None:
    role = Role.create(code="temporary", name="Тимчасова роль")
    with pytest.raises(ResourceAlreadyActiveException):
        role.restore()


def test_role_permissions_list_converted_to_set() -> None:
    p = _make_permission(PermissionCode.USERS_READ)
    role = Role(
        id=uuid7(),
        code="test_role",
        name="Test Role",
        permissions=[p],  # type: ignore[arg-type]
    )
    assert isinstance(role.permissions, set)
    assert role.permissions == {p}
