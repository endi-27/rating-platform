from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import get_uow
from src.core import IEventBus, IUnitOfWork, get_db_session
from src.core.events import get_event_bus
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    CreateTargetUseCase,
    GetTargetDetailsUseCase,
    ListTargetReviewsUseCase,
    ListTargetsUseCase,
    ModerateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    IReviewVoteRepository,
    ITargetRatingRepository,
    ITargetRepository,
)
from src.modules.reviews.infrastructure.repositories import (
    SqlAlchemyReviewRepository,
    SqlAlchemyReviewVoteRepository,
    SqlAlchemyTargetRatingRepository,
    SqlAlchemyTargetRepository,
)

# === 1. Репозиторії ===


def get_target_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ITargetRepository:
    return SqlAlchemyTargetRepository(session=session)


def get_target_rating_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ITargetRatingRepository:
    return SqlAlchemyTargetRatingRepository(session=session)


def get_review_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IReviewRepository:
    return SqlAlchemyReviewRepository(session=session)


def get_review_vote_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IReviewVoteRepository:
    return SqlAlchemyReviewVoteRepository(session=session)


# === 2. Use Cases ===


def get_create_target_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> CreateTargetUseCase:
    return CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )


def get_target_details_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
) -> GetTargetDetailsUseCase:
    return GetTargetDetailsUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
    )


def get_list_targets_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
) -> ListTargetsUseCase:
    return ListTargetsUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
    )


def get_create_review_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> CreateReviewUseCase:
    return CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
    )


def get_list_target_reviews_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
) -> ListTargetReviewsUseCase:
    return ListTargetReviewsUseCase(
        uow=uow,
        target_repo=target_repo,
        review_repo=review_repo,
    )


def get_vote_review_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
    vote_repo: Annotated[IReviewVoteRepository, Depends(get_review_vote_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> VoteReviewUseCase:
    return VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
    )


def get_moderate_review_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
) -> ModerateReviewUseCase:
    return ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
