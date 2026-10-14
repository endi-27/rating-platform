from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid6 import uuid7

from src.core import (
    AggregateRoot,
    IPasswordHasher,
    PermissionCode,
    SystemRole,
    default_password_hasher,
)
from src.modules.users.domain.exceptions import (
    InactiveRoleAssignmentError,
    SuperAdminProtectionError,
)
from src.modules.users.domain.models.permission import Permission
from src.modules.users.domain.models.role import Role


@dataclass(kw_only=True)
class User(AggregateRoot):
    """Доменний агрегат користувача системи."""

    username: str
    name: str
    password_hash: str
    role_id: UUID
    role: Role | None = None
    custom_permissions: set[Permission] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not isinstance(self.custom_permissions, set):
            self.custom_permissions = set(self.custom_permissions)

    @classmethod
    def register(
        cls,
        username: str,
        name: str,
        password_hash: str,
        role: Role,
        custom_permissions: Iterable[Permission] | None = None,
    ) -> "User":
        """
        Фабричний метод реєстрації нового користувача.
        Перевіряє сумісність ролі через інваріанти.
        """
        if not role.is_active:
            raise InactiveRoleAssignmentError("Неможливо зареєструвати користувача з деактивованою роллю.")
        if role.code == SystemRole.SUPER_ADMIN:
            raise SuperAdminProtectionError("Створення SuperAdmin користувачів заборонено системними правилами.")

        return cls(
            id=uuid7(),
            username=username,
            name=name,
            password_hash=password_hash,
            role_id=role.id,
            role=role,
            custom_permissions=set(custom_permissions or ()),
        )

    @property
    def is_super_admin(self) -> bool:
        """Перевірка чи має користувач системну роль SUPER_ADMIN."""
        return bool(self.role and self.role.code == SystemRole.SUPER_ADMIN)

    @property
    def custom_permission_ids(self) -> set[UUID]:
        """Множина ідентифікаторів персональних дозволів."""
        return {p.id for p in self.custom_permissions}

    @property
    def effective_permissions(self) -> set[str]:
        """
        Розрахунок фактичних прав доступу:
        Для SUPER_ADMIN повертає 100% існуючих системних дозволів.
        Для інших — об'єднання прав призначеної ролі та індивідуальних прав.
        """
        if self.is_super_admin:
            return {p.value for p in PermissionCode}

        perms: set[str] = set()
        if self.role:
            perms.update(p.code.value for p in self.role.permissions)
        perms.update(p.code.value for p in self.custom_permissions)

        return perms

    def has_permission(self, permission: str | PermissionCode) -> bool:
        """Перевіряє, чи має користувач конкретне право доступу."""
        code = permission.value if isinstance(permission, PermissionCode) else permission
        return code in self.effective_permissions

    def verify_password(self, plain_password: str, hasher: IPasswordHasher = default_password_hasher) -> bool:
        """Перевірка відповідності відкритого пароля збереженому хешу."""
        return hasher.verify(plain_password, self.password_hash)

    def change_password(self, new_password_hash: str) -> None:
        """Оновлення хешу пароля."""
        self.ensure_active("змінити пароль деактивованого користувача")
        self.password_hash = new_password_hash
        self.updated_at = datetime.now(UTC)

    def assign_role(self, role: Role) -> None:
        """Призначення нової ролі користувачу (інваріант захисту цілісності)."""
        self.ensure_active("призначити роль деактивованому користувачу")
        if not role.is_active:
            raise InactiveRoleAssignmentError("Неможливо призначити користувачу деактивовану роль.")
        if self.is_super_admin and role.code != SystemRole.SUPER_ADMIN:
            raise SuperAdminProtectionError("Пониження системної ролі SuperAdmin заборонене.")
        if not self.is_super_admin and role.code == SystemRole.SUPER_ADMIN:
            raise SuperAdminProtectionError("Підвищення звичайного користувача до ролі SuperAdmin заборонено.")
        self.role_id = role.id
        self.role = role
        self.updated_at = datetime.now(UTC)

    def set_custom_permissions(self, permissions: Iterable[Permission]) -> None:
        """Оновлення (повна заміна) персональних дозволів користувача."""
        self.ensure_active("змінити дозволи деактивованого користувача")
        self.custom_permissions = set(permissions)
        self.updated_at = datetime.now(UTC)

    def grant_custom_permissions(self, permissions: Iterable[Permission]) -> None:
        """Додавання персональних дозволів користувачу без дублювання."""
        self.ensure_active("змінити дозволи деактивованого користувача")
        self.custom_permissions.update(permissions)
        self.updated_at = datetime.now(UTC)

    def revoke_custom_permissions(self, permission_ids: set[UUID] | Sequence[UUID]) -> None:
        """Відкликання персональних дозволів користувача."""
        self.ensure_active("змінити дозволи деактивованого користувача")
        ids_set = set(permission_ids)
        self.custom_permissions = {p for p in self.custom_permissions if p.id not in ids_set}
        self.updated_at = datetime.now(UTC)

    def change_username(self, new_username: str) -> None:
        """Оновлення логіна користувача."""
        self.ensure_active("змінити логін деактивованого користувача")
        self.username = new_username
        self.updated_at = datetime.now(UTC)

    def update_profile(
        self,
        name: str,
        username: str | None = None,
        role: Role | None = None,
        custom_permissions: Iterable[Permission] | None = None,
    ) -> None:
        """Повне оновлення профілю користувача через методи домену."""
        self.ensure_active("редагувати деактивованого користувача")
        self.name = name
        if username is not None:
            self.change_username(username)
        if role is not None:
            self.assign_role(role)
        if custom_permissions is not None:
            self.set_custom_permissions(custom_permissions)
        self.updated_at = datetime.now(UTC)

    def soft_delete(self) -> None:
        """М'яке видалення (деактивація) користувача із захистом SuperAdmin."""
        if self.is_super_admin:
            raise SuperAdminProtectionError("Обліковий запис SuperAdmin заборонено деактивовувати.")
        super().soft_delete()
