from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, func, or_, select
from sqlalchemy.orm import selectinload

from src.api import (
    DeletionAction,
    DeletionAssessmentDTO,
    DeletionRelationDTO,
    DeletionRestrictionDTO,
    MultiSort,
    PaginatedResponse,
    PaginationParams,
    apply_sorting,
)
from src.core import PermissionCode, SystemRole
from src.infrastructure.db import BaseQueryService
from src.modules.users.infrastructure.models import RoleModel, UserModel
from src.modules.users.queries.dto import (
    PermissionResponseDTO,
    RoleDetailDTO,
    RoleResponseDTO,
)
from src.modules.users.queries.filters import RoleFilterDTO
from src.modules.users.queries.sorting import RoleSortField


class RoleQueryService(BaseQueryService):
    """Read Side CQRS сервіс для оптимізованих вибірок даних ролей."""

    _ROLE_SORT_MAP: dict[RoleSortField, ColumnExpressionArgument[Any]] = {
        RoleSortField.CREATED_AT: RoleModel.created_at,
        RoleSortField.NAME: RoleModel.name,
        RoleSortField.CODE: RoleModel.code,
        RoleSortField.UPDATED_AT: RoleModel.updated_at,
    }

    # === Helper methods ===

    @classmethod
    def _apply_filters(cls, stmt: Select[Any], filters: RoleFilterDTO) -> Select[Any]:
        if not filters.include_inactive:
            stmt = stmt.where(RoleModel.deleted_at.is_(None))

        if filters.ids:
            stmt = stmt.where(RoleModel.id.in_(filters.ids))

        if filters.codes:
            stmt = stmt.where(RoleModel.code.in_(filters.codes))

        if filters.search:
            escaped = cls._escape_like(filters.search.strip().lower())
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                or_(
                    func.lower(RoleModel.name).like(pattern),
                    func.lower(RoleModel.code).like(pattern),
                )
            )

        return stmt

    @staticmethod
    def _map_to_detail_dto(orm: RoleModel) -> RoleDetailDTO:
        perms_dto = [
            PermissionResponseDTO(
                id=p.id,
                code=PermissionCode(p.code),
                name=p.name,
                description=p.description,
                created_at=p.created_at,
            )
            for p in (orm.permissions or [])
        ]
        return RoleDetailDTO(
            id=orm.id,
            version=orm.version,
            code=orm.code,
            name=orm.name,
            description=orm.description,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            deleted_at=orm.deleted_at,
            permissions=perms_dto,
        )

    @staticmethod
    def _map_to_response_dto(orm: RoleModel) -> RoleResponseDTO:
        return RoleResponseDTO(
            id=orm.id,
            version=orm.version,
            code=orm.code,
            name=orm.name,
            description=orm.description,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            deleted_at=orm.deleted_at,
        )

    # === Main query methods ===

    async def get_by_id(self, role_id: UUID) -> RoleResponseDTO | None:
        """Отримання базової інформації про роль без списку дозволів."""
        stmt = select(RoleModel).where(RoleModel.id == role_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._map_to_response_dto(orm)

    async def get_detail_by_id(self, role_id: UUID) -> RoleDetailDTO | None:
        """Отримання детальної інформації про роль разом із прив'язаними дозволами."""
        stmt = select(RoleModel).where(RoleModel.id == role_id).options(selectinload(RoleModel.permissions))
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._map_to_detail_dto(orm)

    async def get_all(
        self,
        pagination: PaginationParams,
        sort: MultiSort[RoleSortField],
        filters: RoleFilterDTO,
    ) -> PaginatedResponse[RoleResponseDTO]:
        """Отримання списку ролей без списку дозволів."""
        stmt = select(RoleModel).where(RoleModel.code != SystemRole.SUPER_ADMIN)
        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        stmt = apply_sorting(stmt, sort, self._ROLE_SORT_MAP, RoleModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_response_dto(r) for r in results]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)

    async def get_all_details(
        self,
        pagination: PaginationParams,
        sort: MultiSort[RoleSortField],
        filters: RoleFilterDTO,
    ) -> PaginatedResponse[RoleDetailDTO]:
        """Отримання списку ролей разом із підвантаженими дозволами."""
        stmt = (
            select(RoleModel)
            .where(RoleModel.code != SystemRole.SUPER_ADMIN)
            .options(selectinload(RoleModel.permissions))
        )
        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        stmt = apply_sorting(stmt, sort, self._ROLE_SORT_MAP, RoleModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_detail_dto(r) for r in results]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)

    async def assess_deletion(self, role_id: UUID) -> DeletionAssessmentDTO:
        stmt = select(RoleModel).where(RoleModel.id == role_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        if not orm:
            return DeletionAssessmentDTO(
                resource_id=role_id,
                action=DeletionAction.BLOCKED,
                dependencies=[],
                restriction=DeletionRestrictionDTO(
                    code="not_found",
                    message="Роль не знайдено.",
                ),
            )

        if orm.code == SystemRole.SUPER_ADMIN:
            return DeletionAssessmentDTO(
                resource_id=role_id,
                action=DeletionAction.BLOCKED,
                dependencies=[],
                restriction=DeletionRestrictionDTO(
                    code="protected_resource",
                    message="Системну роль SUPER_ADMIN заборонено видаляти або деактивовувати.",
                ),
            )

        # Перевірка користувачів, прив'язаних до цієї ролі (активних та м'яко видалених через RESTRICT у БД)
        count_stmt = select(func.count(UserModel.id)).where(UserModel.role_id == role_id)
        user_count = (await self._session.execute(count_stmt)).scalar_one()

        dependencies = [DeletionRelationDTO(entity_type="users", count=user_count)] if user_count > 0 else []

        action = DeletionAction.DEACTIVATE if dependencies else DeletionAction.HARD_DELETE

        return DeletionAssessmentDTO(
            resource_id=role_id,
            action=action,
            dependencies=dependencies,
            restriction=None,
        )
