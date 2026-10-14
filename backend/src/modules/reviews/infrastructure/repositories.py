from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.repositories.base_crud_repository import SqlAlchemyBaseCrudRepository
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    IReviewVoteRepository,
    ITargetRatingRepository,
    ITargetRepository,
)
from src.modules.reviews.domain.models import Review, ReviewVote, Target, TargetRating
from src.modules.reviews.infrastructure.mappers import (
    ReviewMapper,
    ReviewVoteMapper,
    TargetMapper,
    TargetRatingMapper,
)
from src.modules.reviews.infrastructure.models import (
    ReviewModel,
    ReviewVoteModel,
    TargetModel,
    TargetRatingModel,
)


class SqlAlchemyTargetRepository(SqlAlchemyBaseCrudRepository[Target, TargetModel], ITargetRepository):
    """SQLAlchemy реалізація репозиторію об'єктів оцінювання (Target)."""

    _model_cls = TargetModel
    _mapper = TargetMapper

    async def save(self, target: Target, /) -> None:
        orm = await self._session.get(TargetModel, target.id)
        if orm is None:
            orm = TargetMapper.to_orm(target)
            self._session.add(orm)
        else:
            TargetMapper.update_to_orm(orm, target)
        await self._session.flush()

    async def get_by_slug(self, slug: str, /) -> Target | None:
        stmt = select(TargetModel).where(
            TargetModel.slug == slug.strip().lower(),
            TargetModel.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return TargetMapper.to_domain(orm) if orm is not None else None

    async def exists_by_slug(self, slug: str, /, exclude_id: UUID | None = None) -> bool:
        stmt = select(1).where(
            TargetModel.slug == slug.strip().lower(),
            TargetModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            stmt = stmt.where(TargetModel.id != exclude_id)
        stmt = stmt.limit(1)
        res = await self._session.execute(stmt)
        return bool(res.scalar() is not None)

    async def list_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Target]:
        stmt = select(TargetModel).where(TargetModel.deleted_at.is_(None))

        if category:
            stmt = stmt.where(TargetModel.category == category.strip().lower())
        if search:
            clean_search = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                (func.lower(TargetModel.title).ilike(clean_search)) | (func.lower(TargetModel.slug).ilike(clean_search))
            )

        stmt = stmt.order_by(TargetModel.created_at.desc()).limit(limit).offset(offset)
        res = await self._session.execute(stmt)
        return [TargetMapper.to_domain(orm) for orm in res.scalars().all()]

    async def count_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(TargetModel).where(TargetModel.deleted_at.is_(None))

        if category:
            stmt = stmt.where(TargetModel.category == category.strip().lower())
        if search:
            clean_search = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                (func.lower(TargetModel.title).ilike(clean_search)) | (func.lower(TargetModel.slug).ilike(clean_search))
            )

        res = await self._session.execute(stmt)
        return res.scalar_one() or 0


class SqlAlchemyTargetRatingRepository(ITargetRatingRepository):
    """SQLAlchemy реалізація репозиторію знімків рейтингу (TargetRating)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, rating: TargetRating, /) -> None:
        orm = await self._session.get(TargetRatingModel, rating.target_id)
        if orm is None:
            orm = TargetRatingMapper.to_orm(rating)
            self._session.add(orm)
        else:
            TargetRatingMapper.update_to_orm(orm, rating)
        await self._session.flush()

    async def get_by_target_id(self, target_id: UUID, /) -> TargetRating | None:
        orm = await self._session.get(TargetRatingModel, target_id)
        return TargetRatingMapper.to_domain(orm) if orm is not None else None

    async def get_global_mean_score(self) -> Decimal:
        """Обчислення середнього балу по системі для формули Байєса."""
        stmt = select(func.avg(TargetRatingModel.average_score)).where(TargetRatingModel.total_reviews > 0)
        res = await self._session.execute(stmt)
        val = res.scalar()
        if val is None:
            return Decimal("3.50")
        return Decimal(str(round(float(val), 2)))


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
        status: str = "published",
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

    async def count_by_target(self, target_id: UUID, *, status: str = "published") -> int:
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


class SqlAlchemyReviewVoteRepository(IReviewVoteRepository):
    """SQLAlchemy реалізація репозиторію голосів корисності (ReviewVote)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, vote: ReviewVote, /) -> None:
        orm = await self._session.get(ReviewVoteModel, vote.id)
        if orm is None:
            orm = ReviewVoteMapper.to_orm(vote)
            self._session.add(orm)
        else:
            ReviewVoteMapper.update_to_orm(orm, vote)
        await self._session.flush()

    async def get_by_review_and_user(self, review_id: UUID, user_id: UUID, /) -> ReviewVote | None:
        stmt = select(ReviewVoteModel).where(
            ReviewVoteModel.review_id == review_id,
            ReviewVoteModel.user_id == user_id,
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return ReviewVoteMapper.to_domain(orm) if orm is not None else None

    async def delete_by_id(self, vote_id: UUID, /) -> bool:
        orm = await self._session.get(ReviewVoteModel, vote_id)
        if orm is not None:
            await self._session.delete(orm)
            await self._session.flush()
            return True
        return False
