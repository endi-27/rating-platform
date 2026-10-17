from uuid import UUID

from src.core.events import BaseEvent


class TargetCreatedEvent(BaseEvent):
    """Подія створення нового об'єкта оцінювання."""

    target_id: UUID
    slug: str
    category: str


class TargetUpdatedEvent(BaseEvent):
    """Подія оновлення об'єкта оцінювання."""

    target_id: UUID
    version: int


class TargetDeletedEvent(BaseEvent):
    """Подія видалення об'єкта оцінювання."""

    target_id: UUID


class ReviewCreatedEvent(BaseEvent):
    """Подія створення нового відгуку (інвалідація кешу + фоновий перерахунок)."""

    review_id: UUID
    target_id: UUID
    user_id: UUID
    score: int


class ReviewUpdatedEvent(BaseEvent):
    """Подія оновлення відгуку або його оцінки."""

    review_id: UUID
    target_id: UUID
    user_id: UUID
    old_score: int
    new_score: int


class ReviewDeletedEvent(BaseEvent):
    """Подія видалення відгуку."""

    review_id: UUID
    target_id: UUID
    user_id: UUID
    score: int


class ReviewVotedEvent(BaseEvent):
    """Подія голосування за корисність відгуку."""

    vote_id: UUID
    review_id: UUID
    user_id: UUID
    is_helpful: bool


class TargetRatingRecalculatedEvent(BaseEvent):
    """Подія перерахунку рейтингу (наприклад, байєсівського бала)."""

    target_id: UUID
    total_reviews: int
    average_score: float
    bayesian_score: float
