import pytest

from src.core import UserAlreadyExistsException
from src.modules.auth.application.dto import RegisterDTO
from src.modules.auth.application.use_cases import RegisterPublicUserUseCase
from src.modules.auth.domain import UserLoggedInEvent
from tests.unit.fake_repositories import (
    FakeRefreshTokenRepository,
    FakeUserAuthGateway,
    FakeUserRepository,
)
from tests.unit.fakes import FakeEventBus, FakeUnitOfWork


async def test_register_public_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = RegisterPublicUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RegisterDTO(
        username="newuser",
        name="New User",
        password="SecurePassword123!",
        is_remember_me=False,
    )

    result = await use_case.execute(
        dto=dto,
        ip_address="127.0.0.1",
    )

    assert result.user_id is not None
    user = await user_repo.get_by_id(result.user_id)
    assert user is not None
    assert user.username == "newuser"
    assert user.name == "New User"
    assert result.access_token != ""
    assert result.refresh_token != ""
    assert uow.committed is True

    # Check refresh token saved
    tokens = [t for t in refresh_repo.tokens.values() if t.user_id == result.user_id]
    assert len(tokens) == 1

    # Check UserLoggedInEvent emitted
    events = event_bus.get_events_of_type(UserLoggedInEvent)
    assert len(events) == 1
    assert events[0].username == "newuser"


async def test_register_public_user_duplicate_username() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = RegisterPublicUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RegisterDTO(
        username="duplicate_user",
        name="Duplicate User",
        password="SecurePassword123!",
        is_remember_me=False,
    )

    # First registration
    await use_case.execute(dto=dto, ip_address="127.0.0.1")

    # Second registration with same username -> UserAlreadyExistsException
    with pytest.raises(UserAlreadyExistsException):
        await use_case.execute(dto=dto, ip_address="127.0.0.1")


async def test_register_public_user_remember_me() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()

    use_case = RegisterPublicUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
    )

    dto = RegisterDTO(
        username="remember_user",
        name="Remember User",
        password="SecurePassword123!",
        is_remember_me=True,
    )

    result = await use_case.execute(dto=dto)
    assert result.is_remember_me is True
    tokens = [t for t in refresh_repo.tokens.values() if t.user_id == result.user_id]
    assert len(tokens) == 1
    assert tokens[0].is_remember_me is True
