from uuid6 import uuid7

from src.modules.reviews.domain.models import ReviewVote


def test_review_vote_creation() -> None:
    review_id = uuid7()
    user_id = uuid7()

    vote = ReviewVote.create(
        review_id=review_id,
        user_id=user_id,
        is_helpful=True,
    )

    assert vote.id is not None
    assert vote.review_id == review_id
    assert vote.user_id == user_id
    assert vote.is_helpful is True
    assert vote.created_at is not None


def test_review_vote_change_vote() -> None:
    vote = ReviewVote.create(
        review_id=uuid7(),
        user_id=uuid7(),
        is_helpful=True,
    )

    assert vote.is_helpful is True
    vote.change_vote(False)
    assert vote.is_helpful is False
    vote.change_vote(True)
    assert vote.is_helpful is True


def test_review_vote_creation_unhelpful() -> None:
    review_id = uuid7()
    user_id = uuid7()

    vote = ReviewVote.create(
        review_id=review_id,
        user_id=user_id,
        is_helpful=False,
    )

    assert vote.id is not None
    assert vote.review_id == review_id
    assert vote.user_id == user_id
    assert vote.is_helpful is False
    assert vote.created_at is not None
