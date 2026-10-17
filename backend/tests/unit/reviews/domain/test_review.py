import pytest
from uuid6 import uuid7

from src.core.exceptions import (
    DomainException,
    InactiveEntityError,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
)
from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.domain.exceptions import InvalidScoreException
from src.modules.reviews.domain.models import Review


def test_review_creation_happy_path() -> None:
    target_id = uuid7()
    user_id = uuid7()

    review = Review.create(
        target_id=target_id,
        user_id=user_id,
        score=5,
        content="Great movie with stunning visuals and wonderful acting!",
        title="Masterpiece!",
    )

    assert review.id is not None
    assert review.target_id == target_id
    assert review.user_id == user_id
    assert review.score == 5
    assert review.content == "Great movie with stunning visuals and wonderful acting!"
    assert review.title == "Masterpiece!"
    assert review.status == ReviewStatus.PUBLISHED
    assert isinstance(review.status, ReviewStatus)
    assert review.helpful_count == 0
    assert review.unhelpful_count == 0
    assert review.is_active is True
    assert review.version == 1
    assert review.created_at is not None
    assert review.updated_at is None


def test_review_score_validation() -> None:
    target_id = uuid7()
    user_id = uuid7()

    with pytest.raises(InvalidScoreException):
        Review.create(
            target_id=target_id,
            user_id=user_id,
            score=0,
            content="Valid content string for testing.",
        )

    with pytest.raises(InvalidScoreException):
        Review.create(
            target_id=target_id,
            user_id=user_id,
            score=6,
            content="Valid content string for testing.",
        )


def test_review_content_validation() -> None:
    target_id = uuid7()
    user_id = uuid7()

    # Content too short (< 10)
    with pytest.raises(DomainException, match="Текст відгуку повинен містити"):
        Review.create(
            target_id=target_id,
            user_id=user_id,
            score=5,
            content="Too short",
        )

    # Content too long (> 5000)
    with pytest.raises(DomainException, match="Текст відгуку повинен містити"):
        Review.create(
            target_id=target_id,
            user_id=user_id,
            score=5,
            content="A" * 5001,
        )

    # Title too long (> 150)
    with pytest.raises(DomainException, match="Заголовок відгуку не може"):
        Review(
            id=uuid7(),
            target_id=target_id,
            user_id=user_id,
            score=5,
            content="Valid content string for testing.",
            title="T" * 151,
        )


def test_review_update_content() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=4,
        content="Initial review text with enough characters.",
        title="Good movie",
    )

    review.update_content(
        score=5,
        title="Even better than I thought!",
        content="Updated review text that now explains why it is 5 stars.",
    )

    assert review.score == 5
    assert review.title == "Even better than I thought!"
    assert review.content == "Updated review text that now explains why it is 5 stars."
    assert review.updated_at is not None


def test_review_update_content_validation() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=4,
        content="Initial review text with enough characters.",
    )

    with pytest.raises(InvalidScoreException):
        review.update_content(score=7)

    with pytest.raises(DomainException, match="Текст відгуку повинен містити"):
        review.update_content(content="Short")

    # Inactive review update raises InactiveEntityError
    review.soft_delete()
    with pytest.raises(InactiveEntityError):
        review.update_content(score=3)


def test_review_moderation_status_transitions() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Initial review text with enough characters.",
    )
    assert review.status == ReviewStatus.PUBLISHED
    assert isinstance(review.status, ReviewStatus)

    review.hide()
    assert review.status == ReviewStatus.HIDDEN
    assert review.updated_at is not None

    review.publish()
    assert review.status == ReviewStatus.PUBLISHED

    review.flag()
    assert review.status == ReviewStatus.FLAGGED


def test_review_vote_counters() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Initial review text with enough characters.",
    )

    # Helpful votes
    review.add_helpful_vote()
    review.add_helpful_vote()
    assert review.helpful_count == 2

    review.remove_helpful_vote()
    assert review.helpful_count == 1

    review.remove_helpful_vote()
    review.remove_helpful_vote()
    assert review.helpful_count == 0  # does not go negative

    # Unhelpful votes
    review.add_unhelpful_vote()
    assert review.unhelpful_count == 1

    review.remove_unhelpful_vote()
    review.remove_unhelpful_vote()
    assert review.unhelpful_count == 0


def test_review_soft_delete_and_restore() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Initial review text with enough characters.",
    )
    assert review.is_active is True

    review.soft_delete()
    assert review.is_active is False  # pyrefly: ignore
    assert review.deleted_at is not None

    with pytest.raises(ResourceAlreadyInactiveException):
        review.soft_delete()

    review.restore()
    assert review.is_active is True
    assert review.deleted_at is None

    with pytest.raises(ResourceAlreadyActiveException):
        review.restore()


def test_review_update_content_title_too_long() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Valid content string for testing.",
    )
    with pytest.raises(DomainException, match="Заголовок відгуку не може"):
        review.update_content(title="A" * 151)


def test_review_is_counted_in_rating_property() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Valid content string for testing.",
    )
    # Published & active
    assert review.status == "published"
    assert review.is_counted_in_rating is True

    # Flagged & active
    review.flag()
    assert review.status == "flagged"
    assert review.is_counted_in_rating is True

    # Hidden & active
    review.hide()
    assert review.status == "hidden"
    assert review.is_counted_in_rating is False

    # Published back
    review.publish()
    assert review.is_counted_in_rating is True

    # Soft deleted
    review.soft_delete()
    assert review.is_active is False
    assert review.is_counted_in_rating is False

    # Restored
    review.restore()
    assert review.is_active is True
    assert review.is_counted_in_rating is True


def test_review_boolean_score_rejected() -> None:
    with pytest.raises(InvalidScoreException):
        Review.create(
            target_id=uuid7(),
            user_id=uuid7(),
            score=True,  # type: ignore[arg-type]
            content="Valid content string for testing.",
        )


def test_review_whitespace_title_and_content_normalization() -> None:
    # Whitespace-only title becomes None on create and direct init
    rev1 = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="   Valid content with spaces   ",
        title="     ",
    )
    assert rev1.title is None
    assert rev1.content == "Valid content with spaces"

    rev2 = Review(
        id=uuid7(),
        target_id=uuid7(),
        user_id=uuid7(),
        score=4,
        content="   Direct init content   ",
        title="   Direct Title   ",
    )
    assert rev2.title == "Direct Title"
    assert rev2.content == "Direct init content"

    # Update content with whitespace-only title resets title to None
    rev2.update_content(title="   ")
    assert rev2.title is None


def test_review_inactive_moderation_and_voting_raises() -> None:
    review = Review.create(
        target_id=uuid7(),
        user_id=uuid7(),
        score=5,
        content="Valid content string for testing.",
    )
    review.soft_delete()

    with pytest.raises(InactiveEntityError):
        review.hide()

    with pytest.raises(InactiveEntityError):
        review.publish()

    with pytest.raises(InactiveEntityError):
        review.flag()

    with pytest.raises(InactiveEntityError):
        review.add_helpful_vote()

    with pytest.raises(InactiveEntityError):
        review.remove_helpful_vote()

    with pytest.raises(InactiveEntityError):
        review.add_unhelpful_vote()

    with pytest.raises(InactiveEntityError):
        review.remove_unhelpful_vote()
