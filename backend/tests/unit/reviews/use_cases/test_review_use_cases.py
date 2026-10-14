from decimal import Decimal

import pytest
from uuid6 import uuid7

from src.modules.reviews.application.dto import CreateReviewDTO
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    ListTargetReviewsUseCase,
    ModerateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.domain.events import (
    ReviewCreatedEvent,
    ReviewUpdatedEvent,
    ReviewVotedEvent,
)
from src.modules.reviews.domain.exceptions import (
    ReviewAlreadyExistsException,
    ReviewNotFoundException,
    ReviewVoteAlreadyExistsException,
    SelfReviewVoteForbiddenException,
    TargetNotFoundException,
)
from src.modules.reviews.domain.models import Review, Target, TargetRating
from tests.unit.fake_repositories import (
    FakeReviewRepository,
    FakeReviewVoteRepository,
    FakeTargetRatingRepository,
    FakeTargetRepository,
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
def review_repo() -> FakeReviewRepository:
    return FakeReviewRepository()


@pytest.fixture
def vote_repo() -> FakeReviewVoteRepository:
    return FakeReviewVoteRepository()


@pytest.fixture
def event_bus() -> FakeEventBus:
    return FakeEventBus()


async def test_create_review_happy_path(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target = Target.create(slug="fight-club-1999", title="Fight Club", category="movie")
    await target_repo.save(target)
    rating = TargetRating.create_empty(target.id)
    await rating_repo.save(rating)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
    )

    user_id = uuid7()
    dto = CreateReviewDTO(
        score=5,
        title="First rule of Fight Club",
        content="The first rule of Fight Club is: you do not talk about Fight Club.",
    )

    review = await use_case.execute(
        target_id=target.id,
        user_id=user_id,
        dto=dto,
    )

    assert review.id is not None
    assert review.target_id == target.id
    assert review.user_id == user_id
    assert review.score == 5
    assert uow.committed is True

    # Rating should be updated to 5.00
    updated_rating = await rating_repo.get_by_target_id(target.id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 1
    assert updated_rating.average_score == Decimal("5.00")

    # Event published
    events = event_bus.get_events_of_type(ReviewCreatedEvent)
    assert len(events) == 1
    assert events[0].review_id == review.id
    assert events[0].target_id == target.id


async def test_create_review_target_not_found(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
    )

    dto = CreateReviewDTO(score=4, content="Valid review text for testing purposes.")
    with pytest.raises(TargetNotFoundException):
        await use_case.execute(
            target_id=uuid7(),
            user_id=uuid7(),
            dto=dto,
        )


async def test_create_review_duplicate_raises_exception(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target = Target.create(slug="matrix", title="The Matrix", category="movie")
    await target_repo.save(target)

    user_id = uuid7()
    existing = Review.create(
        target_id=target.id,
        user_id=user_id,
        score=5,
        content="First review from user.",
    )
    await review_repo.save(existing)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
    )

    dto = CreateReviewDTO(score=4, content="Attempting second review from same user.")
    with pytest.raises(ReviewAlreadyExistsException):
        await use_case.execute(
            target_id=target.id,
            user_id=user_id,
            dto=dto,
        )


async def test_list_target_reviews(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    review_repo: FakeReviewRepository,
) -> None:
    target = Target.create(slug="alien-1979", title="Alien", category="movie")
    await target_repo.save(target)

    r1 = Review.create(
        target_id=target.id,
        user_id=uuid7(),
        score=5,
        content="In space no one can hear you scream.",
    )
    r2 = Review.create(
        target_id=target.id,
        user_id=uuid7(),
        score=4,
        content="Superb horror atmosphere and pacing.",
    )
    await review_repo.save(r1)
    await review_repo.save(r2)

    use_case = ListTargetReviewsUseCase(
        uow=uow,
        target_repo=target_repo,
        review_repo=review_repo,
    )

    reviews, total = await use_case.execute(target_id=target.id, page=1, page_size=10)
    assert total == 2
    assert len(reviews) == 2

    # Target not found
    with pytest.raises(TargetNotFoundException):
        await use_case.execute(target_id=uuid7())


async def test_vote_review_use_case(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
) -> None:
    author_id = uuid7()
    voter_id = uuid7()
    target_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=author_id,
        score=5,
        content="Very detailed and helpful review about this item.",
    )
    await review_repo.save(review)

    use_case = VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
    )

    # 1. Author votes for own review -> Forbidden
    with pytest.raises(SelfReviewVoteForbiddenException):
        await use_case.execute(
            review_id=review.id,
            user_id=author_id,
            is_helpful=True,
        )

    # 2. Voter votes helpful -> success
    vote = await use_case.execute(
        review_id=review.id,
        user_id=voter_id,
        is_helpful=True,
    )
    assert vote.is_helpful is True
    assert review.helpful_count == 1
    assert uow.committed is True

    # 3. Voter votes helpful again -> Already exists conflict
    with pytest.raises(ReviewVoteAlreadyExistsException):
        await use_case.execute(
            review_id=review.id,
            user_id=voter_id,
            is_helpful=True,
        )

    # 4. Voter changes vote to unhelpful -> switches vote
    changed_vote = await use_case.execute(
        review_id=review.id,
        user_id=voter_id,
        is_helpful=False,
    )
    assert changed_vote.is_helpful is False
    assert review.helpful_count == 0
    assert review.unhelpful_count == 1
    assert event_bus.has_event_of_type(ReviewVotedEvent)

    # 5. Non-existent review -> ReviewNotFoundException
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            review_id=uuid7(),
            user_id=voter_id,
            is_helpful=True,
        )


async def test_moderate_review_use_case(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target = Target.create(slug="test-item", title="Test Item", category="misc")
    await target_repo.save(target)
    rating = TargetRating.create_empty(target.id)
    rating.apply_new_review(5)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target.id,
        user_id=uuid7(),
        score=5,
        content="Suspicious review content with spam links.",
    )
    await review_repo.save(review)

    use_case = ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    # 1. Action: hide -> review status hidden, rating deducted
    mod_review = await use_case.execute(review_id=review.id, action="hide")
    assert mod_review.status == "hidden"
    assert rating.total_reviews == 0

    # 2. Action: publish -> review restored, rating added back
    pub_review = await use_case.execute(review_id=review.id, action="publish")
    assert pub_review.status == "published"
    assert rating.total_reviews == 1

    # 3. Action: flag -> review marked flagged
    flag_review = await use_case.execute(review_id=review.id, action="flag")
    assert flag_review.status == "flagged"

    # Event was published
    assert event_bus.has_event_of_type(ReviewUpdatedEvent)
