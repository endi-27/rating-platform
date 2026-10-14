from collections.abc import Sequence
from uuid import UUID

from src.core import PermissionCode
from src.modules.users.domain import (
    IPermissionRepository,
    Permission,
)


class FakePermissionRepository(IPermissionRepository):
    def __init__(self, initial_permissions: list[Permission] | None = None) -> None:
        self.permissions: dict[UUID, Permission] = {p.id: p for p in (initial_permissions or [])}

    async def get_by_id(self, permission_id: UUID) -> Permission | None:
        return self.permissions.get(permission_id)

    async def get_by_code(self, code: str | PermissionCode) -> Permission | None:
        val = code.value if isinstance(code, PermissionCode) else code.lower()
        for p in self.permissions.values():
            if p.code == val:
                return p
        return None

    async def get_by_ids(self, permission_ids: Sequence[UUID]) -> list[Permission]:
        return [self.permissions[pid] for pid in permission_ids if pid in self.permissions]

    async def get_all(self) -> list[Permission]:
        return list(self.permissions.values())
