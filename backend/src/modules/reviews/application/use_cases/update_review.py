from uuid import UUID

from src.core import ForbiddenException, IEventBus, IUnitOfWork, logger
from src.modules.reviews.application.dto import UpdateReviewDTO
from src.modules.reviews.domain.events import ReviewUpdatedEvent
from src.modules.reviews.domain.exceptions import ReviewNotFoundException
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    ITargetRatingRepository,
)
from src.utils import check_optimistic_lock


class UpdateReviewUseCase:
    """
    Use Case оновлення власного відгуку та оцінки (Full PUT).
    1. Перевірка існування та активності відгуку.
    2. Перевірка приналежності до target_id.
    3. Перевірка, що автор запиту є автором відгуку.
    4. Перевірка версії (OCC).
    5. Оновлення змісту та оцінки.
    6. Якщо оцінка змінилася і статус 'published', синхронно оновлюється TargetRating.
    7. Збереження та коміт.
    8. Публікація ReviewUpdatedEvent (інвалідація кешу та фоновий перерахунок рейтингу).
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        review_repo: IReviewRepository,
        rating_repo: ITargetRatingRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._review_repo = review_repo
        self._rating_repo = rating_repo
        self._event_bus = event_bus

    async def execute(
        self,
        *,
        target_id: UUID,
        review_id: UUID,
        user_id: UUID,
        dto: UpdateReviewDTO,
    ) -> UUID:
        async with self._uow:
            review = await self._review_repo.get_by_id(review_id)
            if review is None or not review.is_active or review.target_id != target_id:
                raise ReviewNotFoundException(review_id)

            if review.user_id != user_id:
                raise ForbiddenException("Ви можете редагувати лише власний відгук.")

            check_optimistic_lock(review.version, dto.version, "відгуку")

            old_score = review.score
            review.update_content(
                score=dto.score,
                title=dto.title,
                content=dto.content,
            )
            await self._review_repo.save(review)

            if old_score != dto.score and review.is_counted_in_rating:
                rating = await self._rating_repo.get_by_target_id(target_id)
                if rating is not None:
                    rating.apply_updated_review(old_score=old_score, new_score=dto.score)
                    await self._rating_repo.save(rating)

            await self._uow.commit()

        await self._event_bus.publish(
            ReviewUpdatedEvent(
                review_id=review.id,
                target_id=target_id,
                user_id=user_id,
                old_score=old_score,
                new_score=dto.score,
            )
        )
        logger.info(
            "Оновлено відгук id='{id}' користувача user_id='{user_id}' для target_id='{target_id}'",
            id=str(review.id),
            user_id=str(user_id),
            target_id=str(target_id),
        )
        return review.id
