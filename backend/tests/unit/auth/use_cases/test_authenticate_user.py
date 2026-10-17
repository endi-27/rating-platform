import pytest
from uuid6 import uuid7

from src.core import (
    AccountDeactivatedException,
    InvalidCredentialsException,
    SystemRole,
    get_current_user_id,
    get_current_username,
)
from src.modules.auth.application.dto import LoginDTO
from src.modules.auth.application.use_cases import AuthenticateUserUseCase
from src.modules.auth.domain import (
    LoginFailedEvent,
    LoginFailureReason,
    UserLoggedInEvent,
)
from src.modules.users.domain import Role, User
from tests.unit.fake_repositories import (
    FakeRefreshTokenRepository,
    FakeUserAuthGateway,
    FakeUserRepository,
)
from tests.unit.fakes import FakeEventBus, FakePasswordHasher, FakeUnitOfWork


def _create_test_user(
    username: str = "john.doe",
    password_hash: str = "hashed_CorrectPassword123!",
    is_active: bool = True,
) -> User:
    role = Role(
        id=uuid7(),
        code=SystemRole.USER.value,
        name="Користувач",
        permissions=set(),
    )
    user = User(
        id=uuid7(),
        username=username,
        name="John Doe",
        password_hash=password_hash,
        role_id=role.id,
        role=role,
    )
    if not is_active:
        user.soft_delete()
    return user


async def test_authenticate_user_success() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _create_test_user()
    await user_repo.save(user)

    use_case = AuthenticateUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = LoginDTO(
        username="john.doe",
        password="CorrectPassword123!",
        is_remember_me=False,
    )

    result = await use_case.execute(dto, ip_address="127.0.0.1")

    # Assert DTO result
    assert result.user_id == user.id
    assert result.is_remember_me is False
    assert result.access_token is not None
    assert result.refresh_token is not None

    # Assert UoW committed
    assert uow.committed is True
    assert uow.rolled_back is False

    # Assert refresh token stored in repository
    assert len(refresh_repo.tokens) == 1
    token_entity = next(iter(refresh_repo.tokens.values()))
    assert token_entity.user_id == user.id
    assert token_entity.is_remember_me is False
    assert token_entity.is_revoked is False

    # Assert contextvars set
    assert get_current_user_id() == user.id
    assert get_current_username() == user.username

    # Assert UserLoggedInEvent published
    logged_in_events = event_bus.get_events_of_type(UserLoggedInEvent)
    assert len(logged_in_events) == 1
    event = logged_in_events[0]
    assert event.entity_id == user.id
    assert event.actor_id == user.id
    assert event.username == user.username
    assert event.ip_address == "127.0.0.1"


async def test_authenticate_user_remember_me() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _create_test_user()
    await user_repo.save(user)

    use_case = AuthenticateUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = LoginDTO(
        username="john.doe",
        password="CorrectPassword123!",
        is_remember_me=True,
    )

    result = await use_case.execute(dto)

    assert result.is_remember_me is True
    token_entity = next(iter(refresh_repo.tokens.values()))
    assert token_entity.is_remember_me is True


async def test_authenticate_user_not_found() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    use_case = AuthenticateUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = LoginDTO(
        username="nonexistent.user",
        password="SomePassword123!",
    )

    with pytest.raises(InvalidCredentialsException, match="Неправильний логін або пароль"):
        await use_case.execute(dto, ip_address="192.168.1.1")

    assert uow.committed is False
    assert uow.rolled_back is True
    assert len(refresh_repo.tokens) == 0

    failed_events = event_bus.get_events_of_type(LoginFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].username == "nonexistent.user"
    assert failed_events[0].reason == LoginFailureReason.INVALID_CREDENTIALS
    assert failed_events[0].ip_address == "192.168.1.1"


async def test_authenticate_user_wrong_password() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _create_test_user()
    await user_repo.save(user)

    use_case = AuthenticateUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = LoginDTO(
        username="john.doe",
        password="WrongPassword999!",
    )

    with pytest.raises(InvalidCredentialsException, match="Неправильний логін або пароль"):
        await use_case.execute(dto)

    assert uow.committed is False
    assert uow.rolled_back is True
    assert len(refresh_repo.tokens) == 0

    failed_events = event_bus.get_events_of_type(LoginFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].reason == LoginFailureReason.INVALID_CREDENTIALS


async def test_authenticate_user_account_deactivated() -> None:
    uow = FakeUnitOfWork()
    user_repo = FakeUserRepository()
    user_gateway = FakeUserAuthGateway(user_repo)
    refresh_repo = FakeRefreshTokenRepository()
    event_bus = FakeEventBus()
    hasher = FakePasswordHasher()

    user = _create_test_user(is_active=False)
    await user_repo.save(user)

    use_case = AuthenticateUserUseCase(
        uow=uow,
        users_gateway=user_gateway,
        refresh_repo=refresh_repo,
        event_bus=event_bus,
        password_hasher=hasher,
    )

    dto = LoginDTO(
        username="john.doe",
        password="CorrectPassword123!",
    )

    with pytest.raises(AccountDeactivatedException, match="Обліковий запис користувача деактивовано"):
        await use_case.execute(dto, ip_address="10.0.0.5")

    assert uow.committed is False
    assert uow.rolled_back is True
    assert len(refresh_repo.tokens) == 0

    failed_events = event_bus.get_events_of_type(LoginFailedEvent)
    assert len(failed_events) == 1
    assert failed_events[0].entity_id == user.id
    assert failed_events[0].reason == LoginFailureReason.ACCOUNT_DEACTIVATED
    assert failed_events[0].ip_address == "10.0.0.5"
