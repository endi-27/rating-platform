from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid6 import uuid7

from src.core import AggregateRoot, SystemRole
from src.modules.users.domain.exceptions import SuperAdminProtectionError
from src.modules.users.domain.models.permission import Permission


@dataclass(kw_only=True)
class Role(AggregateRoot):
    """Доменна сутність ролі користувача."""

    code: str
    name: str
    description: str | None = None
    permissions: set[Permission] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not isinstance(self.permissions, set):
            self.permissions = set(self.permissions)

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        description: str | None = None,
        permissions: Iterable[Permission] | None = None,
    ) -> "Role":
        """Фабричний метод створення нової ролі з валідацією системних інваріантів."""
        normalized_code = code.lower()
        if normalized_code == SystemRole.SUPER_ADMIN:
            raise SuperAdminProtectionError("Створення системної ролі super_admin заборонено системними правилами.")

        return cls(
            id=uuid7(),
            code=normalized_code,
            name=name,
            description=description,
            permissions=set(permissions or ()),
        )

    @property
    def is_super_admin(self) -> bool:
        """Перевірка чи є роль системною SUPER_ADMIN."""
        return self.code == SystemRole.SUPER_ADMIN

    @property
    def is_system_role(self) -> bool:
        """Перевірка чи є роль системною (SUPER_ADMIN)."""
        return self.is_super_admin

    @property
    def permission_ids(self) -> set[UUID]:
        """Множина ідентифікаторів дозволів ролі."""
        return {p.id for p in self.permissions}

    def update_details(
        self,
        name: str,
        description: str | None,
        permissions: Iterable[Permission],
    ) -> None:
        """Оновлення основних реквізитів ролі (Full Update)."""
        self.ensure_active("редагувати деактивовану роль", "Спочатку відновіть її.")
        if self.is_super_admin:
            raise SuperAdminProtectionError("Системну роль SUPER_ADMIN заборонено редагувати.")

        self.name = name
        self.description = description
        self.set_permissions(permissions)
        self.updated_at = datetime.now(UTC)

    def set_permissions(self, permissions: Iterable[Permission]) -> None:
        """Оновлення (повна заміна) множини прав ролі."""
        if self.is_super_admin:
            raise SuperAdminProtectionError("Права ролі SUPER_ADMIN не можуть бути змінені.")
        self.permissions = set(permissions)
        self.updated_at = datetime.now(UTC)

    def grant_permissions(self, permissions: Iterable[Permission]) -> None:
        """Додавання прав до ролі без дублювання."""
        self.ensure_active("змінити дозволи деактивованої ролі", "Спочатку відновіть її.")
        if self.is_super_admin:
            raise SuperAdminProtectionError("Права ролі SUPER_ADMIN не можуть бути змінені.")
        self.permissions.update(permissions)
        self.updated_at = datetime.now(UTC)

    def revoke_permissions(self, permission_ids: set[UUID] | Sequence[UUID]) -> None:
        """Відкликання прав у ролі."""
        self.ensure_active("змінити дозволи деактивованої ролі", "Спочатку відновіть її.")
        if self.is_super_admin:
            raise SuperAdminProtectionError("Права ролі SUPER_ADMIN не можуть бути змінені.")
        ids_set = set(permission_ids)
        self.permissions = {p for p in self.permissions if p.id not in ids_set}
        self.updated_at = datetime.now(UTC)

    def soft_delete(self) -> None:
        """М'яке видалення (деактивація) ролі із захистом системного SuperAdmin."""
        if self.is_super_admin:
            raise SuperAdminProtectionError("Системну роль SUPER_ADMIN заборонено деактивовувати чи видаляти.")
        super().soft_delete()
