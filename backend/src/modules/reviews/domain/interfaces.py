from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.domain.models import Review, ReviewVote, Target, TargetRating


class IUserRecord(Protocol):
    """Мінімальний протокол сутності користувача, необхідний модулю Reviews."""

    @property
    def id(self) -> UUID: ...

    @property
    def deleted_at(self) -> datetime | None: ...


class IUserGateway(Protocol):
    """Шлюз до модуля Users для перевірки існування та активності користувачів."""

    async def get_user_by_id(self, user_id: UUID, /) -> IUserRecord | None:
        """Отримання даних користувача за ID."""
        ...


class ITargetRepository(ABC):
    """Інтерфейс сховища об'єктів оцінювання (Target)."""

    @abstractmethod
    async def save(self, target: Target, /) -> None:
        """Збереження або оновлення цільового об'єкта."""
        ...

    @abstractmethod
    async def get_by_id(self, target_id: UUID, /) -> Target | None:
        """Отримання об'єкта за його UUID."""
        ...

    @abstractmethod
    async def get_by_slug(self, slug: str, /) -> Target | None:
        """Отримання об'єкта за унікальним рядковим slug."""
        ...

    @abstractmethod
    async def exists_by_slug(self, slug: str, /, exclude_id: UUID | None = None) -> bool:
        """Перевірка наявності об'єкта з таким slug."""
        ...

    @abstractmethod
    async def list_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Target]:
        """Пагінований список об'єктів з опціональною фільтрацією."""
        ...

    @abstractmethod
    async def count_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        """Загальна кількість об'єктів за фільтрами."""
        ...

    @abstractmethod
    async def delete_by_id(self, target_id: UUID, /) -> bool:
        """Фізичне видалення об'єкта оцінювання."""
        ...


class ITargetRatingRepository(ABC):
    """Інтерфейс сховища агрегованого знімка рейтингу (TargetRating)."""

    @abstractmethod
    async def save(self, rating: TargetRating, /) -> None:
        """Збереження або оновлення агрегованого рейтингу."""
        ...

    @abstractmethod
    async def get_by_target_id(self, target_id: UUID, /) -> TargetRating | None:
        """Отримання рейтингу за target_id (Shard Key)."""
        ...

    @abstractmethod
    async def get_global_mean_score(self) -> Decimal:
        """Отримання середнього балу по всій платформі для байєсівського згладжування."""
        ...


class IReviewRepository(ABC):
    """Інтерфейс сховища відгуків користувачів (Review)."""

    @abstractmethod
    async def save(self, review: Review, /) -> None:
        """Збереження або оновлення відгуку."""
        ...

    @abstractmethod
    async def get_by_id(self, review_id: UUID, /) -> Review | None:
        """Отримання відгуку за його id."""
        ...

    @abstractmethod
    async def get_by_target_and_user(self, target_id: UUID, user_id: UUID, /) -> Review | None:
        """Отримання відгуку конкретного користувача на конкретний таргет (для перевірки One Review)."""
        ...

    @abstractmethod
    async def list_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Review]:
        """Отримання списку відгуків об'єкта (виключно з фільтром за target_id під шардинг)."""
        ...

    @abstractmethod
    async def count_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
    ) -> int:
        """Підрахунок кількості відгуків об'єкта."""
        ...

    @abstractmethod
    async def delete_by_id(self, review_id: UUID, /) -> bool:
        """Фізичне видалення відгуку."""
        ...


class IReviewVoteRepository(ABC):
    """Інтерфейс сховища оцінок корисності відгуків (ReviewVote)."""

    @abstractmethod
    async def save(self, vote: ReviewVote, /) -> None:
        """Збереження голосу."""
        ...

    @abstractmethod
    async def get_by_review_and_user(self, review_id: UUID, user_id: UUID, /) -> ReviewVote | None:
        """Отримання голосу конкретного користувача за конкретний відгук."""
        ...

    @abstractmethod
    async def delete_by_id(self, vote_id: UUID, /) -> bool:
        """Видалення голосу."""
        ...
