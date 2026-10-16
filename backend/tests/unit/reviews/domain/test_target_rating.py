from decimal import Decimal

import pytest
from uuid6 import uuid7

from src.modules.reviews.domain.exceptions import InvalidScoreException
from src.modules.reviews.domain.models import TargetRating


def test_target_rating_empty_initialization() -> None:
    target_id = uuid7()
    rating = TargetRating.create_empty(target_id)

    assert rating.target_id == target_id
    assert rating.total_reviews == 0
    assert rating.average_score == Decimal("0.00")
    assert rating.bayesian_score == Decimal("0.00")
    assert rating.star_1_count == 0
    assert rating.star_2_count == 0
    assert rating.star_3_count == 0
    assert rating.star_4_count == 0
    assert rating.star_5_count == 0
    assert rating.version == 1
    assert rating.last_calculated_at is not None


def test_apply_new_review_success() -> None:
    target_id = uuid7()
    rating = TargetRating.create_empty(target_id)

    # 1st review: 5 stars
    rating.apply_new_review(5)
    assert rating.total_reviews == 1
    assert rating.star_5_count == 1
    assert rating.average_score == Decimal("5.00")

    # 2nd review: 4 stars -> avg = 4.50
    rating.apply_new_review(4)
    assert rating.total_reviews == 2
    assert rating.star_4_count == 1
    assert rating.average_score == Decimal("4.50")

    # 3rd review: 1 star -> (5 + 4 + 1) / 3 = 10 / 3 = 3.3333 -> 3.33
    rating.apply_new_review(1)
    assert rating.total_reviews == 3
    assert rating.star_1_count == 1
    assert rating.average_score == Decimal("3.33")

    # 4th review: 2 stars
    rating.apply_new_review(2)
    assert rating.total_reviews == 4
    assert rating.star_2_count == 1

    # 5th review: 3 stars -> (5+4+1+2+3) / 5 = 15/5 = 3.00
    rating.apply_new_review(3)
    assert rating.total_reviews == 5
    assert rating.star_3_count == 1
    assert rating.average_score == Decimal("3.00")


def test_apply_new_review_invalid_score() -> None:
    rating = TargetRating.create_empty(uuid7())

    with pytest.raises(InvalidScoreException):
        rating.apply_new_review(0)

    with pytest.raises(InvalidScoreException):
        rating.apply_new_review(6)

    with pytest.raises(InvalidScoreException):
        rating.apply_new_review(-1)


def test_apply_updated_review() -> None:
    rating = TargetRating.create_empty(uuid7())
    rating.apply_new_review(5)  # total=1, avg=5.00

    # Score unchanged
    rating.apply_updated_review(5, 5)
    assert rating.total_reviews == 1
    assert rating.average_score == Decimal("5.00")

    # Score changed 5 -> 1
    rating.apply_updated_review(5, 1)
    assert rating.total_reviews == 1
    assert rating.star_5_count == 0
    assert rating.star_1_count == 1
    assert rating.average_score == Decimal("1.00")


def test_apply_deleted_review() -> None:
    rating = TargetRating.create_empty(uuid7())
    rating.apply_new_review(5)
    rating.apply_new_review(3)
    assert rating.total_reviews == 2
    assert rating.average_score == Decimal("4.00")

    # Delete 5-star review
    rating.apply_deleted_review(5)
    assert rating.total_reviews == 1
    assert rating.star_5_count == 0
    assert rating.star_3_count == 1
    assert rating.average_score == Decimal("3.00")

    # Delete 3-star review -> 0 reviews
    rating.apply_deleted_review(3)
    assert rating.total_reviews == 0
    assert rating.star_3_count == 0
    assert rating.average_score == Decimal("0.00")
    assert rating.bayesian_score == Decimal("0.00")


def test_calculate_bayesian_score() -> None:
    target_id = uuid7()
    rating = TargetRating.create_empty(target_id)
    global_mean = Decimal("3.50")
    min_threshold = 5

    # 0 reviews: (0/(0+5))*0 + (5/(0+5))*3.5 = 3.50
    # Formula: WR = (v / (v + m)) * R + (m / (v + m)) * C
    # When v=0, (0/5)*0 + (5/5)*3.50 = 3.50
    bayesian = rating.calculate_bayesian_score(
        min_votes_threshold=min_threshold,
        global_mean=global_mean,
    )
    assert bayesian == Decimal("3.50")

    # Target with 5 perfect reviews: v=5, m=5, R=5.00, C=3.50
    # WR = (5/10)*5.00 + (5/10)*3.50 = 2.50 + 1.75 = 4.25
    for _ in range(5):
        rating.apply_new_review(5)

    bayesian = rating.calculate_bayesian_score(
        min_votes_threshold=min_threshold,
        global_mean=global_mean,
    )
    assert rating.average_score == Decimal("5.00")
    assert bayesian == Decimal("4.25")

    # Edge case: v + m == 0
    empty_rating = TargetRating.create_empty(uuid7())
    assert empty_rating.calculate_bayesian_score(
        min_votes_threshold=0,
        global_mean=global_mean,
    ) == Decimal("0.00")


def test_apply_updated_review_intermediate_scores() -> None:
    rating = TargetRating.create_empty(uuid7())
    rating.apply_new_review(1)
    assert rating.star_1_count == 1

    # 1 -> 2
    rating.apply_updated_review(1, 2)
    assert rating.star_1_count == 0
    assert rating.star_2_count == 1
    assert rating.average_score == Decimal("2.00")

    # 2 -> 3
    rating.apply_updated_review(2, 3)
    assert rating.star_2_count == 0
    assert rating.star_3_count == 1
    assert rating.average_score == Decimal("3.00")

    # 3 -> 4
    rating.apply_updated_review(3, 4)
    assert rating.star_3_count == 0
    assert rating.star_4_count == 1
    assert rating.average_score == Decimal("4.00")

    # 4 -> 2
    rating.apply_updated_review(4, 2)
    assert rating.star_4_count == 0
    assert rating.star_2_count == 1
    assert rating.average_score == Decimal("2.00")


def test_apply_deleted_review_all_scores() -> None:
    rating = TargetRating.create_empty(uuid7())
    for s in (1, 2, 4):
        rating.apply_new_review(s)

    assert rating.star_1_count == 1
    assert rating.star_2_count == 1
    assert rating.star_4_count == 1
    assert rating.total_reviews == 3

    rating.apply_deleted_review(1)
    assert rating.star_1_count == 0
    assert rating.total_reviews == 2

    rating.apply_deleted_review(2)
    assert rating.star_2_count == 0
    assert rating.total_reviews == 1

    rating.apply_deleted_review(4)
    assert rating.star_4_count == 0
    assert rating.total_reviews == 0
