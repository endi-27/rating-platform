from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.core import ISetBuffer, get_redis_client, settings


class RedisSetBuffer(ISetBuffer):
    """
    Універсальний розподілений буфер на базі множин Redis Set (Infrastructure Adapter).

    Забезпечує:
    1. Idempotent O(1) операцію додавання (SADD) за довільним переданим ключем.
    2. Атомарне вилучення пачки елементів (SPOP) без race conditions для пакетної обробки.
    3. Повну відв'язку від конкретних бізнес-модулів — може використовуватись будь-яким модулем платформи.
    """

    def __init__(self, redis: Redis[Any]) -> None:
        self._redis = redis

    async def add(self, key: str, *items: str | UUID) -> int:
        """Додає один або декілька елементів у вказану множину Redis."""
        if not items:
            return 0
        str_items = [str(item) for item in items]
        added = await self._redis.sadd(key, *str_items)
        return added if added is not None else 0

    async def pop_batch(self, key: str, batch_size: int = 100) -> list[str]:
        """Атомарно вилучає до batch_size елементів із вказаної множини Redis."""
        raw_members = await self._redis.spop(key, count=batch_size)  # type: ignore[arg-type]
        if not raw_members:
            return []

        if isinstance(raw_members, (str, bytes)):
            raw_members = [raw_members]

        return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in raw_members]

    async def count(self, key: str) -> int:
        """Повертає поточну кількість елементів у вказаній множині Redis."""
        count = await self._redis.scard(key)
        return count if count is not None else 0


def get_set_buffer() -> ISetBuffer:
    """Глобальна фабрика розподіленого буфера Redis Set."""
    redis = get_redis_client(settings.redis.databases.cache)
    return RedisSetBuffer(redis=redis)
