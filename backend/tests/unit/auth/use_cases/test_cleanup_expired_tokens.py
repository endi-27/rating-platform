from datetime import UTC, datetime, timedelta

import pytest
from uuid6 import uuid7

from src.modules.auth.application.use_cases import CleanupExpiredTokensUseCase
from src.modules.auth.domain import RefreshToken
from tests.unit.fake_repositories import FakeRefreshTokenRepository
from tests.unit.fakes import FakeUnitOfWork


async def test_cleanup_expired_tokens_success_multiple_batches() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()

    now = datetime.now(UTC)
    cutoff = now

    # Create 5 expired tokens
    for i in range(5):
        token = RefreshToken.create(
            user_id=uuid7(),
            token_hash=f"expired_token_hash_{i}_long_enough",
            expires_at=now - timedelta(days=2),
            max_session_expiration=now + timedelta(days=10),
            issued_at=now - timedelta(days=10),
        )
        await refresh_repo.create(token)

    # Create 2 valid active tokens
    for i in range(2):
        token = RefreshToken.create(
            user_id=uuid7(),
            token_hash=f"active_token_hash_{i}_long_enough",
            expires_at=now + timedelta(days=5),
            max_session_expiration=now + timedelta(days=30),
            issued_at=now,
        )
        await refresh_repo.create(token)

    use_case = CleanupExpiredTokensUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
    )

    # batch_size = 2 -> will delete in batches: 2, 2, 1 (total 3 batches, 5 deleted)
    total_deleted = await use_case.execute(cutoff=cutoff, batch_size=2)

    assert total_deleted == 5
    assert len(refresh_repo.tokens) == 2
    assert uow.commit_count == 3
    assert uow.committed is True
    assert uow.rolled_back is False


async def test_cleanup_expired_tokens_zero_tokens() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()

    use_case = CleanupExpiredTokensUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
    )

    total_deleted = await use_case.execute()

    assert total_deleted == 0
    assert uow.commit_count == 0


async def test_cleanup_expired_tokens_naive_cutoff_handled() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()

    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="expired_token_hash_with_32_chars",
        expires_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        max_session_expiration=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
        issued_at=datetime(2024, 12, 1, 10, 0, tzinfo=UTC),
    )
    await refresh_repo.create(token)

    use_case = CleanupExpiredTokensUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
    )

    # Naive cutoff should be converted to UTC internally
    naive_cutoff = datetime(2025, 1, 2, 0, 0)
    total_deleted = await use_case.execute(cutoff=naive_cutoff, batch_size=10)

    assert total_deleted == 1
    assert len(refresh_repo.tokens) == 0


async def test_cleanup_expired_tokens_error_handling() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()
    refresh_repo.fail_on_delete = True

    use_case = CleanupExpiredTokensUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
    )

    with pytest.raises(RuntimeError, match="Помилка видалення застарілих токенів"):
        await use_case.execute()

    assert uow.rolled_back is True
