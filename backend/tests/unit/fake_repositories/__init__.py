from tests.unit.fake_repositories.fake_permission_repository import FakePermissionRepository
from tests.unit.fake_repositories.fake_refresh_token_repository import FakeRefreshTokenRepository
from tests.unit.fake_repositories.fake_reviews_repositories import (
    FakeReviewRepository,
    FakeReviewVoteRepository,
    FakeTargetRatingRepository,
    FakeTargetRepository,
)
from tests.unit.fake_repositories.fake_role_repository import FakeRoleRepository
from tests.unit.fake_repositories.fake_user_auth_gateway import FakeUserAuthGateway
from tests.unit.fake_repositories.fake_user_repository import FakeUserRepository

__all__ = [
    "FakePermissionRepository",
    "FakeRefreshTokenRepository",
    "FakeReviewRepository",
    "FakeReviewVoteRepository",
    "FakeRoleRepository",
    "FakeTargetRatingRepository",
    "FakeTargetRepository",
    "FakeUserAuthGateway",
    "FakeUserRepository",
]
