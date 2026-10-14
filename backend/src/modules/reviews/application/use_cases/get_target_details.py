from uuid import UUID

from src.core import IUnitOfWork
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.interfaces import ITargetRatingRepository, ITargetRepository
from src.modules.reviews.domain.models import Target, TargetRating


class GetTargetDetailsUseCase:
    """Use Case отримання картки об'єкта оцінювання разом з агрегованим рейтингом."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        rating_repo: ITargetRatingRepository,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._rating_repo = rating_repo

    async def execute(self, id_or_slug: UUID | str) -> tuple[Target, TargetRating | None]:
        async with self._uow:
            target: Target | None = None
            if isinstance(id_or_slug, UUID):
                target = await self._target_repo.get_by_id(id_or_slug)
            else:
                target = await self._target_repo.get_by_slug(id_or_slug)

            if target is None:
                raise TargetNotFoundException(id_or_slug)

            rating = await self._rating_repo.get_by_target_id(target.id)
            return target, rating
