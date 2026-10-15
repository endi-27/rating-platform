from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core import AccountDeactivatedException
from src.modules.reviews.application.dto import CreateTargetDTO
from src.modules.reviews.application.use_cases import CreateTargetUseCase
from src.modules.reviews.domain.events import TargetCreatedEvent
from src.modules.reviews.domain.exceptions import (
    TargetSlugAlreadyExistsException,
    UserNotFoundException,
)
from src.modules.reviews.domain.models import Target
from tests.unit.fake_repositories import (
    FakeTargetRatingRepository,
    FakeTargetRepository,
    FakeUserGateway,
)
from tests.unit.fakes import FakeEventBus, FakeUnitOfWork


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def target_repo() -> FakeTargetRepository:
    return FakeTargetRepository()


@pytest.fixture
def rating_repo() -> FakeTargetRatingRepository:
    return FakeTargetRatingRepository()


@pytest.fixture
def event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def user_gateway() -> FakeUserGateway:
    return FakeUserGateway()


async def test_create_target_happy_path(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    use_case = CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    user_id = uuid7()
    user_gateway.add_user(user_id)

    dto = CreateTargetDTO(
        slug="the-dark-knight-2008",
        title="The Dark Knight",
        category="movie",
        description="When the menace known as the Joker wreaks havoc and chaos on the people of Gotham.",
        metadata={"director": "Christopher Nolan"},
    )

    target_id = await use_case.execute(dto, created_by_id=user_id)

    assert isinstance(target_id, UUID)
    target = await target_repo.get_by_id(target_id)
    assert target is not None
    assert target.slug == "the-dark-knight-2008"
    assert target.title == "The Dark Knight"
    assert target.category == "movie"
    assert target.created_by_id == user_id
    assert uow.committed is True

    # Check rating created
    rating = await rating_repo.get_by_target_id(target_id)
    assert rating is not None
    assert rating.total_reviews == 0

    # Check event published
    events = event_bus.get_events_of_type(TargetCreatedEvent)
    assert len(events) == 1
    assert events[0].target_id == target_id
    assert events[0].slug == "the-dark-knight-2008"


async def test_create_target_slug_already_exists(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    existing = Target.create(
        slug="avatar-2009",
        title="Avatar",
        category="movie",
    )
    await target_repo.save(existing)

    use_case = CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateTargetDTO(
        slug="avatar-2009",
        title="Avatar 2009 Special",
        category="movie",
    )

    with pytest.raises(TargetSlugAlreadyExistsException):
        await use_case.execute(dto)

    assert uow.committed is False


async def test_create_target_author_not_found(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    use_case = CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateTargetDTO(slug="new-movie", title="New Movie", category="movie")
    with pytest.raises(UserNotFoundException):
        await use_case.execute(dto, created_by_id=uuid7())


async def test_create_target_author_deactivated(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    user_id = uuid7()
    user_gateway.add_user(user_id, is_active=False)

    use_case = CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateTargetDTO(slug="inactive-movie", title="Inactive Movie", category="movie")
    with pytest.raises(AccountDeactivatedException):
        await use_case.execute(dto, created_by_id=user_id)
