from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core import ISetBuffer, settings
from src.infrastructure import (
    SqlAlchemyUnitOfWork,
    clear_cache_with_dependencies,
    get_set_buffer,
)
from src.modules.reviews.application.use_cases import BatchRecalculateRatingsUseCase
from src.modules.reviews.infrastructure.repositories import SqlAlchemyTargetRatingRepository


async def process_dirty_target_ratings_task(
    ctx: dict[str, object],
    batch_size: int = 100,
) -> dict[str, object]:
    """
    Періодична cron-задача ARQ:
    Пакетно вилучає об'єкти з черги на перерахунок, один раз обчислює global_mean
    та оновлює рейтинги об'єктів без лавиноподібного навантаження (Thundering Herd).
    """
    buffer: ISetBuffer | None = ctx.get("set_buffer") or ctx.get("rating_buffer")  # type: ignore[assignment]
    if buffer is None:
        buffer = get_set_buffer()

    session_factory: async_sessionmaker[AsyncSession] | None = ctx.get("session_factory")  # type: ignore[assignment]
    if session_factory is None:
        raise RuntimeError("У контексті ARQ воркера відсутня фабрика сесій 'session_factory'")

    total_processed = 0
    async with session_factory() as session:
        uow = SqlAlchemyUnitOfWork(session=session)
        rating_repo = SqlAlchemyTargetRatingRepository(session)
        use_case = BatchRecalculateRatingsUseCase(
            uow=uow,
            rating_repo=rating_repo,
            buffer=buffer,
        )
        while True:
            processed = await use_case.execute(batch_size=batch_size)
            total_processed += processed
            if processed < batch_size:
                break

    if total_processed > 0:
        await clear_cache_with_dependencies(settings.cache.namespace.targets)
        await clear_cache_with_dependencies(settings.cache.namespace.reviews)

    return {
        "status": "success",
        "processed": total_processed,
    }
