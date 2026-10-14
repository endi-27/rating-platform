from __future__ import annotations

from typing import Any

from fastapi_cache import FastAPICache
from redis.asyncio import Redis

from src.core import get_redis_client, settings
from src.infrastructure.cache.backend import SafeJsonCoder, SafeRedisBackend
from src.infrastructure.cache.key_builders import default_key_builder


def setup_cache(redis_client: Redis[Any] | None = None) -> None:
    """Ініціалізація глобального FastAPICache з кастомним SafeRedisBackend, SafeJsonCoder та білдером ключів."""
    redis = redis_client or get_redis_client(settings.redis.databases.cache)
    FastAPICache.init(
        backend=SafeRedisBackend(redis),
        coder=SafeJsonCoder,
        prefix=settings.cache.prefix,
        expire=settings.cache.expire,
        key_builder=default_key_builder,
        cache_status_header="X-Cache",
    )
