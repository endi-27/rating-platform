import pytest
from uuid6 import uuid7

from src.modules.reviews.application.dto import CreateTargetDTO
from src.modules.reviews.application.use_cases import (
    CreateTargetUseCase,
    GetTargetDetailsUseCase,
    ListTargetsUseCase,
)
from src.modules.reviews.domain.events import TargetCreatedEvent
from src.modules.reviews.domain.exceptions import (
    TargetNotFoundException,
    TargetSlugAlreadyExistsException,
)
from src.modules.reviews.domain.models import Target
from tests.unit.fake_repositories import FakeTargetRatingRepository, FakeTargetRepository
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


async def test_create_target_happy_path(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
) -> None:
    use_case = CreateTargetUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    dto = CreateTargetDTO(
        slug="the-dark-knight-2008",
        title="The Dark Knight",
        category="movie",
        description="When the menace known as the Joker wreaks havoc and chaos on the people of Gotham.",
        metadata={"director": "Christopher Nolan"},
    )
    user_id = uuid7()

    target = await use_case.execute(dto, created_by_id=user_id)

    assert target.id is not None
    assert target.slug == "the-dark-knight-2008"
    assert target.title == "The Dark Knight"
    assert target.category == "movie"
    assert target.created_by_id == user_id
    assert uow.committed is True

    # Check rating created
    rating = await rating_repo.get_by_target_id(target.id)
    assert rating is not None
    assert rating.total_reviews == 0

    # Check event published
    events = event_bus.get_events_of_type(TargetCreatedEvent)
    assert len(events) == 1
    assert events[0].target_id == target.id
    assert events[0].slug == "the-dark-knight-2008"


async def test_create_target_slug_already_exists(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    event_bus: FakeEventBus,
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
    )

    dto = CreateTargetDTO(
        slug="avatar-2009",
        title="Avatar 2009 Special",
        category="movie",
    )

    with pytest.raises(TargetSlugAlreadyExistsException):
        await use_case.execute(dto)

    assert uow.committed is False


async def test_get_target_details_by_id_and_slug(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
) -> None:
    target = Target.create(
        slug="gladiator-2000",
        title="Gladiator",
        category="movie",
    )
    await target_repo.save(target)

    use_case = GetTargetDetailsUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
    )

    # By UUID
    found_by_id, rating1 = await use_case.execute(target.id)
    assert found_by_id.id == target.id
    assert found_by_id.slug == "gladiator-2000"

    # By slug string
    found_by_slug, rating2 = await use_case.execute("gladiator-2000")
    assert found_by_slug.id == target.id

    # Not found raises TargetNotFoundException
    with pytest.raises(TargetNotFoundException):
        await use_case.execute(uuid7())

    with pytest.raises(TargetNotFoundException):
        await use_case.execute("non-existent-slug")


async def test_list_targets_with_filters_and_pagination(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
) -> None:
    t1 = Target.create(slug="dune-1", title="Dune Part One", category="sci-fi")
    t2 = Target.create(slug="dune-2", title="Dune Part Two", category="sci-fi")
    t3 = Target.create(slug="godfather", title="The Godfather", category="crime")

    await target_repo.save(t1)
    await target_repo.save(t2)
    await target_repo.save(t3)

    use_case = ListTargetsUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
    )

    # All targets
    items, total = await use_case.execute(page=1, page_size=10)
    assert total == 3
    assert len(items) == 3

    # Filter by category
    items_scifi, total_scifi = await use_case.execute(category="sci-fi")
    assert total_scifi == 2
    assert len(items_scifi) == 2

    # Search by title
    items_search, total_search = await use_case.execute(search="dune")
    assert total_search == 2
    assert len(items_search) == 2

    # Pagination: page 2, size 2
    items_p2, total_p2 = await use_case.execute(page=2, page_size=2)
    assert total_p2 == 3
    assert len(items_p2) == 1
