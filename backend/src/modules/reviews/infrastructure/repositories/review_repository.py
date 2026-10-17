from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from src.infrastructure.db.repositories.base_crud_repository import SqlAlchemyBaseCrudRepository
from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.domain.interfaces import IReviewRepository
from src.modules.reviews.domain.models.review import Review
from src.modules.reviews.infrastructure.mappers.review_mapper import ReviewMapper
from src.modules.reviews.infrastructure.models.review_model import ReviewModel


class SqlAlchemyReviewRepository(SqlAlchemyBaseCrudRepository[Review, ReviewModel], IReviewRepository):
    """SQLAlchemy реалізація репозиторію відгуків (Review)."""

    _model_cls = ReviewModel
    _mapper = ReviewMapper

    async def save(self, review: Review, /) -> None:
        orm = await self._session.get(ReviewModel, review.id)
        if orm is None:
            orm = ReviewMapper.to_orm(review)
            self._session.add(orm)
        else:
            ReviewMapper.update_to_orm(orm, review)
        await self._session.flush()
        review.version = orm.version

    async def get_by_target_and_user(self, target_id: UUID, user_id: UUID, /) -> Review | None:
        stmt = select(ReviewModel).where(
            ReviewModel.target_id == target_id,
            ReviewModel.user_id == user_id,
            ReviewModel.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return ReviewMapper.to_domain(orm) if orm is not None else None

    async def list_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Review]:
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.target_id == target_id,
                ReviewModel.status == status,
                ReviewModel.deleted_at.is_(None),
            )
            .order_by(ReviewModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._session.execute(stmt)
        return [ReviewMapper.to_domain(orm) for orm in res.scalars().all()]

    async def count_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ReviewModel)
            .where(
                ReviewModel.target_id == target_id,
                ReviewModel.status == status,
                ReviewModel.deleted_at.is_(None),
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one() or 0
