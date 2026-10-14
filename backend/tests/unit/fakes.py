from types import TracebackType
from typing import Any
from uuid import UUID

from src.core import (
    IEventBus,
    IPasswordHasher,
    IUnitOfWork,
)
from src.modules.users.domain import IAuthSessionGateway


class FakeUnitOfWork(IUnitOfWork):
    """Швидкий тестовий дублер Unit of Work для юніт-тестів без БД (< 0.05 сек)."""

    def __init__(self) -> None:
        self.committed: bool = False
        self.commit_count: int = 0
        self.rolled_back: bool = False
        self.in_context: bool = False
        self.fail_on_commit: bool = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        self.in_context = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.in_context = False
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError("Database commit error simulated")
        self.committed = True
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeEventBus(IEventBus):
    """Тестовий дублер шини подій з фіксацією опублікованих подій."""

    def __init__(self) -> None:
        self.published_events: list[Any] = []

    async def publish(self, *events: Any) -> None:
        self.published_events.extend(events)

    def has_event_of_type(self, event_type: type) -> bool:
        return any(isinstance(e, event_type) for e in self.published_events)

    def get_events_of_type(self, event_type: type) -> list[Any]:
        return [e for e in self.published_events if isinstance(e, event_type)]


class FakeAuthSessionGateway(IAuthSessionGateway):
    """Тестовий дублер шлюзу сесій модуля auth."""

    def __init__(self) -> None:
        self.revoked_user_ids: list[UUID] = []
        self.revocation_calls: list[dict[str, Any]] = []

    async def revoke_all_user_sessions(
        self,
        user_id: UUID,
        *,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        external_uow: IUnitOfWork | None = None,
    ) -> None:
        self.revoked_user_ids.append(user_id)
        self.revocation_calls.append(
            {
                "user_id": user_id,
                "actor_id": actor_id,
                "actor_username": actor_username,
                "external_uow": external_uow,
            }
        )


class FakePasswordHasher(IPasswordHasher):
    """Швидкий тестовий дублер сервісу хешування паролів (< 0.001 сек)."""

    def hash(self, password: str, rounds: int | None = None) -> str:
        return f"hashed_{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        if hashed_password.startswith("hashed_"):
            return hashed_password == f"hashed_{plain_password}"
        return plain_password == hashed_password


__all__ = [
    "FakeAuthSessionGateway",
    "FakeEventBus",
    "FakePasswordHasher",
    "FakeUnitOfWork",
]
