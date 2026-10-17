from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from uuid6 import uuid7

from src.core.domain.base import AggregateRoot
from src.core.exceptions import DomainException
from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.domain.exceptions import InvalidScoreException


@dataclass(kw_only=True)
class Review(AggregateRoot):
    """
    Доменний агрегат відгуку користувача (Review).
    Користувач залишає оцінку (1..5) та текст відгуку на конкретний Target.
    """

    target_id: UUID
    user_id: UUID
    score: int
    content: str
    title: str | None = None
    status: ReviewStatus = ReviewStatus.PUBLISHED
    helpful_count: int = 0
    unhelpful_count: int = 0

    @property
    def is_counted_in_rating(self) -> bool:
        """Чи враховується цей відгук у розрахунку агрегованого рейтингу цілі."""
        return self.is_active and self.status != ReviewStatus.HIDDEN

    def __post_init__(self) -> None:
        self._validate_score(self.score)
        self._validate_content(self.content)
        self.content = self.content.strip()
        if self.title is not None:
            clean_title = self.title.strip()
            if len(clean_title) > 150:
                raise DomainException("Заголовок відгуку не може перевищувати 150 символів.")
            self.title = clean_title if clean_title else None

    @staticmethod
    def _validate_score(score: int) -> None:
        if isinstance(score, bool) or not (1 <= score <= 5):
            raise InvalidScoreException(score)

    @staticmethod
    def _validate_content(content: str) -> None:
        clean = content.strip()
        if len(clean) < 10 or len(clean) > 5000:
            raise DomainException("Текст відгуку повинен містити від 10 до 5000 символів.")

    @classmethod
    def create(
        cls,
        *,
        target_id: UUID,
        user_id: UUID,
        score: int,
        content: str,
        title: str | None = None,
    ) -> "Review":
        """Фабричний метод створення нового опублікованого відгуку."""
        return cls(
            id=uuid7(),
            target_id=target_id,
            user_id=user_id,
            score=score,
            content=content.strip(),
            title=title.strip() if title and title.strip() else None,
            status=ReviewStatus.PUBLISHED,
        )

    def update_content(
        self,
        *,
        score: int | None = None,
        title: str | None = None,
        content: str | None = None,
    ) -> None:
        """Оновлення оцінки та змісту власного відгуку."""
        self.ensure_active(action_phrase="оновити деактивований відгук")

        if score is not None:
            self._validate_score(score)
            self.score = score

        if content is not None:
            self._validate_content(content)
            self.content = content.strip()

        if title is not None:
            clean_title = title.strip()
            if len(clean_title) > 150:
                raise DomainException("Заголовок відгуку не може перевищувати 150 символів.")
            self.title = clean_title if clean_title else None

        self.updated_at = datetime.now(UTC)

    def hide(self) -> None:
        """Модерація: приховати відгук з публічного простору."""
        self.ensure_active(action_phrase="модерувати деактивований відгук")
        self.status = ReviewStatus.HIDDEN
        self.updated_at = datetime.now(UTC)

    def publish(self) -> None:
        """Модерація: відновити публічний статус відгуку."""
        self.ensure_active(action_phrase="модерувати деактивований відгук")
        self.status = ReviewStatus.PUBLISHED
        self.updated_at = datetime.now(UTC)

    def flag(self) -> None:
        """Позначити відгук як підозрілий для перевірки модератором."""
        self.ensure_active(action_phrase="модерувати деактивований відгук")
        self.status = ReviewStatus.FLAGGED
        self.updated_at = datetime.now(UTC)

    def add_helpful_vote(self) -> None:
        """Збільшити лічильник схвальних голосів."""
        self.ensure_active(action_phrase="голосувати за деактивований відгук")
        self.helpful_count += 1
        self.updated_at = datetime.now(UTC)

    def remove_helpful_vote(self) -> None:
        """Зменшити лічильник схвальних голосів."""
        self.ensure_active(action_phrase="голосувати за деактивований відгук")
        self.helpful_count = max(0, self.helpful_count - 1)
        self.updated_at = datetime.now(UTC)

    def add_unhelpful_vote(self) -> None:
        """Збільшити лічильник несхвальних голосів."""
        self.ensure_active(action_phrase="голосувати за деактивований відгук")
        self.unhelpful_count += 1
        self.updated_at = datetime.now(UTC)

    def remove_unhelpful_vote(self) -> None:
        """Зменшити лічильник несхвальних голосів."""
        self.ensure_active(action_phrase="голосувати за деактивований відгук")
        self.unhelpful_count = max(0, self.unhelpful_count - 1)
        self.updated_at = datetime.now(UTC)
