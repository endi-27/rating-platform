from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.reviews.domain.enums import ReviewStatus
from src.modules.reviews.domain.interfaces import (
    IReviewRepository,
    IReviewVoteRepository,
    ITargetRatingRepository,
    ITargetRepository,
    IUserGateway,
)
from src.modules.reviews.domain.models import Review, ReviewVote, Target, TargetRating
from src.modules.users.queries.dto import UserResponseDTO


class FakeTargetRepository(ITargetRepository):
    """Швидкий тестовий дублер сховища Target."""

    def __init__(self) -> None:
        self.targets: dict[UUID, Target] = {}

    async def save(self, target: Target, /) -> None:
        self.targets[target.id] = target

    async def get_by_id(self, target_id: UUID, /) -> Target | None:
        return self.targets.get(target_id)

    async def get_by_slug(self, slug: str, /) -> Target | None:
        for t in self.targets.values():
            if t.slug == slug:
                return t
        return None

    async def exists_by_slug(self, slug: str, /, exclude_id: UUID | None = None) -> bool:
        return any(t.slug == slug and (exclude_id is None or t.id != exclude_id) for t in self.targets.values())

    async def list_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Target]:
        items = [t for t in self.targets.values() if t.is_active]
        if category:
            items = [t for t in items if t.category == category]
        if search:
            s = search.lower()
            items = [t for t in items if s in t.title.lower() or s in t.slug.lower()]
        return items[offset : offset + limit]

    async def count_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        items = [t for t in self.targets.values() if t.is_active]
        if category:
            items = [t for t in items if t.category == category]
        if search:
            s = search.lower()
            items = [t for t in items if s in t.title.lower() or s in t.slug.lower()]
        return len(items)

    async def delete_by_id(self, target_id: UUID, /) -> bool:
        if target_id in self.targets:
            del self.targets[target_id]
            return True
        return False


class FakeTargetRatingRepository(ITargetRatingRepository):
    """Швидкий тестовий дублер сховища TargetRating."""

    def __init__(self) -> None:
        self.ratings: dict[UUID, TargetRating] = {}
        self.global_mean: Decimal = Decimal("3.50")

    async def save(self, rating: TargetRating, /) -> None:
        self.ratings[rating.target_id] = rating

    async def get_by_target_id(self, target_id: UUID, /) -> TargetRating | None:
        return self.ratings.get(target_id)

    async def get_global_mean_score(self) -> Decimal:
        return self.global_mean


class FakeReviewRepository(IReviewRepository):
    """Швидкий тестовий дублер сховища Review."""

    def __init__(self) -> None:
        self.reviews: dict[UUID, Review] = {}

    async def save(self, review: Review, /) -> None:
        self.reviews[review.id] = review

    async def get_by_id(self, review_id: UUID, /) -> Review | None:
        return self.reviews.get(review_id)

    async def get_by_target_and_user(self, target_id: UUID, user_id: UUID, /) -> Review | None:
        for r in self.reviews.values():
            if r.target_id == target_id and r.user_id == user_id and r.is_active:
                return r
        return None

    async def list_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Review]:
        items = [r for r in self.reviews.values() if r.target_id == target_id and r.status == status and r.is_active]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[offset : offset + limit]

    async def count_by_target(
        self,
        target_id: UUID,
        *,
        status: ReviewStatus | str = ReviewStatus.PUBLISHED,
    ) -> int:
        return len(
            [r for r in self.reviews.values() if r.target_id == target_id and r.status == status and r.is_active]
        )

    async def delete_by_id(self, review_id: UUID, /) -> bool:
        if review_id in self.reviews:
            del self.reviews[review_id]
            return True
        return False


class FakeReviewVoteRepository(IReviewVoteRepository):
    """Швидкий тестовий дублер сховища ReviewVote."""

    def __init__(self) -> None:
        self.votes: dict[UUID, ReviewVote] = {}

    async def save(self, vote: ReviewVote, /) -> None:
        self.votes[vote.id] = vote

    async def get_by_review_and_user(self, review_id: UUID, user_id: UUID, /) -> ReviewVote | None:
        for v in self.votes.values():
            if v.review_id == review_id and v.user_id == user_id:
                return v
        return None

    async def delete_by_id(self, vote_id: UUID, /) -> bool:
        if vote_id in self.votes:
            del self.votes[vote_id]
            return True
        return False


class FakeUserGateway(IUserGateway):
    """Швидкий тестовий дублер IUserGateway для юніт-тестів."""

    def __init__(self) -> None:
        self.users: dict[UUID, UserResponseDTO] = {}

    def add_user(
        self,
        user_id: UUID,
        *,
        is_active: bool = True,
        username: str = "test_user",
        name: str = "Test User",
        role_id: UUID | None = None,
    ) -> UserResponseDTO:
        dto = UserResponseDTO(
            id=user_id,
            version=1,
            username=username,
            name=name,
            role_id=role_id or user_id,
            created_at=datetime.now(UTC),
            deleted_at=None if is_active else datetime.now(UTC),
        )
        self.users[user_id] = dto
        return dto

    async def get_user_by_id(self, user_id: UUID, /) -> UserResponseDTO | None:
        return self.users.get(user_id)
