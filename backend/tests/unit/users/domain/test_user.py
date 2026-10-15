from datetime import UTC

import pytest
from uuid6 import uuid7

from src.core import (
    InactiveEntityError,
    PermissionCode,
    ResourceAlreadyInactiveException,
    SystemRole,
)
from src.modules.users.domain import (
    InactiveRoleAssignmentError,
    Permission,
    Role,
    SuperAdminProtectionError,
    User,
)
from tests.unit.fakes import FakePasswordHasher


def _make_perm(code: PermissionCode) -> Permission:
    return Permission(id=uuid7(), code=code, name=code.value)


def _make_role(
    code: str = SystemRole.USER.value,
    name: str = "Користувач",
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


def test_user_register_success() -> None:
    p1 = _make_perm(PermissionCode.USERS_READ)
    role = _make_role(permissions=[p1])
    custom_p = _make_perm(PermissionCode.USERS_UPDATE)

    user = User.register(
        username="john.doe",
        name="John Doe",
        password_hash="hashed_Secret123!",
        role=role,
        custom_permissions=[custom_p],
    )

    assert user.username == "john.doe"
    assert user.name == "John Doe"
    assert user.password_hash == "hashed_Secret123!"
    assert user.role_id == role.id
    assert user.role == role
    assert user.custom_permissions == {custom_p}
    assert user.custom_permission_ids == {custom_p.id}
    assert user.is_active is True
    assert user.is_super_admin is False
    assert user.version == 1


def test_user_register_super_admin_forbidden() -> None:
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")

    with pytest.raises(SuperAdminProtectionError, match="Створення SuperAdmin користувачів заборонено"):
        User.register(
            username="admin.root",
            name="Root Admin",
            password_hash="hashed_pw",
            role=admin_role,
        )


def test_user_register_inactive_role_forbidden() -> None:
    inactive_role = _make_role(is_active=False)

    with pytest.raises(InactiveRoleAssignmentError, match="деактивованою роллю"):
        User.register(
            username="john.doe",
            name="John Doe",
            password_hash="hashed_pw",
            role=inactive_role,
        )


def test_user_is_super_admin() -> None:
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    user_admin = User(
        id=uuid7(),
        username="admin",
        name="Admin",
        password_hash="pw",
        role_id=admin_role.id,
        role=admin_role,
    )
    assert user_admin.is_super_admin is True

    user_no_role = User(
        id=uuid7(),
        username="user",
        name="User",
        password_hash="pw",
        role_id=uuid7(),
        role=None,
    )
    assert user_no_role.is_super_admin is False


def test_user_effective_permissions_regular_user() -> None:
    p_role = _make_perm(PermissionCode.USERS_READ)
    p_custom = _make_perm(PermissionCode.ROLES_READ)
    role = _make_role(permissions=[p_role])

    user = User.register(
        username="alice",
        name="Alice",
        password_hash="pw",
        role=role,
        custom_permissions=[p_custom],
    )

    effective = user.effective_permissions
    assert effective == {PermissionCode.USERS_READ.value, PermissionCode.ROLES_READ.value}
    assert user.has_permission(PermissionCode.USERS_READ) is True
    assert user.has_permission(PermissionCode.USERS_READ.value) is True
    assert user.has_permission(PermissionCode.ROLES_READ) is True
    assert user.has_permission(PermissionCode.USERS_CREATE) is False


def test_user_effective_permissions_super_admin() -> None:
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    user = User(
        id=uuid7(),
        username="root",
        name="Root",
        password_hash="pw",
        role_id=admin_role.id,
        role=admin_role,
    )

    all_codes = {p.value for p in PermissionCode}
    assert user.effective_permissions == all_codes
    for code in PermissionCode:
        assert user.has_permission(code) is True


def test_user_verify_password() -> None:
    hasher = FakePasswordHasher()
    role = _make_role()
    user = User.register(
        username="bob",
        name="Bob",
        password_hash=hasher.hash("MyPassword123!"),
        role=role,
    )

    assert user.verify_password("MyPassword123!", hasher) is True
    assert user.verify_password("WrongPassword!", hasher) is False


def test_user_change_password_success() -> None:
    role = _make_role()
    user = User.register(username="bob", name="Bob", password_hash="old_hash", role=role)

    user.change_password("new_hash")
    assert user.password_hash == "new_hash"
    assert user.updated_at is not None
    assert user.updated_at.tzinfo == UTC


def test_user_change_password_deactivated_raises() -> None:
    role = _make_role()
    user = User.register(username="bob", name="Bob", password_hash="old_hash", role=role)
    user.soft_delete()

    with pytest.raises(InactiveEntityError, match="змінити пароль деактивованого користувача"):
        user.change_password("new_hash")


def test_user_assign_role_success() -> None:
    role1 = _make_role(name="Role 1")
    role2 = _make_role(name="Role 2")
    user = User.register(username="charlie", name="Charlie", password_hash="pw", role=role1)

    user.assign_role(role2)
    assert user.role_id == role2.id
    assert user.role == role2
    assert user.updated_at is not None


def test_user_assign_role_deactivated_user_raises() -> None:
    role1 = _make_role()
    role2 = _make_role()
    user = User.register(username="charlie", name="Charlie", password_hash="pw", role=role1)
    user.soft_delete()

    with pytest.raises(InactiveEntityError, match="призначити роль деактивованому користувачу"):
        user.assign_role(role2)


def test_user_assign_role_inactive_role_raises() -> None:
    role1 = _make_role()
    inactive_role = _make_role(is_active=False)
    user = User.register(username="charlie", name="Charlie", password_hash="pw", role=role1)

    with pytest.raises(InactiveRoleAssignmentError, match="призначити користувачу деактивовану роль"):
        user.assign_role(inactive_role)


def test_user_assign_role_demoting_super_admin_forbidden() -> None:
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    user = User(
        id=uuid7(),
        username="admin",
        name="Admin",
        password_hash="pw",
        role_id=admin_role.id,
        role=admin_role,
    )
    regular_role = _make_role()

    with pytest.raises(SuperAdminProtectionError, match="Пониження системної ролі SuperAdmin заборонене"):
        user.assign_role(regular_role)


def test_user_assign_role_promoting_to_super_admin_forbidden() -> None:
    role = _make_role()
    user = User.register(username="dave", name="Dave", password_hash="pw", role=role)
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")

    with pytest.raises(
        SuperAdminProtectionError, match="Підвищення звичайного користувача до ролі SuperAdmin заборонено"
    ):
        user.assign_role(admin_role)


def test_user_custom_permissions_lifecycle() -> None:
    role = _make_role()
    user = User.register(username="eva", name="Eva", password_hash="pw", role=role)

    p1 = _make_perm(PermissionCode.USERS_CREATE)
    p2 = _make_perm(PermissionCode.USERS_UPDATE)

    # set_custom_permissions
    user.set_custom_permissions([p1])
    assert user.custom_permissions == {p1}

    # grant_custom_permissions (adds p2, duplicate p1)
    user.grant_custom_permissions([p1, p2])
    assert user.custom_permissions == {p1, p2}

    # revoke_custom_permissions
    user.revoke_custom_permissions([p1.id])
    assert user.custom_permissions == {p2}


def test_user_custom_permissions_deactivated_raises() -> None:
    role = _make_role()
    user = User.register(username="eva", name="Eva", password_hash="pw", role=role)
    user.soft_delete()
    p = _make_perm(PermissionCode.USERS_READ)

    with pytest.raises(InactiveEntityError):
        user.set_custom_permissions([p])

    with pytest.raises(InactiveEntityError):
        user.grant_custom_permissions([p])

    with pytest.raises(InactiveEntityError):
        user.revoke_custom_permissions([p.id])


def test_user_change_username_success() -> None:
    role = _make_role()
    user = User.register(username="old.username", name="Frank", password_hash="pw", role=role)

    user.change_username("new.username")
    assert user.username == "new.username"
    assert user.updated_at is not None


def test_user_change_username_deactivated_raises() -> None:
    role = _make_role()
    user = User.register(username="frank", name="Frank", password_hash="pw", role=role)
    user.soft_delete()

    with pytest.raises(InactiveEntityError, match="змінити логін деактивованого користувача"):
        user.change_username("frank.new")


def test_user_update_profile_success() -> None:
    role1 = _make_role(name="Role 1")
    role2 = _make_role(name="Role 2")
    p = _make_perm(PermissionCode.USERS_READ)
    user = User.register(username="grace", name="Grace", password_hash="pw", role=role1)

    user.update_profile(
        name="Grace Hopper",
        username="grace.hopper",
        role=role2,
        custom_permissions=[p],
    )

    assert user.name == "Grace Hopper"
    assert user.username == "grace.hopper"
    assert user.role == role2
    assert user.custom_permissions == {p}
    assert user.updated_at is not None


def test_user_update_profile_deactivated_raises() -> None:
    role = _make_role()
    user = User.register(username="grace", name="Grace", password_hash="pw", role=role)
    user.soft_delete()

    with pytest.raises(InactiveEntityError, match="редагувати деактивованого користувача"):
        user.update_profile(name="Grace Hopper")


def test_user_soft_delete_success() -> None:
    role = _make_role()
    user = User.register(username="helen", name="Helen", password_hash="pw", role=role)
    assert user.is_active is True

    user.soft_delete()
    assert user.is_active is False
    assert user.deleted_at is not None


def test_user_soft_delete_super_admin_forbidden() -> None:
    admin_role = _make_role(code=SystemRole.SUPER_ADMIN.value, name="Super Admin")
    user = User(
        id=uuid7(),
        username="admin",
        name="Admin",
        password_hash="pw",
        role_id=admin_role.id,
        role=admin_role,
    )

    with pytest.raises(SuperAdminProtectionError, match="SuperAdmin заборонено деактивовувати"):
        user.soft_delete()


def test_user_soft_delete_already_inactive_raises() -> None:
    role = _make_role()
    user = User.register(username="helen", name="Helen", password_hash="pw", role=role)
    user.soft_delete()

    with pytest.raises(ResourceAlreadyInactiveException):
        user.soft_delete()
