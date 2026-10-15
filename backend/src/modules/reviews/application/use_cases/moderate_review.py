from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.reviews.domain.events import ReviewUpdatedEvent
from src.modules.reviews.domain.exceptions import ReviewNotFoundException
from src.modules.reviews.domain.interfaces import IReviewRepository, ITargetRatingRepository


class ModerateReviewUseCase:
    """Use Case модерації відгуків (hide / publish / flag) з автоматичним перерахунком рейтингу."""

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

    async def execute(self, *, review_id: UUID, action: str) -> UUID:
        async with self._uow:
            review = await self._review_repo.get_by_id(review_id)
            if review is None or not review.is_active:
                raise ReviewNotFoundException(review_id)

            old_status = review.status
            rating = await self._rating_repo.get_by_target_id(review.target_id)

            if action == "hide" and old_status != "hidden":
                review.hide()
                if old_status == "published" and rating is not None:
                    rating.apply_deleted_review(review.score)
                    await self._rating_repo.save(rating)

            elif action == "publish" and old_status != "published":
                review.publish()
                if old_status == "hidden" and rating is not None:
                    rating.apply_new_review(review.score)
                    await self._rating_repo.save(rating)

            elif action == "flag":
                review.flag()

            await self._review_repo.save(review)
            await self._uow.commit()

        await self._event_bus.publish(
            ReviewUpdatedEvent(
                review_id=review.id,
                target_id=review.target_id,
                user_id=review.user_id,
                old_score=review.score,
                new_score=review.score,
            )
        )
        logger.info(
            "Модерація відгуку id='{id}': дія='{action}', новий статус='{status}'",
            id=str(review.id),
            action=action,
            status=review.status,
        )
        return review.id
