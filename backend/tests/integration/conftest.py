from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db import SqlAlchemyUnitOfWork


@pytest.fixture
async def integration_uow(db_session: AsyncSession) -> AsyncGenerator[SqlAlchemyUnitOfWork, None]:
    """
    Справжній SqlAlchemyUnitOfWork для інтеграційного тестування транзакцій та репозиторіїв.
    Працює через транзакційну сесію з savepoint та безпечно відкочує всі зміни.
    """
    uow = SqlAlchemyUnitOfWork(session=db_session)
    yield uow
