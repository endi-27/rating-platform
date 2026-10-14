from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.coder import JsonCoder, object_hook
from redis.asyncio import Redis

from src.core import logger

# Контекстна змінна для фіксації відмови Redis та виставлення заголовка X-Cache: FALLBACK
cache_fallback_ctx: ContextVar[bool] = ContextVar("cache_fallback_ctx", default=False)


async def delete_by_pattern(redis: Redis[Any], pattern: str, batch_size: int = 200) -> int:
    """Неблокуюче пакетне видалення ключів у Redis за патерном через scan_iter."""
    safe_batch_size = max(1, batch_size)
    batch: list[str] = []
    total_deleted = 0
    try:
        async for key in redis.scan_iter(match=pattern, count=100):
            batch.append(key)
            if len(batch) >= safe_batch_size:
                deleted = await redis.delete(*batch)
                total_deleted += deleted if isinstance(deleted, int) else len(batch)
                batch.clear()
        if batch:
            deleted = await redis.delete(*batch)
            total_deleted += deleted if isinstance(deleted, int) else len(batch)
    except Exception as exc:
        logger.warning(
            "Помилка під час видалення ключів за патерном '{pattern}': {err}",
            pattern=pattern,
            err=str(exc),
        )
    return total_deleted


class SafeRedisBackend(RedisBackend):
    """
    Безпечний RedisBackend для FastAPICache з:
    1. Автоматичною конвертацією str у bytes при роботі з Redis-клієнтом (decode_responses=True).
    2. Неблокуючим пакетним видаленням ключів через scan_iter (усуває ризик блокування KEYS).
    3. Graceful degradation при мережевих збоях Redis (повернення miss замість HTTP 500).
    """

    async def get_with_ttl(self, key: str) -> tuple[int, bytes | None]:
        try:
            ttl, val = await super().get_with_ttl(key)
            if isinstance(val, str):
                val = val.encode("utf-8")
            return ttl, val
        except Exception as exc:
            cache_fallback_ctx.set(True)
            logger.warning(
                "Помилка отримання ключа '{key}' з Redis кешу: {err}",
                key=key,
                err=str(exc),
            )
            return 0, None

    async def get(self, key: str) -> bytes | None:
        try:
            val = await super().get(key)
            if isinstance(val, str):
                return val.encode("utf-8")
            return val
        except Exception as exc:
            logger.warning(
                "Помилка читання ключа '{key}' з Redis кешу: {err}",
                key=key,
                err=str(exc),
            )
            return None

    async def set(self, key: str, value: bytes, expire: int | None = None) -> None:
        try:
            await super().set(key, value, expire=expire)
        except Exception as exc:
            logger.warning(
                "Помилка запису ключа '{key}' у Redis кеш: {err}",
                key=key,
                err=str(exc),
            )

    async def clear(self, namespace: str | None = None, key: str | None = None) -> int:
        try:
            if key:
                deleted = await self.redis.delete(key)  # type: ignore[union-attr]
                return deleted if isinstance(deleted, int) else (1 if deleted else 0)
            if namespace:
                pattern = f"{namespace.rstrip(':')}:*"
                return await delete_by_pattern(self.redis, pattern)  # type: ignore[arg-type]
            return 0
        except Exception as exc:
            logger.warning(
                "Помилка очищення кешу Redis (namespace={ns}, key={k}): {err}",
                ns=namespace,
                k=key,
                err=str(exc),
            )
            return 0


class SafeJsonCoder(JsonCoder):
    """
    Безпечний JSON-кодер для FastAPICache.
    Підтримує декодування як байтів (bytes), так і рядків (str), запобігаючи
    помилці AttributeError: 'str' object has no attribute 'decode' при роботі
    з Redis-клієнтами, налаштованими з decode_responses=True.
    """

    @classmethod
    def decode(cls, value: bytes | str) -> Any:
        if isinstance(value, str):
            return json.loads(value, object_hook=object_hook)
        return super().decode(value)
