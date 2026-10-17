import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from uuid6 import uuid7

from src.core import (
    AccountDeactivatedException,
    InvalidTokenException,
    SystemRole,
    get_current_user_id,
    get_current_username,
)
from src.modules.auth.application.dto import RefreshTokenDTO
from src.modules.auth.application.use_cases import RefreshTokenUseCase
from src.modules.auth.domain import (
    RefreshToken,
    SessionExpiredEvent,
    TokenCompromisedEvent,
    TokenRefreshFailedEvent,
    TokenRefreshFailureReason,
)
from src.modules.users.domain import Role, User
from tests.unit.fake_repositories import (
    FakeRefreshTokenRepository,
    FakeUserAuthGateway,
    FakeUserRepository,
)
from tests.unit.fakes import FakeEventBus, FakeUnitOfWork


def _create_user_and_role() -> User:
    role = Role(
        id=uuid7(),
        code=SystemRole.USER.value,
        name="Користувач",
        permissions=set(),
    )
    return User(
        id=uuid7(),
        username="alice",
        name="Alice Wonderland",
        password_hash="hashed_pw",
        role_id=role.id,
        role=role,
    )


async def test_refresh_token_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user = _create_user_and_role()
    await user_repo.save(user)

    now = datetime.now(UTC)
    raw_token = "valid_raw_refresh_token_string_123456789"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    existing_token = RefreshToken.create(
        user_id=user.id,
        token_hash=raw_hash,
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
        is_remember_me=True,
        issued_at=now - timedelta(days=1),
    )
    await refresh_repo.create(existing_token)

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)
    result = await use_case.execute(dto, ip_address="192.168.0.1")

    # Result checks
    assert result.user_id == user.id
    assert result.is_remember_me is True
    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.refresh_token != raw_token

    # UoW committed
    assert uow.committed is True

    # Check old token revoked and updated
    old_token = await refresh_repo.get_by_token_hash(raw_hash)
    assert old_token is not None
    assert old_token.is_revoked is True

    # Check new token stored
    assert len(refresh_repo.tokens) == 2

    # Check contextvars set
    assert get_current_user_id() == user.id
    assert get_current_username() == user.username


async def test_refresh_token_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token="unknown_refresh_token_string_with_32_chars")

    with pytest.raises(InvalidTokenException, match="Refresh токен недійсний"):
        await use_case.execute(dto, ip_address="10.10.10.1")

    assert uow.committed is False
    assert uow.rolled_back is True

    failed_events = event_bus.get_events_of_type(TokenRefreshFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].reason == TokenRefreshFailureReason.TOKEN_NOT_FOUND
    assert failed_events[0].ip_address == "10.10.10.1"


async def test_refresh_token_reuse_detection() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user = _create_user_and_role()
    await user_repo.save(user)

    now = datetime.now(UTC)
    raw_token = "revoked_raw_token_that_is_at_least_32_chars"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # Pre-revoked token (attempted reuse)
    revoked_token = RefreshToken.create(
        user_id=user.id,
        token_hash=raw_hash,
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
    )
    revoked_token.revoke()
    await refresh_repo.create(revoked_token)

    # Another active token of same user
    other_token = RefreshToken.create(
        user_id=user.id,
        token_hash="other_active_token_hash_longer_than_needed",
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
    )
    await refresh_repo.create(other_token)
    assert other_token.is_revoked is False

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)

    with pytest.raises(InvalidTokenException, match="спробу повторного використання токена"):
        await use_case.execute(dto, ip_address="1.2.3.4")

    # Bulk revoke must have revoked ALL sessions
    assert other_token.is_revoked is True
    assert uow.committed is True

    compromised_events = event_bus.get_events_of_type(TokenCompromisedEvent)
    assert len(compromised_events) == 1
    assert compromised_events[0].entity_id == user.id
    assert compromised_events[0].username == user.username
    assert compromised_events[0].ip_address == "1.2.3.4"


async def test_refresh_token_expired() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user = _create_user_and_role()
    await user_repo.save(user)

    now = datetime.now(UTC)
    raw_token = "expired_raw_token_with_at_least_32_characters"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    expired_token = RefreshToken.create(
        user_id=user.id,
        token_hash=raw_hash,
        expires_at=now - timedelta(minutes=5),
        max_session_expiration=now + timedelta(days=30),
        issued_at=now - timedelta(days=8),
    )
    await refresh_repo.create(expired_token)

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)

    with pytest.raises(InvalidTokenException, match="Термін дії сесії вичерпано або токен недійсний"):
        await use_case.execute(dto)

    assert expired_token.is_revoked is True
    assert uow.committed is True

    expired_events = event_bus.get_events_of_type(SessionExpiredEvent)
    assert len(expired_events) == 1
    assert expired_events[0].entity_id == user.id


async def test_refresh_token_session_expired() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user = _create_user_and_role()
    await user_repo.save(user)

    now = datetime.now(UTC)
    raw_token = "session_expired_raw_token_with_32_characters"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    token = RefreshToken.create(
        user_id=user.id,
        token_hash=raw_hash,
        expires_at=now + timedelta(days=1),
        max_session_expiration=now - timedelta(seconds=1),
        issued_at=now - timedelta(days=31),
    )
    await refresh_repo.create(token)

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)

    with pytest.raises(InvalidTokenException, match="Термін дії сесії вичерпано або токен недійсний"):
        await use_case.execute(dto)

    assert token.is_revoked is True
    assert uow.committed is True

    expired_events = event_bus.get_events_of_type(SessionExpiredEvent)
    assert len(expired_events) == 1


async def test_refresh_token_deactivated_user() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user = _create_user_and_role()
    user.soft_delete()
    await user_repo.save(user)

    now = datetime.now(UTC)
    raw_token = "valid_token_deactivated_user_with_32_chars"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    token = RefreshToken.create(
        user_id=user.id,
        token_hash=raw_hash,
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
        issued_at=now,
    )
    await refresh_repo.create(token)

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)

    with pytest.raises(AccountDeactivatedException, match="Обліковий запис користувача деактивовано"):
        await use_case.execute(dto, ip_address="127.0.0.1")

    assert uow.committed is False
    assert uow.rolled_back is True

    failed_events = event_bus.get_events_of_type(TokenRefreshFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].entity_id == user.id
    assert failed_events[0].reason == TokenRefreshFailureReason.ACCOUNT_DEACTIVATED


async def test_refresh_token_user_not_found_in_gateway() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    non_existent_user_id = uuid7()
    now = datetime.now(UTC)
    raw_token = "valid_token_missing_user_with_32_chars"
    raw_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    token = RefreshToken.create(
        user_id=non_existent_user_id,
        token_hash=raw_hash,
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
        issued_at=now,
    )
    await refresh_repo.create(token)

    use_case = RefreshTokenUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RefreshTokenDTO(refresh_token=raw_token)

    with pytest.raises(AccountDeactivatedException, match="Обліковий запис користувача деактивовано"):
        await use_case.execute(dto, ip_address="127.0.0.1")

    assert uow.committed is False
    assert uow.rolled_back is True

    failed_events = event_bus.get_events_of_type(TokenRefreshFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].entity_id == non_existent_user_id
    assert failed_events[0].reason == TokenRefreshFailureReason.ACCOUNT_DEACTIVATED
