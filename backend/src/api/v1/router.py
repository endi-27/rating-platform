from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.core import db_router, get_redis_client, settings
from src.modules.auth.router import auth_router
from src.modules.users.routers import (
    permissions_router,
    roles_router,
    users_router,
)

api_v1_router = APIRouter()


@api_v1_router.get("/health", tags=["System"])
async def health_check(response: Response) -> dict[str, Any]:
    """
    Комплексна перевірка працездатності сервісу та його компонентів (Health Check).
    Валідує доступність PostgreSQL (SELECT 1) та Redis (PING).
    Повертає 503 Service Unavailable у випадку збою будь-якої критичної залежності.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "instance_id": settings.instance_id,
        "environment": settings.environment,
        "version": "0.1.0",
        "dependencies": {},
    }
    is_healthy = True

    # 1. Перевірка бази даних (PostgreSQL)
    try:
        async with db_router.get_session(operation="read") as session:
            await session.execute(text("SELECT 1"))
        health_status["dependencies"]["database"] = "ok"
    except Exception as exc:
        health_status["dependencies"]["database"] = f"unhealthy: {exc}"
        is_healthy = False

    # 2. Перевірка Redis
    try:
        redis_client = get_redis_client(settings.redis.databases.cache)
        await redis_client.ping()
        health_status["dependencies"]["redis"] = "ok"
    except Exception as exc:
        health_status["dependencies"]["redis"] = f"unhealthy: {exc}"
        is_healthy = False

    if not is_healthy:
        health_status["status"] = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_status


# Підключення роутерів модулів платформи
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(roles_router)
api_v1_router.include_router(permissions_router)
