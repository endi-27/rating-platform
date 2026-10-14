from dataclasses import dataclass
from uuid import UUID

from uuid6 import uuid7

from src.core.domain.base import BaseEntity


@dataclass(kw_only=True)
class ReviewVote(BaseEntity):
    """
    Доменна сутність голосу за корисність відгуку (ReviewVote).
    is_helpful = True (👍 Корисно), is_helpful = False (👎 Не корисно).
    """

    review_id: UUID
    user_id: UUID
    is_helpful: bool

    @classmethod
    def create(
        cls,
        *,
        review_id: UUID,
        user_id: UUID,
        is_helpful: bool,
    ) -> "ReviewVote":
        """Фабричний метод створення нового голосу."""
        return cls(
            id=uuid7(),
            review_id=review_id,
            user_id=user_id,
            is_helpful=is_helpful,
        )

    def change_vote(self, is_helpful: bool) -> None:
        """Зміна голосу (наприклад, з 'корисно' на 'не корисно')."""
        self.is_helpful = is_helpful
