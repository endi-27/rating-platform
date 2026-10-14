import pytest

from src.core.redis import close_redis, get_redis_client


@pytest.mark.asyncio
async def test_redis_ping() -> None:
    """Перевірка живого підключення до Redis (команда PING)."""
    client = get_redis_client()
    try:
        pong = await client.ping()
        assert pong is True
    finally:
        await client.aclose()  # type: ignore[attr-defined]
        await close_redis()


@pytest.mark.asyncio
async def test_redis_crud_operations() -> None:
    """Перевірка базових операцій запису, читання, TTL та видалення ключів у Redis."""
    client = get_redis_client()
    test_key = "rating:test:health_check_key"
    test_val = "rating_ok_value"

    try:
        # 1. Запис зі строком дії (TTL 60 секунд)
        await client.set(test_key, test_val, ex=60)

        # 2. Читання
        val = await client.get(test_key)
        assert val == test_val

        # 3. Перевірка TTL
        ttl = await client.ttl(test_key)
        assert ttl > 0

        # 4. Видалення
        deleted = await client.delete(test_key)
        assert deleted == 1

        # 5. Перевірка відсутності ключа
        val_after_del = await client.get(test_key)
        assert val_after_del is None
    finally:
        await client.aclose()  # type: ignore[attr-defined]
        await close_redis()
