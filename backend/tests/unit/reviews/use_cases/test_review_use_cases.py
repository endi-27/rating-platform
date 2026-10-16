from decimal import Decimal
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core import (
    AccountDeactivatedException,
    ForbiddenException,
    OptimisticLockConflictException,
)
from src.modules.reviews.application.dto import CreateReviewDTO, UpdateReviewDTO
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    DeleteReviewUseCase,
    ModerateReviewUseCase,
    UpdateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.domain.events import (
    ReviewCreatedEvent,
    ReviewDeletedEvent,
    ReviewUpdatedEvent,
    ReviewVotedEvent,
)
from src.modules.reviews.domain.exceptions import (
    ReviewAlreadyExistsException,
    ReviewNotFoundException,
    ReviewVoteAlreadyExistsException,
    SelfReviewVoteForbiddenException,
    TargetNotFoundException,
    UserNotFoundException,
)
from src.modules.reviews.domain.models import Review, Target, TargetRating
from tests.unit.fake_repositories import (
    FakeReviewRepository,
    FakeReviewVoteRepository,
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
def review_repo() -> FakeReviewRepository:
    return FakeReviewRepository()


@pytest.fixture
def vote_repo() -> FakeReviewVoteRepository:
    return FakeReviewVoteRepository()


@pytest.fixture
def event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def user_gateway() -> FakeUserGateway:
    return FakeUserGateway()


async def test_create_review_happy_path(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="fight-club-1999", title="Fight Club", category="movie")
    await target_repo.save(target)
    rating = TargetRating.create_empty(target.id)
    await rating_repo.save(rating)

    user_id = uuid7()
    user_gateway.add_user(user_id)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateReviewDTO(
        score=5,
        title="First rule of Fight Club",
        content="The first rule of Fight Club is: you do not talk about Fight Club.",
    )

    review_id = await use_case.execute(
        target_id=target.id,
        user_id=user_id,
        dto=dto,
    )

    assert isinstance(review_id, UUID)
    review = await review_repo.get_by_id(review_id)
    assert review is not None
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
    assert events[0].review_id == review_id
    assert events[0].target_id == target.id


async def test_create_review_target_not_found(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    user_id = uuid7()
    user_gateway.add_user(user_id)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateReviewDTO(score=4, content="Valid review text for testing purposes.")
    with pytest.raises(TargetNotFoundException):
        await use_case.execute(
            target_id=uuid7(),
            user_id=user_id,
            dto=dto,
        )


async def test_create_review_duplicate_raises_exception(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="matrix", title="The Matrix", category="movie")
    await target_repo.save(target)

    user_id = uuid7()
    user_gateway.add_user(user_id)

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
        user_gateway=user_gateway,
    )

    dto = CreateReviewDTO(score=4, content="Attempting second review from same user.")
    with pytest.raises(ReviewAlreadyExistsException):
        await use_case.execute(
            target_id=target.id,
            user_id=user_id,
            dto=dto,
        )


async def test_create_review_author_not_found(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="avatar", title="Avatar", category="movie")
    await target_repo.save(target)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateReviewDTO(score=5, content="Valid text for non-existent author test.")
    with pytest.raises(UserNotFoundException):
        await use_case.execute(
            target_id=target.id,
            user_id=uuid7(),
            dto=dto,
        )


async def test_create_review_author_deactivated(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="titanic", title="Titanic", category="movie")
    await target_repo.save(target)

    user_id = uuid7()
    user_gateway.add_user(user_id, is_active=False)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    dto = CreateReviewDTO(score=5, content="Valid text for deactivated author test.")
    with pytest.raises(AccountDeactivatedException):
        await use_case.execute(
            target_id=target.id,
            user_id=user_id,
            dto=dto,
        )


async def test_vote_review_use_case(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    author_id = uuid7()
    voter_id = uuid7()
    target_id = uuid7()

    user_gateway.add_user(author_id)
    user_gateway.add_user(voter_id)

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
        user_gateway=user_gateway,
    )

    # 1. Author votes for own review -> Forbidden
    with pytest.raises(SelfReviewVoteForbiddenException):
        await use_case.execute(
            review_id=review.id,
            user_id=author_id,
            is_helpful=True,
        )

    # 2. Voter votes helpful -> success
    vote_id = await use_case.execute(
        review_id=review.id,
        user_id=voter_id,
        is_helpful=True,
    )
    assert isinstance(vote_id, UUID)
    vote = await vote_repo.get_by_review_and_user(review.id, voter_id)
    assert vote is not None
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
    changed_vote_id = await use_case.execute(
        review_id=review.id,
        user_id=voter_id,
        is_helpful=False,
    )
    assert changed_vote_id == vote.id
    changed_vote = await vote_repo.get_by_review_and_user(review.id, voter_id)
    assert changed_vote is not None
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

    # 6. Non-existent voter -> UserNotFoundException
    with pytest.raises(UserNotFoundException):
        await use_case.execute(
            review_id=review.id,
            user_id=uuid7(),
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
    mod_id = await use_case.execute(review_id=review.id, action="hide")
    assert isinstance(mod_id, UUID)
    mod_review = await review_repo.get_by_id(mod_id)
    assert mod_review is not None
    assert mod_review.status == "hidden"
    assert rating.total_reviews == 0

    # 2. Action: publish -> review restored, rating added back
    pub_id = await use_case.execute(review_id=review.id, action="publish")
    pub_review = await review_repo.get_by_id(pub_id)
    assert pub_review is not None
    assert pub_review.status == "published"
    assert rating.total_reviews == 1

    # 3. Action: flag -> review marked flagged
    flag_id = await use_case.execute(review_id=review.id, action="flag")
    flag_review = await review_repo.get_by_id(flag_id)
    assert flag_review is not None
    assert flag_review.status == "flagged"

    # Event was published
    assert event_bus.has_event_of_type(ReviewUpdatedEvent)


async def test_update_review_happy_path(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(3)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=3,
        content="Decent film, nothing special initially.",
    )
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    dto = UpdateReviewDTO(
        score=5,
        title="Changed my mind!",
        content="Upon rewatching, this is truly a masterpiece.",
        version=1,
    )

    updated_id = await use_case.execute(
        target_id=target_id,
        review_id=review.id,
        user_id=user_id,
        dto=dto,
    )

    assert updated_id == review.id
    assert uow.committed is True

    updated_review = await review_repo.get_by_id(review.id)
    assert updated_review is not None
    assert updated_review.score == 5
    assert updated_review.title == "Changed my mind!"
    assert updated_review.content == "Upon rewatching, this is truly a masterpiece."

    # Rating should be updated (star 3 count decremented, star 5 count incremented)
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.star_3_count == 0
    assert updated_rating.star_5_count == 1
    assert updated_rating.average_score == Decimal("5.00")

    events = event_bus.get_events_of_type(ReviewUpdatedEvent)
    assert len(events) == 1
    assert events[0].old_score == 3
    assert events[0].new_score == 5


async def test_update_review_non_author_forbidden(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    author_id = uuid7()
    stranger_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=author_id,
        score=4,
        content="Great movie with stunning visuals.",
    )
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    dto = UpdateReviewDTO(score=1, content="Hacked review content by stranger.", version=1)

    with pytest.raises(ForbiddenException):
        await use_case.execute(
            target_id=target_id,
            review_id=review.id,
            user_id=stranger_id,
            dto=dto,
        )


async def test_update_review_target_mismatch(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    other_target_id = uuid7()
    user_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=4,
        content="Great movie with stunning visuals.",
    )
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    dto = UpdateReviewDTO(score=5, content="Updated content for movie.", version=1)

    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=other_target_id,
            review_id=review.id,
            user_id=user_id,
            dto=dto,
        )


async def test_update_review_occ_conflict(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=4,
        content="Great movie with stunning visuals.",
    )
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    dto = UpdateReviewDTO(score=5, content="Updated content for movie.", version=99)

    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(
            target_id=target_id,
            review_id=review.id,
            user_id=user_id,
            dto=dto,
        )


async def test_delete_review_by_author(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(5)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=5,
        content="I will delete this review soon.",
    )
    await review_repo.save(review)

    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    await use_case.execute(
        target_id=target_id,
        review_id=review.id,
        user_id=user_id,
        has_moderate_permission=False,
    )

    assert uow.committed is True
    assert review.is_active is False
    assert review.deleted_at is not None

    # Rating should be decremented
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 0

    events = event_bus.get_events_of_type(ReviewDeletedEvent)
    assert len(events) == 1
    assert events[0].review_id == review.id
    assert events[0].score == 5


async def test_delete_review_by_moderator(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    author_id = uuid7()
    moderator_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(4)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target_id,
        user_id=author_id,
        score=4,
        content="Toxic content that moderator will delete.",
    )
    await review_repo.save(review)

    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    # Allowed because has_moderate_permission=True
    await use_case.execute(
        target_id=target_id,
        review_id=review.id,
        user_id=moderator_id,
        has_moderate_permission=True,
    )

    assert uow.committed is True
    assert review.is_active is False
    assert rating.total_reviews == 0


async def test_delete_review_non_author_forbidden(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    author_id = uuid7()
    stranger_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=author_id,
        score=4,
        content="Normal review content.",
    )
    await review_repo.save(review)

    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    with pytest.raises(ForbiddenException):
        await use_case.execute(
            target_id=target_id,
            review_id=review.id,
            user_id=stranger_id,
            has_moderate_permission=False,
        )


async def test_moderate_review_with_occ(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    review = Review.create(
        target_id=target_id,
        user_id=uuid7(),
        score=5,
        content="Review to be moderated with OCC.",
    )
    await review_repo.save(review)

    use_case = ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    # Mismatched version -> OptimisticLockConflictException
    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(review_id=review.id, action="hide", version=99)

    # Correct version -> Success
    await use_case.execute(review_id=review.id, action="hide", version=1)
    assert review.status == "hidden"


async def test_moderate_review_rating_lifecycle_publish_flag_hide_publish(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(5)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=5,
        content="Suspicious but initially published review.",
    )
    await review_repo.save(review)

    use_case = ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    # Initial state: published, counted in rating
    assert review.status == "published"
    assert review.is_counted_in_rating is True
    assert rating.total_reviews == 1
    assert rating.star_5_count == 1
    assert rating.average_score == Decimal("5.00")

    # Step 1: Flag the review -> still counted in rating
    await use_case.execute(review_id=review.id, action="flag")
    assert review.status == "flagged"
    assert review.is_counted_in_rating is True
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 1
    assert updated_rating.star_5_count == 1
    assert updated_rating.average_score == Decimal("5.00")

    # Step 2: Hide the flagged review -> must be removed from rating
    await use_case.execute(review_id=review.id, action="hide")
    assert review.status == "hidden"
    assert review.is_counted_in_rating is False
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 0
    assert updated_rating.star_5_count == 0
    assert updated_rating.average_score == Decimal("0.00")

    # Step 3: Publish the hidden review back -> must be restored into rating
    await use_case.execute(review_id=review.id, action="publish")
    assert review.status == "published"
    assert review.is_counted_in_rating is True
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 1
    assert updated_rating.star_5_count == 1
    assert updated_rating.average_score == Decimal("5.00")


async def test_delete_flagged_review_decrements_rating(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(4)
    await rating_repo.save(rating)

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=4,
        content="Flagged review that user decides to delete.",
    )
    review.flag()
    await review_repo.save(review)

    assert review.is_counted_in_rating is True

    delete_uc = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )

    await delete_uc.execute(
        target_id=target_id,
        review_id=review.id,
        user_id=user_id,
        has_moderate_permission=False,
    )

    assert review.is_active is False
    assert review.is_counted_in_rating is False
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.total_reviews == 0
    assert updated_rating.star_4_count == 0


async def test_create_review_rating_none_creates_empty_rating(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="movie-no-rating", title="Movie", category="movie")
    await target_repo.save(target)
    # Do NOT pre-create rating in rating_repo

    user_id = uuid7()
    user_gateway.add_user(user_id)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )
    dto = CreateReviewDTO(score=4, content="First review on a target without pre-existing rating.")
    review_id = await use_case.execute(target_id=target.id, user_id=user_id, dto=dto)

    assert review_id is not None
    rating = await rating_repo.get_by_target_id(target.id)
    assert rating is not None
    assert rating.total_reviews == 1
    assert rating.star_4_count == 1
    assert rating.average_score == Decimal("4.00")


