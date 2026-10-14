from collections.abc import Sequence
from uuid import UUID

from src.core import IUnitOfWork
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.interfaces import IReviewRepository, ITargetRepository
from src.modules.reviews.domain.models import Review


class ListTargetReviewsUseCase:
    """Use Case пагінованого отримання списку відгуків конкретного об'єкта (з фільтрацією за target_id під шардинг)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        review_repo: IReviewRepository,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._review_repo = review_repo

    async def execute(
        self,
        *,
        target_id: UUID,
        status: str = "published",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Review], int]:
        offset = (page - 1) * page_size
        async with self._uow:
            target = await self._target_repo.get_by_id(target_id)
            if target is None:
                raise TargetNotFoundException(target_id)

            reviews = await self._review_repo.list_by_target(
                target_id,
                status=status,
                limit=page_size,
                offset=offset,
            )
            total = await self._review_repo.count_by_target(target_id, status=status)
            return reviews, total
