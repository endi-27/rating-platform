import hashlib
from datetime import UTC, datetime, timedelta

from uuid6 import uuid7

from src.core import get_current_user_id, get_current_username
from src.modules.auth.application.dto import LogoutDTO
from src.modules.auth.application.use_cases import LogoutUseCase
from src.modules.auth.domain import RefreshToken, UserLoggedOutEvent
from tests.unit.fake_repositories import FakeRefreshTokenRepository
from tests.unit.fakes import FakeEventBus, FakeUnitOfWork


async def test_logout_with_valid_refresh_token() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    user_id = uuid7()
    now = datetime.now(UTC)
    raw_token = "valid_refresh_token_to_logout_with_32_chars"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    token = RefreshToken.create(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
    )
    await refresh_repo.create(token)

    use_case = LogoutUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = LogoutDTO(refresh_token=raw_token)
    await use_case.execute(
        dto,
        ip_address="127.0.0.1",
        user_id=user_id,
        username="john.doe",
    )

    assert token.is_revoked is True
    assert uow.committed is True

    # Assert context set
    assert get_current_user_id() == user_id
    assert get_current_username() == "john.doe"

    # Assert UserLoggedOutEvent published
    logged_out_events = event_bus.get_events_of_type(UserLoggedOutEvent)
    assert len(logged_out_events) == 1
    event = logged_out_events[0]
    assert event.entity_id == user_id
    assert event.session_id == token.id
    assert event.username == "john.doe"
    assert event.ip_address == "127.0.0.1"


async def test_logout_idempotent_with_nonexistent_token() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = LogoutUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    actor_id = uuid7()
    dto = LogoutDTO(refresh_token="nonexistent_token_string_with_32_chars")
    await use_case.execute(
        dto,
        ip_address="192.168.1.100",
        user_id=actor_id,
        username="alice",
    )

    # Repository was not modified, but no error raised
    assert uow.committed is False

    # Event still published with session_id=None
    logged_out_events = event_bus.get_events_of_type(UserLoggedOutEvent)
    assert len(logged_out_events) == 1
    assert logged_out_events[0].entity_id == actor_id
    assert logged_out_events[0].session_id is None
    assert logged_out_events[0].username == "alice"


async def test_logout_without_refresh_token() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = LogoutUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    actor_id = uuid7()
    dto = LogoutDTO(refresh_token=None)
    await use_case.execute(
        dto,
        user_id=actor_id,
        username="bob",
    )

    assert uow.committed is False
    logged_out_events = event_bus.get_events_of_type(UserLoggedOutEvent)
    assert len(logged_out_events) == 1
    assert logged_out_events[0].entity_id == actor_id
    assert logged_out_events[0].session_id is None


async def test_logout_without_token_and_without_user_id() -> None:
    uow = FakeUnitOfWork()
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = LogoutUseCase(
        uow=uow,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = LogoutDTO(refresh_token=None)
    await use_case.execute(dto, user_id=None)

    assert len(event_bus.published_events) == 0
    assert uow.committed is False
