from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.api import (
    setup_custom_openapi,
    setup_exception_handlers,
    setup_middlewares,
)
from src.api.events_setup import setup_application_events
from src.api.v1 import api_v1_router
from src.core import (
    close_db,
    close_redis,
    get_redis_client,
    logger,
    settings,
    setup_logging,
)
from src.core.events import get_event_bus
from src.infrastructure.cache import setup_cache
from src.tasks import close_task_dispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Керування життєвим циклом FastAPI додатку."""
    # Startup
    setup_logging()
    logger.info("Ініціалізація бекенду rating-platform ({env})...", env=settings.environment)
    bus = get_event_bus()
    setup_application_events(bus)
    setup_cache(get_redis_client(settings.redis.databases.cache))

    yield

    # Shutdown
    logger.info("Завершення роботи бекенду rating-platform...")
    await close_task_dispatcher()
    await close_redis()
    await close_db()
    logger.info("Ресурси успішно вивільнено.")


# Створення головного екземпляра додатку (Composition Root)
app = FastAPI(
    title="Distributed Reviews & Ratings Platform API",
    description=(
        "Високонавантажена розподілена платформа збору та агрегації відгуків і призначених користувачем рейтингів"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Підключення глобальних HTTP-мідлварів
setup_middlewares(app)

# Підключення глобальних обробників винятків
setup_exception_handlers(app)

# Налаштування розширеної схеми OpenAPI (x- розширення для параметрів)
setup_custom_openapi(app)

# Підключення роутерів версій API
app.include_router(api_v1_router, prefix=settings.api.v1_prefix)


@app.get("/", tags=["System"])
async def root() -> dict[str, Any]:
    """Кореневий ендпоінт перевірки статусу системи."""
    return {
        "service": "Rating Platform Backend",
        "version": "0.1.0",
        "docs": "/docs",
        "health": f"{settings.api.v1_prefix}/health",
    }
