from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reviews.domain.interfaces import IReviewVoteRepository
from src.modules.reviews.domain.models.review_vote import ReviewVote
from src.modules.reviews.infrastructure.mappers.review_vote_mapper import ReviewVoteMapper
from src.modules.reviews.infrastructure.models.review_vote_model import ReviewVoteModel


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
