from __future__ import annotations

from typing import Any, Protocol


class IUnitOfWork(Protocol):
    """Абстрактний протокол легковажного Unit of Work для керування транзакціями."""

    async def __aenter__(self) -> IUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class IEventBus(Protocol):
    """Абстрактний протокол внутрішньопроцесної шини подій."""

    async def publish(self, *events: Any) -> None: ...


class IPasswordHasher(Protocol):
    """Абстрактний протокол сервісу хешування та верифікації паролів (Driven Port)."""

    def hash(self, password: str, rounds: int | None = None) -> str:
        """Створення криптографічного хешу пароля."""
        ...

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Перевірка відповідності відкритого пароля збереженому хешу."""
        ...
