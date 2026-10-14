from types import TracebackType
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core import IUnitOfWork, db_router


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """
    Реалізація Unit of Work для SQLAlchemy 2.0 async з підтримкою маршрутизації сесій.

    Підтримує сценарії:
    1. Request-scoped сесія (FastAPI DI): приймає вже відкриту сесію `session`.
       У цьому випадку UoW керує комітом/відкатом транзакцій цієї сесії,
       а закриття сесії делегується життєвому циклу HTTP-запиту (FastAPI).
    2. Self-contained сесія (Worker/Script/Router): створює нову сесію у `__aenter__`
       через `session_factory` або через `db_router.get_session(...)` із врахуванням
       параметрів operation, shard_key, force_primary та гарантовано закриває її в `__aexit__`.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        operation: Literal["read", "write"] = "write",
        shard_key: Any | None = None,
        force_primary: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = session
        self._is_external_session: bool = session is not None
        self._operation = operation
        self._shard_key = shard_key
        self._force_primary = force_primary
        self._in_context: bool = False

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._in_context = True
        if self.session is None:
            if self._session_factory is not None:
                self.session = self._session_factory()
            else:
                self.session = db_router.get_session(
                    operation=self._operation,
                    shard_key=self._shard_key,
                    force_primary=self._force_primary,
                )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._in_context = False
        if exc_type is not None:
            await self.rollback()
        if not self._is_external_session and self.session is not None:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        if self.session is not None:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()

    @property
    def current_session(self) -> AsyncSession:
        """Повертає поточну активну сесію, викидає RuntimeError якщо сесія поза контекстом."""
        if not self._in_context or self.session is None:
            raise RuntimeError("UnitOfWork поза контекстом 'async with uow:'")
        return self.session
