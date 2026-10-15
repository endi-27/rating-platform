from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reviews.domain.interfaces import ITargetRatingRepository
from src.modules.reviews.domain.models.target_rating import TargetRating
from src.modules.reviews.infrastructure.mappers.target_rating_mapper import TargetRatingMapper
from src.modules.reviews.infrastructure.models.target_rating_model import TargetRatingModel


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
