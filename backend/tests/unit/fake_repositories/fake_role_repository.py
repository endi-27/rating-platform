from uuid import UUID

from src.core import ResourceLockedException
from src.modules.users.domain import IRoleRepository, Role


class FakeRoleRepository(IRoleRepository):
    def __init__(self, initial_roles: list[Role] | None = None) -> None:
        self.roles: dict[UUID, Role] = {r.id: r for r in (initial_roles or [])}
        self.locked_role_ids: set[UUID] = set()

    async def get_by_id(self, role_id: UUID, /) -> Role | None:
        return self.roles.get(role_id)

    async def get_by_code(self, code: str) -> Role | None:
        for r in self.roles.values():
            if r.code.lower() == code.lower():
                return r
        return None

    async def exists_by_code(self, code: str) -> bool:
        return any(r.code.lower() == code.lower() for r in self.roles.values())

    async def save(self, role: Role) -> None:
        self.roles[role.id] = role

    async def delete_by_id(self, role_id: UUID) -> bool:
        if role_id in self.locked_role_ids:
            raise ResourceLockedException(
                "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."
            )
        return self.roles.pop(role_id, None) is not None
