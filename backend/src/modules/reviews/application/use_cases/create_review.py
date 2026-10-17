from uuid import UUID

from src.core import AccountDeactivatedException, IEventBus, IUnitOfWork, logger
from src.modules.reviews.application.dto import CreateReviewDTO
from src.modules.reviews.domain.events import ReviewCreatedEvent
from src.modules.reviews.domain.exceptions import (
    ReviewAlreadyExistsException,
    TargetNotFoundException,
    UserNotFoundException,
)
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    ITargetRatingRepository,
    ITargetRepository,
    IUserGateway,
)
from src.modules.reviews.domain.models import Review, TargetRating


class CreateReviewUseCase:
    """
    Use Case публікації нового відгуку на Target.
    Реалізує:
    1. Перевірку існування та активності автора відгуку (IUserGateway).
    2. Перевірку існування та активності Target.
    3. Правило One Review: перевірку, що користувач ще не залишав відгук на цей об'єкт.
    4. Синхронний атомарний інкремент лічильників рейтингу (TargetRating).
    5. Публікацію ReviewCreatedEvent для інвалідації кешу та запуску фонового перерахунку.
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        target_repo: ITargetRepository,
        rating_repo: ITargetRatingRepository,
        review_repo: IReviewRepository,
        event_bus: IEventBus,
        user_gateway: IUserGateway,
    ) -> None:
        self._uow = uow
        self._target_repo = target_repo
        self._rating_repo = rating_repo
        self._review_repo = review_repo
        self._event_bus = event_bus
        self._user_gateway = user_gateway

    async def execute(
        self,
        *,
        target_id: UUID,
        user_id: UUID,
        dto: CreateReviewDTO,
    ) -> UUID:
        async with self._uow:
            # 1. Валідація існування та активності автора відгуку
            user = await self._user_gateway.get_user_by_id(user_id)
            if not user:
                raise UserNotFoundException(user_id)
            if user.deleted_at is not None:
                raise AccountDeactivatedException()

            # 2. Перевірка цільового об'єкта
            target = await self._target_repo.get_by_id(target_id)
            if target is None or not target.is_active:
                raise TargetNotFoundException(target_id)

            # 3. Інваріант: один відгук від користувача на об'єкт
            existing_review = await self._review_repo.get_by_target_and_user(target_id, user_id)
            if existing_review is not None:
                logger.warning(
                    "Спроба повторного відгуку user_id='{user_id}' на target_id='{target_id}'",
                    user_id=str(user_id),
                    target_id=str(target_id),
                )
                raise ReviewAlreadyExistsException(target_id, user_id)

            # 4. Створення відгуку
            review = Review.create(
                target_id=target_id,
                user_id=user_id,
                score=dto.score,
                content=dto.content,
                title=dto.title,
            )
            await self._review_repo.save(review)

            # 5. Синхронний перерахунок та оновлення агрегату рейтингу
            rating = await self._rating_repo.get_by_target_id(target_id)
            if rating is None:
                rating = TargetRating.create_empty(target_id)

            rating.apply_new_review(dto.score)
            await self._rating_repo.save(rating)

            await self._uow.commit()

        # 6. Публікація доменної події
        await self._event_bus.publish(
            ReviewCreatedEvent(
                review_id=review.id,
                target_id=target_id,
                user_id=user_id,
                score=review.score,
            )
        )
        logger.info(
            "Опубліковано новий відгук id='{id}' (оцінка {score}) на target_id='{target_id}'",
            id=str(review.id),
            score=review.score,
            target_id=str(target_id),
        )
        return review.id
