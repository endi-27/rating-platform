from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.reviews.application.dto import CreateTargetDTO
from src.modules.reviews.domain.events import TargetCreatedEvent
from src.modules.reviews.domain.exceptions import TargetSlugAlreadyExistsException
from src.modules.reviews.domain.interfaces import ITargetRatingRepository, ITargetRepository
from src.modules.reviews.domain.models import Target, TargetRating


class CreateTargetUseCase:
    """Use Case створення нового об'єкта оцінювання (Target)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        rating_repo: ITargetRatingRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._rating_repo = rating_repo
        self._event_bus = event_bus

    async def execute(self, dto: CreateTargetDTO, *, created_by_id: UUID | None = None) -> Target:
        async with self._uow:
            # 1. Перевірка унікальності слага
            if await self._target_repo.exists_by_slug(dto.slug):
                logger.warning("Спроба створення дубліката Target зі slug='{slug}'", slug=dto.slug)
                raise TargetSlugAlreadyExistsException(dto.slug)

            # 2. Створення доменного агрегата Target
            target = Target.create(
                slug=dto.slug,
                title=dto.title,
                category=dto.category,
                description=dto.description,
                metadata=dto.metadata,
                created_by_id=created_by_id,
            )
            await self._target_repo.save(target)

            # 3. Створення початкового порожнього агрегату рейтингу (1:1)
            rating = TargetRating.create_empty(target.id)
            await self._rating_repo.save(rating)

            await self._uow.commit()

        # 4. Публікація доменної події
        await self._event_bus.publish(
            TargetCreatedEvent(
                target_id=target.id,
                slug=target.slug,
                category=target.category,
            )
        )
        logger.info("Створено новий Target id='{id}', slug='{slug}'", id=str(target.id), slug=target.slug)
        return target
