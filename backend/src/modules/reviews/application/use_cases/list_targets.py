from collections.abc import Sequence

from src.core import IUnitOfWork
from src.modules.reviews.domain.interfaces import ITargetRatingRepository, ITargetRepository
from src.modules.reviews.domain.models import Target, TargetRating


class ListTargetsUseCase:
    """Use Case пагінованого перегляду каталогу об'єктів оцінювання з їхніми рейтингами."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        rating_repo: ITargetRatingRepository,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._rating_repo = rating_repo

    async def execute(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[tuple[Target, TargetRating | None]], int]:
        offset = (page - 1) * page_size
        async with self._uow:
            targets = await self._target_repo.list_targets(
                category=category,
                search=search,
                limit=page_size,
                offset=offset,
            )
            total = await self._target_repo.count_targets(
                category=category,
                search=search,
            )

            result: list[tuple[Target, TargetRating | None]] = []
            for t in targets:
                rating = await self._rating_repo.get_by_target_id(t.id)
                result.append((t, rating))

            return result, total
