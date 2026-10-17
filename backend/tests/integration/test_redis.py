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


@pytest.mark.asyncio
async def test_redis_set_buffer_operations() -> None:
    """Перевірка функціонування розподіленого буфера RedisSetBuffer проти реального Redis."""
    from uuid6 import uuid7

    from src.infrastructure.redis import RedisSetBuffer

    client = get_redis_client()
    buffer = RedisSetBuffer(redis=client)
    test_key = "rating:test:set_buffer_test"

    try:
        await client.delete(test_key)

        id1 = uuid7()
        id2 = uuid7()
        id3 = uuid7()

        # 1. Додавання
        added = await buffer.add(test_key, id1, id2, id3)
        assert added == 3

        # 2. Ідемпотентність
        added_duplicate = await buffer.add(test_key, id1)
        assert added_duplicate == 0

        # 3. Підрахунок
        count = await buffer.count(test_key)
        assert count == 3

        # 4. Вилучення пачки
        batch = await buffer.pop_batch(test_key, batch_size=2)
        assert len(batch) == 2
        assert all(isinstance(x, str) for x in batch)

        # 5. Залишок
        remaining_count = await buffer.count(test_key)
        assert remaining_count == 1

        # 6. Вилучення залишку
        final_batch = await buffer.pop_batch(test_key, batch_size=10)
        assert len(final_batch) == 1
        assert await buffer.count(test_key) == 0
    finally:
        await client.delete(test_key)
        await client.aclose()  # type: ignore[attr-defined]
        await close_redis()
