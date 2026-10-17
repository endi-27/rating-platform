from uuid import UUID

from src.core import ForbiddenException, IEventBus, IUnitOfWork, logger
from src.modules.reviews.domain.events import ReviewDeletedEvent
from src.modules.reviews.domain.exceptions import ReviewNotFoundException
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    ITargetRatingRepository,
)


class DeleteReviewUseCase:
    """
    Use Case м'якого видалення (Soft Delete) відгуку.
    1. Перевірка існування та активності відгуку.
    2. Перевірка приналежності до target_id.
    3. Перевірка авторства або наявності прав модератора (has_moderate_permission).
    4. Виклик review.soft_delete().
    5. Якщо статус 'published', синхронно декрементуються лічильники в TargetRating.
    6. Збереження та коміт.
    7. Публікація ReviewDeletedEvent.
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
        has_moderate_permission: bool = False,
    ) -> None:
        async with self._uow:
            review = await self._review_repo.get_by_id(review_id)
            if review is None or not review.is_active or review.target_id != target_id:
                raise ReviewNotFoundException(review_id)

            if review.user_id != user_id and not has_moderate_permission:
                raise ForbiddenException("Ви можете видаляти лише власний відгук.")

            score = review.score
            was_counted = review.is_counted_in_rating

            review.soft_delete()
            await self._review_repo.save(review)

            if was_counted:
                rating = await self._rating_repo.get_by_target_id(target_id)
                if rating is not None:
                    rating.apply_deleted_review(score)
                    await self._rating_repo.save(rating)

            await self._uow.commit()

        await self._event_bus.publish(
            ReviewDeletedEvent(
                review_id=review_id,
                target_id=target_id,
                user_id=review.user_id,
                score=score,
            )
        )
        logger.info(
            "М'яко видалено відгук id='{id}' для target_id='{target_id}'",
            id=str(review_id),
            target_id=str(target_id),
        )
