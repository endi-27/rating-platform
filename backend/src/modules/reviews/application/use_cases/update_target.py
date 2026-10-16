from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.reviews.application.dto import UpdateTargetDTO
from src.modules.reviews.domain.events import TargetUpdatedEvent
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.interfaces import ITargetRepository
from src.utils import check_optimistic_lock


class UpdateTargetUseCase:
    """Use Case повного оновлення інформації про об'єкт оцінювання (Full PUT)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._event_bus = event_bus

    async def execute(self, *, target_id: UUID, dto: UpdateTargetDTO) -> None:
        async with self._uow:
            target = await self._target_repo.get_by_id(target_id)
            if target is None or not target.is_active:
                raise TargetNotFoundException(target_id)

            check_optimistic_lock(target.version, dto.version, "об'єкта оцінювання")

            target.update_details(
                title=dto.title,
                category=dto.category,
                description=dto.description,
                metadata=dto.metadata,
            )
            await self._target_repo.save(target)
            await self._uow.commit()

        await self._event_bus.publish(
            TargetUpdatedEvent(
                target_id=target.id,
                version=target.version,
            )
        )
        logger.info(
            "Оновлено Target id='{id}', нова версія={version}",
            id=str(target.id),
            version=target.version,
        )
