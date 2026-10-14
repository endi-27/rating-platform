from typing import Any

import aiofiles.os
from arq.connections import RedisSettings as ArqRedisSettings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Реєстрація всіх ORM-моделей у Base.metadata для коректної роботи ForeignKey зв'язків у фоновому воркері
import src.modules.auth.infrastructure.models  # noqa: F401
import src.modules.users.infrastructure.models  # noqa: F401
from src.core import logger, set_current_username, settings, setup_worker_logging
from src.tasks.cron import cron_jobs
from src.tasks.functions import (
    cleanup_expired_refresh_tokens_task,
    cleanup_expired_temp_files_task,
)


async def startup(ctx: dict[str, Any]) -> None:
    """Хук запуску ARQ воркера: налаштування логів, папок, рушія БД та клієнтів."""
    setup_worker_logging()
    set_current_username("system:worker")

    # Асинхронне створення необхідних директорій сховища та журналів
    await aiofiles.os.makedirs(settings.storage.dir, exist_ok=True)
    await aiofiles.os.makedirs(settings.storage.uploads_dir, exist_ok=True)
    await aiofiles.os.makedirs(settings.storage.temp_dir, exist_ok=True)
    await aiofiles.os.makedirs(settings.log.dir, exist_ok=True)

    # Виділений асинхронний пул підключень до БД спеціально для процесу воркера
    engine: AsyncEngine = create_async_engine(
        settings.db.url,
        echo=settings.db.echo,
        pool_size=settings.arq.max_jobs,
        max_overflow=5,
        pool_timeout=settings.db.pool_timeout,
        pool_pre_ping=True,
        connect_args={"server_settings": {"timezone": "utc"}},
    )
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    ctx["engine"] = engine
    ctx["session_factory"] = session_factory

    logger.info(
        "[ARQ Worker] Воркер успішно запущено. Черга: {queue} | Конкурентність: {max_jobs} задач",
        queue=settings.arq.queue_name,
        max_jobs=settings.arq.max_jobs,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Хук безпечної зупинки ARQ воркера: коректне закриття пулу з'єднань БД."""
    engine: AsyncEngine | None = ctx.get("engine")
    if engine is not None:
        await engine.dispose()

    logger.info("[ARQ Worker] Воркер успішно зупинено. Пул з'єднань БД вивільнено.")


async def on_job_start(ctx: dict[str, Any]) -> None:
    """Хук перед виконанням кожної задачі ARQ: встановлення ідентифікатора актора."""
    job_name = ctx.get("job_name")
    if job_name:
        set_current_username(f"system:{job_name}")
    else:
        set_current_username("system:worker")


class WorkerSettings:
    """Еталонна конфігурація ARQ воркера."""

    # Список звичайних фонових функцій
    functions = [
        cleanup_expired_temp_files_task,
        cleanup_expired_refresh_tokens_task,
    ]

    # Список періодичних cron-задач
    cron_jobs = cron_jobs

    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start

    # Максимальна кількість повторних спроб виконання задачі при виклику Retry
    max_tries = settings.arq.max_tries

    # Конкурентність: максимальна кількість одночасних асинхронних задач
    max_jobs = settings.arq.max_jobs

    # Жорсткий таймаут виконання задачі у секундах
    job_timeout = settings.arq.job_timeout

    # Час збереження результатів таски у Redis
    keep_result = settings.arq.keep_result

    # Інтервал оновлення кеш-ключа healthcheck у Redis
    health_check_interval = settings.arq.health_check_interval

    # Назва черги в Redis
    queue_name = settings.arq.queue_name

    # Налаштування підключення до Redis
    redis_settings = ArqRedisSettings(
        host=settings.redis.host,
        port=settings.redis.port,
        password=settings.redis.password,
        database=settings.redis.databases.task,
    )
