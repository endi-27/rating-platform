from __future__ import annotations

from uuid import UUID

from src.core import ISetBuffer, IUnitOfWork, logger, settings
from src.modules.reviews.domain.interfaces import (
    ITargetRatingRepository,
)


class BatchRecalculateRatingsUseCase:
    """
    Use Case пакетного перерахунку байєсівського рейтингу (Bayesian Score) для черги змінених об'єктів.

    Реалізує патерн Batch Accumulation:
    1. Вилучає пачку ідентифікаторів з розподіленого буфера множин (ISetBuffer).
    2. ОДИН РАЗ обчислює global_mean_score() по всій системі для всієї пачки (захист від Thundering Herd).
    3. Оновлює зважений байєсівський рейтинг у транзакційному контексті IUnitOfWork.
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        rating_repo: ITargetRatingRepository,
        buffer: ISetBuffer,
        buffer_key: str | None = None,
    ) -> None:
        self._uow = uow
        self._rating_repo = rating_repo
        self._buffer = buffer
        self._buffer_key = buffer_key or settings.redis_sets.dirty_targets_key

    async def execute(self, *, batch_size: int = 100) -> int:
        """
        Виконує один крок пакетної обробки.
        Повертає кількість успішно оновлених об'єктів.
        """
        raw_items = await self._buffer.pop_batch(self._buffer_key, batch_size=batch_size)
        if not raw_items:
            return 0

        target_ids: list[UUID] = []
        for raw_id in raw_items:
            try:
                target_ids.append(UUID(raw_id))
            except ValueError:
                logger.error(
                    "[Batch Rating Recalc] Невалідний UUID '{raw_id}' отримано з буфера Redis Set '{key}'",
                    raw_id=raw_id,
                    key=self._buffer_key,
                )

        if not target_ids:
            return 0

        async with self._uow:
            # 1. Глобальне середнє обчислюється рівно один раз на всю пачку
            global_mean = await self._rating_repo.get_global_mean_score()
            processed_count = 0

            for target_id in target_ids:
                rating = await self._rating_repo.get_by_target_id(target_id)
                if rating is None:
                    logger.warning(
                        "[Batch Rating Recalc] Запис рейтингу для target_id='{id}' не знайдено",
                        id=str(target_id),
                    )
                    continue

                # 2. Розрахунок формули Байєса в доменній моделі
                rating.calculate_bayesian_score(
                    min_votes_threshold=5,
                    global_mean=global_mean,
                )
                await self._rating_repo.save(rating)
                processed_count += 1

            await self._uow.commit()

        logger.info(
            "[Batch Rating Recalc] Успішно оновлено рейтинги для {count} об'єктів (global_mean={mean})",
            count=processed_count,
            mean=str(global_mean),
        )
        return processed_count
