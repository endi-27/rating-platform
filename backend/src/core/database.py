from collections.abc import AsyncGenerator
from typing import Any, Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings


class DatabaseRouter:
    """
    Маршрутизатор підключень до СУБД із підтримкою:
    - Master/Primary для мутацій (operation='write')
    - Read Replica для масштабування читання (operation='read') (ЛР 6)
    - Sharding за ключем shard_key (ЛР 7)
    - Примусової консистентності читання після запису (force_primary=True) (ЛР 6)
    """

    def __init__(self, primary_engine: AsyncEngine) -> None:
        self._primary_engine = primary_engine
        self._primary_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=primary_engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        # Резерв під майбутні репліки (ЛР 6) та шарди (ЛР 7)
        self._replica_session_factory: async_sessionmaker[AsyncSession] | None = None
        self._shard_factories: dict[str, async_sessionmaker[AsyncSession]] = {}

    @property
    def primary_engine(self) -> AsyncEngine:
        return self._primary_engine

    @property
    def primary_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._primary_session_factory

    def register_replica(self, replica_engine: AsyncEngine) -> None:
        """Реєстрація вузла Read Replica (ЛР 6)."""
        self._replica_session_factory = async_sessionmaker(
            bind=replica_engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    def register_shard(self, shard_name: str, shard_engine: AsyncEngine) -> None:
        """Реєстрація вузла шарду (ЛР 7)."""
        self._shard_factories[shard_name] = async_sessionmaker(
            bind=shard_engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    def get_session_factory(
        self,
        operation: Literal["read", "write"] = "write",
        shard_key: Any | None = None,
        force_primary: bool = False,
    ) -> async_sessionmaker[AsyncSession]:
        """Визначає цільовий пул з'єднань згідно з профілем операції та ключем шардингу."""
        # 1. Читання з репліки (якщо зареєстрована та не вимагається strong consistency)
        if operation == "read" and not force_primary and self._replica_session_factory is not None:
            return self._replica_session_factory

        # 2. Шардинг за ключем (ЛР 7)
        if shard_key is not None and self._shard_factories:
            shard_name = f"shard_{(hash(str(shard_key)) % len(self._shard_factories))}"
            if shard_name in self._shard_factories:
                return self._shard_factories[shard_name]

        # 3. Дефолт на Primary вузол
        return self._primary_session_factory

    def get_session(
        self,
        operation: Literal["read", "write"] = "write",
        shard_key: Any | None = None,
        force_primary: bool = False,
    ) -> AsyncSession:
        factory = self.get_session_factory(
            operation=operation,
            shard_key=shard_key,
            force_primary=force_primary,
        )
        return factory()


engine: AsyncEngine = create_async_engine(
    settings.db.url,
    echo=settings.db.echo,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    pool_timeout=settings.db.pool_timeout,
    pool_pre_ping=True,
    connect_args={"server_settings": {"timezone": "utc"}},
)

db_router = DatabaseRouter(primary_engine=engine)
async_session_factory = db_router.primary_session_factory


async def get_db_session(
    operation: Literal["read", "write"] = "write",
    shard_key: Any | None = None,
    force_primary: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Асинхронний генератор сесій для ін'єкції залежностей з підтримкою маршрутизації."""
    async with db_router.get_session(operation=operation, shard_key=shard_key, force_primary=force_primary) as session:
        yield session


async def close_db() -> None:
    """Закриття рушія та пулу з'єднань БД при зупинці додатку."""
    await engine.dispose()
