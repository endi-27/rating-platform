import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

# За замовчуванням спрямовуємо тести в тестове середовище та виділену тестову БД,
# якщо інше не задано у .env.test чи змінних оточення
os.environ.setdefault("APP_CONFIG__ENVIRONMENT", "test")
os.environ.setdefault("APP_CONFIG__DB__NAME", "rating_test_db")

# Якщо для тестового оточення не вказано специфічне число раундів або воно 12 (з .env),
# виставляємо швидкі 4 раунди за замовчуванням для тестів:
if os.environ.get("APP_CONFIG__AUTH__BCRYPT_ROUNDS") in (None, "12"):
    os.environ["APP_CONFIG__AUTH__BCRYPT_ROUNDS"] = "4"


import pytest
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.api.events_setup import setup_application_events
from src.core import Settings, get_settings
from src.core.events import get_event_bus
from src.infrastructure.cache import default_key_builder
from src.main import app

# Очищуємо кеш налаштувань, щоб гарантувати підтягування тестових налаштувань
get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """
    Гарантує існування тестової бази даних
    та автоматично застосовує всі Alembic міграції перед початком тестів.
    """
    current_settings = get_settings()
    if "test" not in current_settings.db.name.lower() or current_settings.db.name == "rating_db":
        msg = (
            f"Критична помилка безпеки: тести намагаються використати базу даних "
            f"'{current_settings.db.name}'. Назва тестової БД повинна містити 'test' "
            f"та не збігатися з основною базою 'rating_db'!"
        )
        raise RuntimeError(msg)

    # 1. Підключаємося до системної БД postgres для перевірки/створення тестової БД
    maintenance_url = (
        f"postgresql+asyncpg://{current_settings.db.user}:{current_settings.db.password}@"
        f"{current_settings.db.host}:{current_settings.db.port}/postgres"
    )
    admin_engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": current_settings.db.name},
        )
        if not exists:
            try:
                await conn.execute(
                    text(f'CREATE DATABASE "{current_settings.db.name}" OWNER "{current_settings.db.user}"')
                )
            except Exception as exc:
                # Обробка паралельного створення бази воркерами pytest-xdist
                if "already exists" not in str(exc).lower() and "duplicate_database" not in str(exc).lower():
                    raise
    await admin_engine.dispose()

    # 2. Програмно застосовуємо міграції Alembic
    def _run_migrations() -> None:
        from alembic.config import Config

        from alembic import command

        backend_dir = Path(__file__).resolve().parent.parent
        ini_path = backend_dir / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", current_settings.db.url)
        command.upgrade(alembic_cfg, "head")

    await asyncio.to_thread(_run_migrations)

    # 3. Сідуємо початкового superadmin у тестову БД
    from scripts.seed_superadmin import main as seed_superadmin_main

    await seed_superadmin_main()

    yield


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Спільний асинхронний рушій SQLAlchemy для тестів.
    Підключається до тестової бази з NullPool.
    """
    engine = create_async_engine(
        get_settings().db.url,
        poolclass=NullPool,
        connect_args={"server_settings": {"timezone": "utc"}},
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Ізольована сесія бази даних для тесту.
    Працює в режимі join_transaction_mode="create_savepoint"
    і автоматично відкочує всі зміни після завершення тесту.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        )
        async with session_factory() as session:
            yield session
        await transaction.rollback()


@pytest.fixture(autouse=True)
def init_test_cache() -> None:
    """Ініціалізація швидкого InMemoryBackend для FastAPICache для ізоляції кешу між тестами."""
    InMemoryBackend._store.clear()
    FastAPICache.reset()
    FastAPICache.init(
        InMemoryBackend(),
        prefix="test-cache",
        key_builder=default_key_builder,
    )


@pytest.fixture(autouse=True)
def init_test_event_bus() -> None:
    """Ізоляція шини подій застосунку: очищення підписок та підключення актуальних слухачів."""
    bus = get_event_bus()
    bus.clear()
    setup_application_events(bus)


@pytest.fixture(autouse=True)
def mock_task_dispatcher() -> Generator[AsyncMock, None, None]:
    """
    Автоматичний мок для диспетчера задач ARQ.
    Запобігає спаму задач у чергу Redis під час тестів.
    """
    with patch(
        "src.tasks.dispatcher.TaskDispatcher.enqueue_cleanup_temp_files",
        new_callable=AsyncMock,
        return_value="mocked-job-id",
    ) as mock_enqueue:
        yield mock_enqueue


@pytest.fixture
def test_settings() -> Settings:
    """Повертає тестові налаштування додатку."""
    return get_settings()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Асинхронний HTTP-клієнт для швидкого тестування ендпоінтів FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
