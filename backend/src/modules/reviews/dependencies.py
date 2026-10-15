from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import get_read_db_session, get_uow
from src.core import IEventBus, IUnitOfWork, get_db_session
from src.core.events import get_event_bus
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    CreateTargetUseCase,
    ModerateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    IReviewVoteRepository,
    ITargetRatingRepository,
    ITargetRepository,
    IUserGateway,
)
from src.modules.reviews.infrastructure.repositories import (
    SqlAlchemyReviewRepository,
    SqlAlchemyReviewVoteRepository,
    SqlAlchemyTargetRatingRepository,
    SqlAlchemyTargetRepository,
)
from src.modules.reviews.queries import (
    ReviewQueryService,
    TargetQueryService,
)
from src.modules.users import get_users_public_gateway

# === 1. Репозиторії та шлюзи (Write Path) ===


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


def get_user_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IUserGateway:
    return get_users_public_gateway(session=session)


# === 2. Query Services (Read-Side CQRS / Read Replica Session) ===


def get_target_query_service(
    session: Annotated[AsyncSession, Depends(get_read_db_session)],
) -> TargetQueryService:
    return TargetQueryService(session=session)


def get_review_query_service(
    session: Annotated[AsyncSession, Depends(get_read_db_session)],
) -> ReviewQueryService:
    return ReviewQueryService(session=session)


# === 3. Use Cases (Write Path / Primary Session) ===


def get_create_target_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
    user_gateway: Annotated[IUserGateway, Depends(get_user_gateway)],
) -> CreateTargetUseCase:
    return CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )


def get_create_review_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    target_repo: Annotated[ITargetRepository, Depends(get_target_repo)],
    rating_repo: Annotated[ITargetRatingRepository, Depends(get_target_rating_repo)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
    user_gateway: Annotated[IUserGateway, Depends(get_user_gateway)],
) -> CreateReviewUseCase:
    return CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )


def get_vote_review_uc(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    review_repo: Annotated[IReviewRepository, Depends(get_review_repo)],
    vote_repo: Annotated[IReviewVoteRepository, Depends(get_review_vote_repo)],
    event_bus: Annotated[IEventBus, Depends(get_event_bus)],
    user_gateway: Annotated[IUserGateway, Depends(get_user_gateway)],
) -> VoteReviewUseCase:
    return VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
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
