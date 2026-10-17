from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.reviews.domain.events import TargetDeletedEvent
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.interfaces import ITargetRepository


class DeleteTargetUseCase:
    """Use Case фізичного видалення об'єкта оцінювання."""

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._event_bus = event_bus

    async def execute(self, *, target_id: UUID) -> None:
        async with self._uow:
            target = await self._target_repo.get_by_id(target_id)
            if target is None or not target.is_active:
                raise TargetNotFoundException(target_id)

            deleted = await self._target_repo.delete_by_id(target_id)
            if not deleted:
                raise TargetNotFoundException(target_id)

            await self._uow.commit()

        await self._event_bus.publish(
            TargetDeletedEvent(
                target_id=target_id,
            )
        )
        logger.info("Видалено Target id='{id}'", id=str(target_id))
