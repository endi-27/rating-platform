from __future__ import annotations

from src.core import ISetBuffer, logger, settings
from src.core.events import AsyncEventBus, BaseEvent
from src.infrastructure import get_set_buffer
from src.infrastructure.cache import clear_cache_with_dependencies
from src.modules.reviews.domain.events import (
    ReviewCreatedEvent,
    ReviewDeletedEvent,
    ReviewUpdatedEvent,
    ReviewVotedEvent,
    TargetCreatedEvent,
    TargetDeletedEvent,
    TargetRatingRecalculatedEvent,
    TargetUpdatedEvent,
)


async def handle_review_mutation_buffer_target(
    event: BaseEvent,
    buffer: ISetBuffer | None = None,
    key: str | None = None,
) -> None:
    """Атомарно додає target_id у розподілений буфер Redis Set для подальшого пакетного перерахунку."""
    target_id = getattr(event, "target_id", None)
    if target_id is not None:
        target_key = key or settings.redis_sets.dirty_targets_key
        try:
            buf = buffer or get_set_buffer()
            await buf.add(target_key, target_id)
        except Exception as exc:
            logger.warning(
                "Не вдалося додати target_id='{id}' у буфер Redis Set '{key}': {err}",
                id=str(target_id),
                key=target_key,
                err=str(exc),
            )


async def handle_review_mutation_cache_invalidation(event: BaseEvent) -> None:
    """Інвалідація просторів імен кешу відгуків та пов'язаних карток об'єктів у Redis."""
    await clear_cache_with_dependencies(settings.cache.namespace.reviews)
    await clear_cache_with_dependencies(settings.cache.namespace.targets)


async def handle_target_mutation_event(event: BaseEvent) -> None:
    """Інвалідація простору імен тарґетів у Redis."""
    await clear_cache_with_dependencies(settings.cache.namespace.targets)


async def handle_review_voted_event(event: BaseEvent) -> None:
    """Інвалідація простору імен відгуків у Redis після голосування за корисність."""
    await clear_cache_with_dependencies(settings.cache.namespace.reviews)


def register_reviews_event_handlers(
    bus: AsyncEventBus,
    buffer: ISetBuffer | None = None,
) -> None:
    """Реєстрація слухачів подій модуля reviews у шині подій з підтримкою ін'єкції буфера (DIP)."""
    bus.on(TargetCreatedEvent)(handle_target_mutation_event)
    bus.on(TargetUpdatedEvent)(handle_target_mutation_event)
    bus.on(TargetDeletedEvent)(handle_target_mutation_event)
    bus.on(TargetRatingRecalculatedEvent)(handle_target_mutation_event)

    bus.on(ReviewCreatedEvent)(handle_review_mutation_cache_invalidation)
    bus.on(ReviewUpdatedEvent)(handle_review_mutation_cache_invalidation)
    bus.on(ReviewDeletedEvent)(handle_review_mutation_cache_invalidation)

    bus.on(ReviewVotedEvent)(handle_review_voted_event)

    async def _on_review_buffer(event: BaseEvent) -> None:
        await handle_review_mutation_buffer_target(event, buffer=buffer)

    bus.on(ReviewCreatedEvent)(_on_review_buffer)
    bus.on(ReviewUpdatedEvent)(_on_review_buffer)
    bus.on(ReviewDeletedEvent)(_on_review_buffer)


__all__ = [
    "handle_review_mutation_buffer_target",
    "handle_review_mutation_cache_invalidation",
    "handle_review_voted_event",
    "handle_target_mutation_event",
    "register_reviews_event_handlers",
]
