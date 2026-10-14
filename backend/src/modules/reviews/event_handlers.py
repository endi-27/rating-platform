from __future__ import annotations

from src.core import logger, settings
from src.core.events import AsyncEventBus, BaseEvent
from src.infrastructure.cache import clear_cache_with_dependencies
from src.modules.reviews.domain.events import (
    ReviewCreatedEvent,
    ReviewDeletedEvent,
    ReviewUpdatedEvent,
    ReviewVotedEvent,
    TargetCreatedEvent,
    TargetRatingRecalculatedEvent,
)
from src.tasks.dispatcher import get_task_dispatcher


async def handle_review_mutation_event(event: BaseEvent) -> None:
    """
    Обробник подій створення/оновлення/видалення відгуку:
    1. Інвалідує кеш відгуків та пов'язаних карток об'єктів у Redis.
    2. Асинхронно ставить задачу в ARQ воркер на перерахунок байєсівського рейтингу.
    """
    await clear_cache_with_dependencies(settings.cache.namespace.reviews)

    target_id = getattr(event, "target_id", None)
    if target_id is not None:
        try:
            dispatcher = get_task_dispatcher()
            await dispatcher.enqueue_recalculate_bayesian_rating(target_id)
        except Exception as exc:
            logger.warning(
                "Не вдалося поставити задачу перерахунку рейтингу для target_id='{id}': {err}",
                id=str(target_id),
                err=str(exc),
            )


async def handle_target_mutation_event(event: BaseEvent) -> None:
    """Інвалідація простору імен тарґетів у Redis."""
    await clear_cache_with_dependencies(settings.cache.namespace.targets)


def register_reviews_event_handlers(bus: AsyncEventBus) -> None:
    """Реєстрація слухачів подій модуля reviews у шині подій."""
    bus.on(TargetCreatedEvent)(handle_target_mutation_event)
    bus.on(TargetRatingRecalculatedEvent)(handle_target_mutation_event)

    bus.on(ReviewCreatedEvent)(handle_review_mutation_event)
    bus.on(ReviewUpdatedEvent)(handle_review_mutation_event)
    bus.on(ReviewDeletedEvent)(handle_review_mutation_event)
    bus.on(ReviewVotedEvent)(handle_review_mutation_event)
