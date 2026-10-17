from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.api.schemas.sorting import MultiSort, apply_sorting
from src.infrastructure.db.queries.base import BaseQueryService
from src.modules.reviews.infrastructure.models.target_model import TargetModel
from src.modules.reviews.infrastructure.models.target_rating_model import TargetRatingModel
from src.modules.reviews.queries.dto import TargetRatingResponseDTO, TargetResponseDTO
from src.modules.reviews.queries.filters import TargetFilterDTO
from src.modules.reviews.queries.sorting import TargetSortField


class TargetQueryService(BaseQueryService):
    """Read Side CQRS сервіс для оптимізованих вибірок даних об'єктів оцінювання."""

    _TARGET_SORT_MAP: dict[TargetSortField, ColumnExpressionArgument[Any]] = {
        TargetSortField.CREATED_AT: TargetModel.created_at,
        TargetSortField.TITLE: TargetModel.title,
        TargetSortField.AVERAGE_SCORE: TargetRatingModel.average_score,
        TargetSortField.BAYESIAN_SCORE: TargetRatingModel.bayesian_score,
        TargetSortField.TOTAL_REVIEWS: TargetRatingModel.total_reviews,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)

    # === Helper mapping methods ===

    @staticmethod
    def _map_to_rating_dto(orm: TargetRatingModel | None) -> TargetRatingResponseDTO | None:
        if orm is None:
            return None
        return TargetRatingResponseDTO(
            total_reviews=orm.total_reviews,
            average_score=orm.average_score,
            bayesian_score=orm.bayesian_score,
            star_1_count=orm.star_1_count,
            star_2_count=orm.star_2_count,
            star_3_count=orm.star_3_count,
            star_4_count=orm.star_4_count,
            star_5_count=orm.star_5_count,
            last_calculated_at=orm.last_calculated_at,
        )

    @classmethod
    def _map_to_target_dto(cls, orm: TargetModel) -> TargetResponseDTO:
        rating_dto = cls._map_to_rating_dto(orm.rating) if orm.rating else None
        return TargetResponseDTO(
            id=orm.id,
            slug=orm.slug,
            title=orm.title,
            category=orm.category,
            description=orm.description,
            metadata=dict(orm.metadata_ or {}),
            is_active=orm.deleted_at is None,
            version=orm.version,
            rating=rating_dto,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @classmethod
    def _apply_filters(cls, stmt: Select[Any], filters: TargetFilterDTO) -> Select[Any]:
        if not filters.include_inactive:
            stmt = stmt.where(TargetModel.deleted_at.is_(None))

        if filters.category:
            stmt = stmt.where(TargetModel.category == filters.category.strip().lower())

        if filters.search:
            escaped = cls._escape_like(filters.search.strip().lower())
            search_pattern = f"%{escaped}%"
            stmt = stmt.where(
                or_(
                    func.lower(TargetModel.title).like(search_pattern),
                    func.lower(TargetModel.slug).like(search_pattern),
                )
            )

        if filters.min_rating is not None:
            stmt = stmt.where(TargetRatingModel.average_score >= filters.min_rating)

        return stmt

    # === Query methods ===

    async def get_by_id(self, target_id: UUID) -> TargetResponseDTO | None:
        """Отримання об'єкта за його UUID разом зі знімком рейтингу."""
        stmt = (
            select(TargetModel)
            .where(TargetModel.id == target_id, TargetModel.deleted_at.is_(None))
            .options(joinedload(TargetModel.rating))
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._map_to_target_dto(orm) if orm is not None else None

    async def get_by_slug(self, slug: str) -> TargetResponseDTO | None:
        """Отримання об'єкта за його slug разом зі знімком рейтингу."""
        stmt = (
            select(TargetModel)
            .where(TargetModel.slug == slug.strip().lower(), TargetModel.deleted_at.is_(None))
            .options(joinedload(TargetModel.rating))
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._map_to_target_dto(orm) if orm is not None else None

    async def get_by_id_or_slug(self, id_or_slug: UUID | str) -> TargetResponseDTO | None:
        """Універсальне отримання об'єкта за UUID або рядковим slug."""
        if isinstance(id_or_slug, UUID):
            return await self.get_by_id(id_or_slug)

        try:
            parsed_uuid = UUID(id_or_slug)
            found = await self.get_by_id(parsed_uuid)
            if found:
                return found
        except ValueError:
            pass

        return await self.get_by_slug(str(id_or_slug))

    async def get_target_rating(self, target_id: UUID) -> TargetRatingResponseDTO | None:
        """Отримання виключно агрегованого рейтингу об'єкта."""
        stmt = select(TargetRatingModel).where(TargetRatingModel.target_id == target_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._map_to_rating_dto(orm)

    async def get_all(
        self,
        pagination: PaginationParams,
        sort: MultiSort[TargetSortField],
        filters: TargetFilterDTO,
    ) -> PaginatedResponse[TargetResponseDTO]:
        """Отримання пагінованого списку об'єктів оцінювання з фільтрами та сортуванням."""
        stmt = (
            select(TargetModel)
            .outerjoin(TargetRatingModel, TargetModel.id == TargetRatingModel.target_id)
            .options(contains_eager(TargetModel.rating))
        )

        stmt = self._apply_filters(stmt, filters)
        total = await self._count_total(stmt)

        stmt = apply_sorting(stmt, sort, self._TARGET_SORT_MAP, TargetModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_target_dto(t) for t in results]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)
