from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.api.schemas.sorting import MultiSort, apply_sorting
from src.infrastructure.db.queries.base import BaseQueryService
from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.infrastructure.models.review_model import ReviewModel
from src.modules.reviews.queries.dto import ReviewResponseDTO
from src.modules.reviews.queries.filters import ReviewFilterDTO
from src.modules.reviews.queries.sorting import ReviewSortField


class ReviewQueryService(BaseQueryService):
    """Read Side CQRS сервіс для оптимізованих вибірок відгуків об'єктів."""

    _REVIEW_SORT_MAP: dict[ReviewSortField, ColumnExpressionArgument[Any]] = {
        ReviewSortField.CREATED_AT: ReviewModel.created_at,
        ReviewSortField.SCORE: ReviewModel.score,
        ReviewSortField.HELPFUL_COUNT: ReviewModel.helpful_count,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)

    # === Helper mapping methods ===

    @staticmethod
    def _map_to_review_dto(orm: ReviewModel) -> ReviewResponseDTO:
        return ReviewResponseDTO(
            id=orm.id,
            target_id=orm.target_id,
            user_id=orm.user_id,
            score=orm.score,
            title=orm.title,
            content=orm.content,
            status=ReviewStatus(orm.status),
            helpful_count=orm.helpful_count,
            unhelpful_count=orm.unhelpful_count,
            version=orm.version,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @classmethod
    def _apply_filters(cls, stmt: Select[Any], filters: ReviewFilterDTO) -> Select[Any]:
        # Інваріант шардингу: обов'язкова фільтрація за target_id
        stmt = stmt.where(ReviewModel.target_id == filters.target_id)
        stmt = stmt.where(ReviewModel.deleted_at.is_(None))

        if filters.status:
            stmt = stmt.where(ReviewModel.status == filters.status)

        if filters.score is not None:
            stmt = stmt.where(ReviewModel.score == filters.score)

        if filters.min_score is not None:
            stmt = stmt.where(ReviewModel.score >= filters.min_score)

        if filters.author_id is not None:
            stmt = stmt.where(ReviewModel.user_id == filters.author_id)

        return stmt

    # === Query methods ===

    async def get_by_id(self, review_id: UUID) -> ReviewResponseDTO | None:
        """Отримання конкретного відгуку за його ID."""
        stmt = select(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.deleted_at.is_(None))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return self._map_to_review_dto(orm) if orm is not None else None

    async def list_by_target(
        self,
        target_id: UUID,
        pagination: PaginationParams,
        sort: MultiSort[ReviewSortField],
        filters: ReviewFilterDTO,
    ) -> PaginatedResponse[ReviewResponseDTO]:
        """Пагіноване отримання стрічки відгуків конкретного об'єкта (з фільтрацією за target_id під шардинг)."""
        # Гарантуємо відповідність target_id у фільтрі
        filters.target_id = target_id

        stmt = select(ReviewModel)
        stmt = self._apply_filters(stmt, filters)

        total = await self._count_total(stmt)

        stmt = apply_sorting(stmt, sort, self._REVIEW_SORT_MAP, ReviewModel.id)
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)

        results = (await self._session.execute(stmt)).scalars().all()
        items = [self._map_to_review_dto(r) for r in results]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)
