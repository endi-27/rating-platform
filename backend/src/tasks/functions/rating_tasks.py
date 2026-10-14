from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core import logger
from src.modules.reviews.infrastructure.repositories import SqlAlchemyTargetRatingRepository


async def recalculate_bayesian_rating_task(
    ctx: dict[str, object],
    target_id: str,
) -> dict[str, object]:
    """
    Фонова задача ARQ для перерахунку зваженого байєсівського рейтингу.
    Виконується асинхронно, щоб не блокувати клієнтський HTTP-запит створення відгуку.
    """
    session_factory: async_sessionmaker[AsyncSession] | None = ctx.get("session_factory")  # type: ignore[assignment]
    if session_factory is None:
        raise RuntimeError("У контексті ARQ воркера відсутня фабрика сесій 'session_factory'")

    target_uuid = UUID(target_id) if isinstance(target_id, str) else target_id

    async with session_factory() as session:
        rating_repo = SqlAlchemyTargetRatingRepository(session)
        rating = await rating_repo.get_by_target_id(target_uuid)

        if rating is None:
            logger.warning(
                "[ARQ Task: Recalculate Rating] Об'єкт target_id='{id}' не знайдено",
                id=str(target_uuid),
            )
            return {"status": "not_found", "target_id": str(target_uuid)}

        # 1. Отримання глобального середнього балу по платформі
        global_mean = await rating_repo.get_global_mean_score()

        # 2. Розрахунок формули Байєса
        bayesian = rating.calculate_bayesian_score(
            min_votes_threshold=5,
            global_mean=global_mean,
        )

        await rating_repo.save(rating)
        await session.commit()

        logger.info(
            "[ARQ Task: Recalculate Rating] Оновлено Bayesian Score для target_id='{id}': {score} (global_mean={mean})",
            id=str(target_uuid),
            score=str(bayesian),
            mean=str(global_mean),
        )

        return {
            "status": "success",
            "target_id": str(target_uuid),
            "bayesian_score": float(bayesian),
            "average_score": float(rating.average_score),
            "total_reviews": rating.total_reviews,
        }
