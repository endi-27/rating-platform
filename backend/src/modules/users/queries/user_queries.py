from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import ColumnExpressionArgument, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

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
from src.core import (
    CurrentUser,
    CurrentUserRole,
    PermissionCode,
    SystemRole,
    logger,
    settings,
)
from src.infrastructure.db import BaseQueryService
from src.modules.users.infrastructure.models import PermissionModel, RoleModel, UserModel
from src.modules.users.queries.dto import (
    PermissionResponseDTO,
    RoleShortResponseDTO,
    UserDetailDTO,
    UserResponseDTO,
    UserShortDTO,
)
from src.modules.users.queries.filters import UserFilterDTO
from src.modules.users.queries.sorting import (
    UserShortSortField,
    UserSortField,
)


class UserQueryService(BaseQueryService):
    """Read Side CQRS сервіс для оптимізованих вибірок даних користувачів."""

    _USER_SORT_MAP: dict[UserSortField, ColumnExpressionArgument[Any]] = {
        UserSortField.CREATED_AT: UserModel.created_at,
        UserSortField.USERNAME: UserModel.username,
        UserSortField.NAME: UserModel.name,
        UserSortField.UPDATED_AT: UserModel.updated_at,
    }

    _USER_SHORT_SORT_MAP: dict[UserShortSortField, ColumnExpressionArgument[Any]] = {
        UserShortSortField.USERNAME: UserModel.username,
        UserShortSortField.NAME: UserModel.name,
    }

    def __init__(
        self,
        session: AsyncSession,
        redis: Redis[Any] | None = None,
    ) -> None:
        super().__init__(session=session)
        self._redis = redis

    # === Helper methods ===

    @staticmethod
    def _calculate_effective_permissions(
        role: RoleModel | None,
        custom_permissions: list[PermissionModel] | None,
    ) -> set[str]:
        """Єдине джерело істини розрахунку діючих прав доступу користувача."""
        if role and role.code == SystemRole.SUPER_ADMIN:
            return {p.value for p in PermissionCode}

        perms: set[str] = set()
        if role and role.permissions:
            perms.update(p.code for p in role.permissions)
        if custom_permissions:
            perms.update(p.code for p in custom_permissions)
        return perms

    @classmethod
    def _apply_filters(cls, stmt: Select[Any], filters: UserFilterDTO) -> Select[Any]:
        if not filters.include_inactive:
            stmt = stmt.where(UserModel.deleted_at.is_(None))

        if filters.ids:
            stmt = stmt.where(UserModel.id.in_(filters.ids))

        if filters.role_ids:
            stmt = stmt.where(UserModel.role_id.in_(filters.role_ids))

        if filters.roles:
            stmt = stmt.join(UserModel.role).where(RoleModel.code.in_(filters.roles))

        stmt = cls._apply_date_range(
            stmt,
            UserModel.created_at,
            date_from=filters.min_created_at,
            date_to=filters.max_created_at,
        )

        if filters.search:
            escaped = cls._escape_like(filters.search.strip().lower())
            search_pattern = f"%{escaped}%"
            stmt = stmt.where(
                or_(
                    func.lower(UserModel.username).like(search_pattern),
                    func.lower(UserModel.name).like(search_pattern),
                )
            )

        if filters.exclude_user_id:
            stmt = stmt.where(UserModel.id != filters.exclude_user_id)

        return stmt

    @staticmethod
    def _map_to_current_user_dto(orm: UserModel, effective_permissions: set[str]) -> CurrentUser:
        role_dto = CurrentUserRole(id=orm.role.id, code=orm.role.code, name=orm.role.name) if orm.role else None
        return CurrentUser(
            id=orm.id,
            username=orm.username,
            name=orm.name,
            role_id=orm.role_id,
            role=role_dto,
            effective_permissions=effective_permissions,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @classmethod
    def _map_to_detail_dto(cls, orm: UserModel) -> UserDetailDTO:
        perms = cls._calculate_effective_permissions(orm.role, orm.custom_permissions)

        role_dto = RoleShortResponseDTO(id=orm.role.id, code=orm.role.code, name=orm.role.name) if orm.role else None
        custom_perms_dto = [
            PermissionResponseDTO(
                id=p.id,
                code=PermissionCode(p.code),
                name=p.name,
                description=p.description,
                created_at=p.created_at,
            )
            for p in (orm.custom_permissions or [])
        ]

        return UserDetailDTO(
            id=orm.id,
            version=orm.version,
            username=orm.username,
            name=orm.name,
            role_id=orm.role_id,
            role=role_dto,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            deleted_at=orm.deleted_at,
            custom_permissions=custom_perms_dto,
            effective_permissions=perms,
        )

    @staticmethod
    def _map_to_response_dto(orm: UserModel) -> UserResponseDTO:
        role_dto = RoleShortResponseDTO(id=orm.role.id, code=orm.role.code, name=orm.role.name) if orm.role else None
        return UserResponseDTO(
            id=orm.id,
            version=orm.version,
            username=orm.username,
            name=orm.name,
            role_id=orm.role_id,
            role=role_dto,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            deleted_at=orm.deleted_at,
        )

    # === Main query methods ===

    async def get_by_id(self, user_id: UUID) -> UserResponseDTO | None:
        """Отримання базової інформації про користувача без кастомних дозволів."""
        stmt = select(UserModel).where(UserModel.id == user_id).options(joinedload(UserModel.role))
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._map_to_response_dto(orm)

    async def get_detail_by_id(self, user_id: UUID) -> UserDetailDTO | None:
        """Отримання повної інформації про користувача з роллю, дозволами ролі та персональними правами."""
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .options(
                selectinload(UserModel.role).selectinload(RoleModel.permissions),
                selectinload(UserModel.custom_permissions),
            )
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._map_to_detail_dto(orm)

    async def get_all(
        self,
        pagination: PaginationParams,
        sort: MultiSort[UserSortField],
        filters: UserFilterDTO,
        exclude_current_id: UUID | None = None,
    ) -> PaginatedResponse[UserResponseDTO]:
        """Отримання пагінованого списку користувачів із базовою інформацією."""
        stmt = select(UserModel).options(joinedload(UserModel.role))
        if exclude_current_id:
            stmt = stmt.where(UserModel.id != exclude_current_id)

        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        # Apply sorting and pagination with tie-breaker by id
        stmt = apply_sorting(stmt, sort, self._USER_SORT_MAP, UserModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_response_dto(u) for u in results]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)

    async def get_short_list(
        self,
        pagination: PaginationParams,
        sort: MultiSort[UserShortSortField],
        filters: UserFilterDTO,
        exclude_current_id: UUID | None = None,
    ) -> PaginatedResponse[UserShortDTO]:
        stmt: Any = select(UserModel.id, UserModel.username, UserModel.name)
        if exclude_current_id:
            stmt = stmt.where(UserModel.id != exclude_current_id)

        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        # Apply sorting and pagination with tie-breaker by id
        stmt = apply_sorting(stmt, sort, self._USER_SHORT_SORT_MAP, UserModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        rows = (await self._session.execute(stmt)).all()
        items = [UserShortDTO(id=r.id, username=r.username, name=r.name) for r in rows]

        return PaginatedResponse.create(items=items, total=total, pagination=pagination)

    def _get_current_user_cache_key(self, user_id: UUID) -> str:
        return f"{settings.cache.prefix}:{settings.cache.namespace.users}:{user_id}:current_user"

    async def get_cached_current_user(self, user_id: UUID) -> CurrentUser | None:
        """Отримання профілю поточного користувача з Redis кешуванням."""
        cache_key = self._get_current_user_cache_key(user_id)
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
                if cached:
                    return CurrentUser.model_validate_json(cached)
            except Exception as e:
                logger.warning("Помилка читання CurrentUser з Redis: {err}", err=str(e))

        # Запит до БД
        stmt = (
            select(UserModel)
            .options(
                selectinload(UserModel.role).selectinload(RoleModel.permissions),
                selectinload(UserModel.custom_permissions),
            )
            .where(UserModel.id == user_id)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()

        if not orm or orm.deleted_at is not None:
            return None

        perms = self._calculate_effective_permissions(orm.role, orm.custom_permissions)
        current_user = self._map_to_current_user_dto(orm, perms)

        # Cache-Aside: зберігаємо результат у Redis для прискорення наступних авторизацій
        if self._redis:
            try:
                await self._redis.set(cache_key, current_user.model_dump_json(), ex=settings.cache.expire)
            except Exception as e:
                logger.warning("Помилка запису CurrentUser в Redis: {err}", err=str(e))

        return current_user

    async def assess_deletion(self, user_id: UUID, current_user_id: UUID) -> DeletionAssessmentDTO:
        """Оцінка можливості видалення користувача (Hard vs Soft delete vs Blocked)."""
        stmt = select(UserModel).options(selectinload(UserModel.role)).where(UserModel.id == user_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        if not orm:
            return DeletionAssessmentDTO(
                resource_id=user_id,
                action=DeletionAction.BLOCKED,
                dependencies=[],
                restriction=DeletionRestrictionDTO(
                    code="not_found",
                    message="Користувача не знайдено.",
                ),
            )

        if orm.role and orm.role.code == SystemRole.SUPER_ADMIN:
            return DeletionAssessmentDTO(
                resource_id=user_id,
                action=DeletionAction.BLOCKED,
                dependencies=[],
                restriction=DeletionRestrictionDTO(
                    code="protected_resource",
                    message="Системного адміністратора SuperAdmin заборонено видаляти.",
                ),
            )

        if user_id == current_user_id:
            return DeletionAssessmentDTO(
                resource_id=user_id,
                action=DeletionAction.BLOCKED,
                dependencies=[],
                restriction=DeletionRestrictionDTO(
                    code="self_delete",
                    message="Ви не можете видалити власний обліковий запис.",
                ),
            )

        dependencies: list[DeletionRelationDTO] = []  # TODO: додати перевірки на залежності від інших сутностей
        action = DeletionAction.DEACTIVATE if dependencies else DeletionAction.HARD_DELETE
        return DeletionAssessmentDTO(
            resource_id=user_id,
            action=action,
            dependencies=dependencies,
            restriction=None,
        )
