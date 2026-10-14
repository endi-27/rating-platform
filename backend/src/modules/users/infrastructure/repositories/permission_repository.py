from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from src.core import PermissionCode
from src.infrastructure.db import SqlAlchemyBaseReadRepository
from src.modules.users.domain import IPermissionRepository, Permission
from src.modules.users.infrastructure.mappers import PermissionMapper
from src.modules.users.infrastructure.models import PermissionModel


class SqlAlchemyPermissionRepository(SqlAlchemyBaseReadRepository[Permission, PermissionModel], IPermissionRepository):
    """SQLAlchemy реалізація репозиторію прав доступу (виключно Read-методи)."""

    _model_cls = PermissionModel
    _mapper = PermissionMapper

    async def get_by_code(self, code: str | PermissionCode) -> Permission | None:
        raw_code = code.value if isinstance(code, PermissionCode) else code
        stmt = select(PermissionModel).where(PermissionModel.code == raw_code)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return PermissionMapper.to_domain(orm) if orm else None

    async def get_by_ids(self, permission_ids: Sequence[UUID]) -> list[Permission]:
        if not permission_ids:
            return []
        stmt = select(PermissionModel).where(PermissionModel.id.in_(permission_ids))
        result = await self._session.execute(stmt)
        return [PermissionMapper.to_domain(orm) for orm in result.scalars().all()]

    async def get_all(self) -> list[Permission]:
        stmt = select(PermissionModel).order_by(PermissionModel.code)
        result = await self._session.execute(stmt)
        return [PermissionMapper.to_domain(orm) for orm in result.scalars().all()]
