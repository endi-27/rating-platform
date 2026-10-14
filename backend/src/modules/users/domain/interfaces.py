from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from src.core import IUnitOfWork, PermissionCode
from src.modules.users.domain.models import Permission, Role, User


class IUserRepository(Protocol):
    """Протокол репозиторію користувачів для Write-пайплайну."""

    async def get_by_id(self, user_id: UUID, /) -> User | None: ...

    async def get_by_username(self, username: str) -> User | None: ...

    async def save(self, user: User, /) -> None: ...

    async def delete_by_id(self, user_id: UUID, /) -> bool: ...

    async def exists_by_username(self, username: str, *, exclude_user_id: UUID | None = None) -> bool: ...


class IRoleRepository(Protocol):
    """Протокол репозиторію ролей для Write-пайплайну."""

    async def get_by_id(self, role_id: UUID, /) -> Role | None: ...

    async def get_by_code(self, code: str) -> Role | None: ...

    async def save(self, role: Role, /) -> None: ...

    async def delete_by_id(self, role_id: UUID, /) -> bool: ...

    async def exists_by_code(self, code: str) -> bool: ...


class IPermissionRepository(Protocol):
    """Протокол репозиторію системних прав (тільки Read-методи)."""

    async def get_by_id(self, permission_id: UUID) -> Permission | None: ...

    async def get_by_code(self, code: str | PermissionCode) -> Permission | None: ...

    async def get_by_ids(self, permission_ids: Sequence[UUID]) -> list[Permission]: ...

    async def get_all(self) -> list[Permission]: ...


class IAuthSessionGateway(Protocol):
    """Протокол взаємодії з модулем auth для управління активними сесіями користувачів."""

    async def revoke_all_user_sessions(
        self,
        user_id: UUID,
        *,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        external_uow: IUnitOfWork | None = None,
    ) -> None:
        """Анулювання всіх активних сесій (refresh токенів) користувача."""
        ...
