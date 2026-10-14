from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Annotated, Any, Literal

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import IUnitOfWork, db_router, get_db_session
from src.infrastructure.db import SqlAlchemyUnitOfWork


async def get_uow(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncGenerator[IUnitOfWork, None]:
    """
    Фабрика Unit of Work для ін'єкції в Use Cases через Depends.
    Отримує спільну сесію запиту (Request Scope), гарантуючи, що UoW та репозиторії
    працюють в одній транзакції.
    """
    uow = SqlAlchemyUnitOfWork(session=session)
    yield uow


async def get_read_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронний генератор сесій спеціально для операцій читання (Read Replica у ЛР 6)."""
    async with db_router.get_session(operation="read", force_primary=False) as session:
        yield session


def provide_uow(
    operation: Literal["read", "write"] = "write",
    shard_key: Any | None = None,
    force_primary: bool = False,
) -> Callable[[], AsyncGenerator[IUnitOfWork, None]]:
    """Генератор залежності UnitOfWork із заданим профілем маршрутизації."""

    async def _dependency() -> AsyncGenerator[IUnitOfWork, None]:
        uow = SqlAlchemyUnitOfWork(
            operation=operation,
            shard_key=shard_key,
            force_primary=force_primary,
        )
        yield uow

    return _dependency
