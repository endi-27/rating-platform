from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, func, or_, select

from src.api import (
    MultiSort,
    PaginatedResponse,
    PaginationParams,
    apply_sorting,
)
from src.core import PermissionCode
from src.infrastructure.db import BaseQueryService
from src.modules.users.infrastructure.models import PermissionModel
from src.modules.users.queries.dto import PermissionResponseDTO
from src.modules.users.queries.filters import PermissionFilterDTO
from src.modules.users.queries.sorting import PermissionSortField


class PermissionQueryService(BaseQueryService):
    """Read Side CQRS сервіс для системних дозволів (Permissions). Виключно читання."""

    _SORT_MAP: dict[PermissionSortField, ColumnExpressionArgument[Any]] = {
        PermissionSortField.CODE: PermissionModel.code,
        PermissionSortField.NAME: PermissionModel.name,
        PermissionSortField.CREATED_AT: PermissionModel.created_at,
    }

    # === Helper methods ===

    @classmethod
    def _apply_filters(cls, stmt: Select[Any], filters: PermissionFilterDTO) -> Select[Any]:
        if filters.ids:
            stmt = stmt.where(PermissionModel.id.in_(filters.ids))

        if filters.codes:
            stmt = stmt.where(PermissionModel.code.in_(filters.codes))

        if filters.search:
            escaped = cls._escape_like(filters.search.strip().lower())
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                or_(
                    func.lower(PermissionModel.name).like(pattern),
                    func.lower(PermissionModel.code).like(pattern),
                )
            )

        return stmt

    @staticmethod
    def _map_to_dto(orm: PermissionModel) -> PermissionResponseDTO:
        return PermissionResponseDTO(
            id=orm.id,
            code=PermissionCode(orm.code),
            name=orm.name,
            description=orm.description,
            created_at=orm.created_at,
        )

    # === Main query methods ===

    async def get_by_id(self, permission_id: UUID) -> PermissionResponseDTO | None:
        orm = await self._session.get(PermissionModel, permission_id)
        return self._map_to_dto(orm) if orm else None

    async def get_by_code(self, code: str) -> PermissionResponseDTO | None:
        stmt = select(PermissionModel).where(PermissionModel.code == code.lower())
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._map_to_dto(orm) if orm else None

    async def get_all(
        self,
        pagination: PaginationParams,
        sort: MultiSort[PermissionSortField],
        filters: PermissionFilterDTO,
    ) -> PaginatedResponse[PermissionResponseDTO]:
        stmt = select(PermissionModel)
        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        stmt = apply_sorting(stmt, sort, self._SORT_MAP, PermissionModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_dto(p) for p in results]

        return PaginatedResponse.create(items=items, total=total, pagination=pagination)
