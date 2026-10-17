from uuid import UUID

from src.core import DomainException, IEventBus, IUnitOfWork, logger
from src.modules.reviews.domain.events import ReviewUpdatedEvent
from src.modules.reviews.domain.exceptions import ReviewNotFoundException
from src.modules.reviews.domain.interfaces import IReviewRepository, ITargetRatingRepository
from src.modules.reviews.domain.models import TargetRating
from src.utils import check_optimistic_lock


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

    async def execute(self, *, review_id: UUID, action: str, version: int | None = None) -> UUID:
        async with self._uow:
            review = await self._review_repo.get_by_id(review_id)
            if review is None or not review.is_active:
                raise ReviewNotFoundException(review_id)

            if version is not None:
                check_optimistic_lock(review.version, version, "відгуку")

            was_counted = review.is_counted_in_rating

            if action == "hide":
                review.hide()
            elif action == "publish":
                review.publish()
            elif action == "flag":
                review.flag()
            else:
                raise DomainException(f"Невідома дія модерації: '{action}'. Дозволено: hide, publish, flag.")

            is_now_counted = review.is_counted_in_rating
            if was_counted != is_now_counted:
                rating = await self._rating_repo.get_by_target_id(review.target_id)
                if was_counted and not is_now_counted:
                    if rating is not None:
                        rating.apply_deleted_review(review.score)
                        await self._rating_repo.save(rating)
                elif not was_counted and is_now_counted:
                    if rating is None:
                        rating = TargetRating.create_empty(review.target_id)
                    rating.apply_new_review(review.score)
                    await self._rating_repo.save(rating)

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