async def test_create_review_on_deactivated_target_raises(
    uow: FakeUnitOfWork,
    target_repo: FakeTargetRepository,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    target = Target.create(slug="deleted-movie", title="Deleted Movie", category="movie")
    target.soft_delete()
    await target_repo.save(target)

    user_id = uuid7()
    user_gateway.add_user(user_id)

    use_case = CreateReviewUseCase(
        uow=uow,
        target_repo=target_repo,
        rating_repo=rating_repo,
        review_repo=review_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )
    dto = CreateReviewDTO(score=5, content="Trying to review a soft-deleted target.")
    with pytest.raises(TargetNotFoundException):
        await use_case.execute(target_id=target.id, user_id=user_id, dto=dto)


async def test_update_review_not_found(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    dto = UpdateReviewDTO(score=4, content="Updated review content.", version=1)
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=uuid7(),
            review_id=uuid7(),
            user_id=uuid7(),
            dto=dto,
        )


async def test_update_review_deactivated_raises(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()
    review = Review.create(target_id=target_id, user_id=user_id, score=3, content="Original content here.")
    review.soft_delete()
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    dto = UpdateReviewDTO(score=4, content="Trying to update inactive review.", version=1)
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=target_id,
            review_id=review.id,
            user_id=user_id,
            dto=dto,
        )


async def test_update_review_same_score_no_rating_recalc(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    rating = TargetRating.create_empty(target_id)
    rating.apply_new_review(4)
    await rating_repo.save(rating)

    review = Review.create(target_id=target_id, user_id=user_id, score=4, content="Initial score 4 content.")
    await review_repo.save(review)

    use_case = UpdateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    dto = UpdateReviewDTO(score=4, content="Updated text with identical score 4.", version=1)
    await use_case.execute(
        target_id=target_id,
        review_id=review.id,
        user_id=user_id,
        dto=dto,
    )

    # Score unchanged, rating count remains 1 and avg remains 4.00
    updated_rating = await rating_repo.get_by_target_id(target_id)
    assert updated_rating is not None
    assert updated_rating.star_4_count == 1
    assert updated_rating.total_reviews == 1
    assert updated_rating.average_score == Decimal("4.00")


async def test_delete_review_not_found(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=uuid7(),
            review_id=uuid7(),
            user_id=uuid7(),
        )


async def test_delete_review_target_mismatch_raises(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    different_target_id = uuid7()
    user_id = uuid7()

    review = Review.create(target_id=target_id, user_id=user_id, score=5, content="Review for target 1.")
    await review_repo.save(review)

    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=different_target_id,
            review_id=review.id,
            user_id=user_id,
        )


async def test_delete_review_already_deactivated_raises(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    user_id = uuid7()

    review = Review.create(target_id=target_id, user_id=user_id, score=5, content="Review to be deleted.")
    review.soft_delete()
    await review_repo.save(review)

    use_case = DeleteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            target_id=target_id,
            review_id=review.id,
            user_id=user_id,
        )


async def test_moderate_review_not_found(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    use_case = ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(review_id=uuid7(), action="hide")


async def test_moderate_review_deactivated_raises(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    review_repo: FakeReviewRepository,
    event_bus: FakeEventBus,
) -> None:
    target_id = uuid7()
    review = Review.create(target_id=target_id, user_id=uuid7(), score=5, content="Deactivated review.")
    review.soft_delete()
    await review_repo.save(review)

    use_case = ModerateReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        rating_repo=rating_repo,
        event_bus=event_bus,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(review_id=review.id, action="hide")


async def test_vote_review_deactivated_user_raises(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    user_id = uuid7()
    user_gateway.add_user(user_id, is_active=False)

    use_case = VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )
    with pytest.raises(AccountDeactivatedException):
        await use_case.execute(
            review_id=uuid7(),
            user_id=user_id,
            is_helpful=True,
        )


async def test_vote_review_deactivated_review_raises(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    voter_id = uuid7()
    user_gateway.add_user(voter_id)

    author_id = uuid7()
    review = Review.create(target_id=uuid7(), user_id=author_id, score=5, content="Inactive review content.")
    review.soft_delete()
    await review_repo.save(review)

    use_case = VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )
    with pytest.raises(ReviewNotFoundException):
        await use_case.execute(
            review_id=review.id,
            user_id=voter_id,
            is_helpful=True,
        )


async def test_vote_review_initial_unhelpful_vote(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    voter_id = uuid7()
    user_gateway.add_user(voter_id)

    author_id = uuid7()
    review = Review.create(target_id=uuid7(), user_id=author_id, score=2, content="Poor quality review.")
    await review_repo.save(review)

    use_case = VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )
    vote_id = await use_case.execute(
        review_id=review.id,
        user_id=voter_id,
        is_helpful=False,
    )
    assert vote_id is not None
    assert review.unhelpful_count == 1
    assert review.helpful_count == 0


async def test_vote_review_change_from_unhelpful_to_helpful(
    uow: FakeUnitOfWork,
    review_repo: FakeReviewRepository,
    vote_repo: FakeReviewVoteRepository,
    event_bus: FakeEventBus,
    user_gateway: FakeUserGateway,
) -> None:
    voter_id = uuid7()
    user_gateway.add_user(voter_id)

    author_id = uuid7()
    review = Review.create(target_id=uuid7(), user_id=author_id, score=4, content="Initial helpful text.")
    await review_repo.save(review)

    use_case = VoteReviewUseCase(
        uow=uow,
        review_repo=review_repo,
        vote_repo=vote_repo,
        event_bus=event_bus,
        user_gateway=user_gateway,
    )

    # First vote: unhelpful
    await use_case.execute(review_id=review.id, user_id=voter_id, is_helpful=False)
    assert review.unhelpful_count == 1
    assert review.helpful_count == 0

    # Change vote: unhelpful -> helpful
    await use_case.execute(review_id=review.id, user_id=voter_id, is_helpful=True)
    assert review.unhelpful_count == 0
    assert review.helpful_count == 1
