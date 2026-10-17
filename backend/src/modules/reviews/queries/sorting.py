from enum import StrEnum


class TargetSortField(StrEnum):
    """Дозволені поля для сортування каталогу об'єктів оцінювання."""

    CREATED_AT = "created_at"
    TITLE = "title"
    AVERAGE_SCORE = "average_score"
    BAYESIAN_SCORE = "bayesian_score"
    TOTAL_REVIEWS = "total_reviews"


class ReviewSortField(StrEnum):
    """Дозволені поля для сортування стрічки відгуків."""

    CREATED_AT = "created_at"
    SCORE = "score"
    HELPFUL_COUNT = "helpful_count"
