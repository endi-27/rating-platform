from uuid import UUID

from src.core import IEventBus, IUnitOfWork, logger
from src.modules.reviews.domain.events import ReviewVotedEvent
from src.modules.reviews.domain.exceptions import (
    ReviewNotFoundException,
    ReviewVoteAlreadyExistsException,
    SelfReviewVoteForbiddenException,
)
from src.modules.reviews.domain.interfaces import IReviewRepository, IReviewVoteRepository
from src.modules.reviews.domain.models import ReviewVote


class VoteReviewUseCase:
    """Use Case оцінки корисності відгуку (👍 / 👎)."""

    def __init__(
        self,
        uow: IUnitOfWork,
        review_repo: IReviewRepository,
        vote_repo: IReviewVoteRepository,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._review_repo = review_repo
        self._vote_repo = vote_repo
        self._event_bus = event_bus

    async def execute(
        self,
        *,
        review_id: UUID,
        user_id: UUID,
        is_helpful: bool,
    ) -> ReviewVote:
        async with self._uow:
            review = await self._review_repo.get_by_id(review_id)
            if review is None or not review.is_active:
                raise ReviewNotFoundException(review_id)

            # Заборона голосування за власний відгук
            if review.user_id == user_id:
                logger.warning(
                    "Спроба користувача '{user_id}' проголосувати за власний відгук '{review_id}'",
                    user_id=str(user_id),
                    review_id=str(review_id),
                )
                raise SelfReviewVoteForbiddenException()

            existing_vote = await self._vote_repo.get_by_review_and_user(review_id, user_id)
            if existing_vote is not None:
                if existing_vote.is_helpful == is_helpful:
                    raise ReviewVoteAlreadyExistsException()

                # Зміна голосу
                if is_helpful:
                    review.add_helpful_vote()
                    review.remove_unhelpful_vote()
                else:
                    review.add_unhelpful_vote()
                    review.remove_helpful_vote()

                existing_vote.change_vote(is_helpful)
                await self._vote_repo.save(existing_vote)
                vote = existing_vote
            else:
                vote = ReviewVote.create(
                    review_id=review_id,
                    user_id=user_id,
                    is_helpful=is_helpful,
                )
                await self._vote_repo.save(vote)
                if is_helpful:
                    review.add_helpful_vote()
                else:
                    review.add_unhelpful_vote()

            await self._review_repo.save(review)
            await self._uow.commit()

        await self._event_bus.publish(
            ReviewVotedEvent(
                vote_id=vote.id,
                review_id=review_id,
                user_id=user_id,
                is_helpful=is_helpful,
            )
        )
        return vote
