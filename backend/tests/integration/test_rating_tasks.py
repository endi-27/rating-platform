from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from uuid6 import uuid7

from src.core import settings
from src.core.redis import close_redis, get_redis_client
from src.infrastructure.redis import RedisSetBuffer
from src.modules.reviews.infrastructure.models import TargetModel, TargetRatingModel
from src.tasks.functions.rating_tasks import process_dirty_target_ratings_task


@pytest.mark.asyncio
async def test_process_dirty_target_ratings_task_missing_session_factory() -> None:
    """Крон-задача повинна піднімати помилку, якщо в контексті відсутня фабрика сесій."""
    with pytest.raises(RuntimeError, match="відсутня фабрика сесій 'session_factory'"):
        await process_dirty_target_ratings_task(ctx={})


@pytest.mark.asyncio
async def test_process_dirty_target_ratings_task_with_real_test_db(
    test_engine: AsyncEngine,
) -> None:
    """
    Повноцінний інтеграційний тест крон-задачі воркера проти тестової БД:
    1. Створює цільовий об'єкт та його початковий рейтинг у реальній rating_test_db.
    2. Додає ID таргету до RedisSetBuffer.
    3. Виконує process_dirty_target_ratings_task з передачею session_factory та буфера.
    4. Перевіряє, що розраховано bayesian_score та очищено буфер.
    """
    # 1. Створюємо цільовий об'єкт і рейтинг у тестовій базі через окрему зафіксовану сесію
    session_factory = async_sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    target_id = uuid7()
    async with session_factory() as setup_session:
        target = TargetModel(
            id=target_id,
            version=1,
            slug=f"task-test-target-{uuid7().hex[:8]}",
            title="Integration Task Test Target",
            category="testing",
        )
        setup_session.add(target)
        await setup_session.flush()

        rating = TargetRatingModel(
            target_id=target_id,
            version=1,
            total_reviews=10,
            average_score=Decimal("4.50"),
            bayesian_score=Decimal("0.00"),
            star_1_count=0,
            star_2_count=0,
            star_3_count=1,
            star_4_count=3,
            star_5_count=6,
        )
        setup_session.add(rating)
        await setup_session.commit()

    # 2. Готуємо Redis Set буфер
    redis_client = get_redis_client()
    buffer = RedisSetBuffer(redis=redis_client)
    buffer_key = settings.redis_sets.dirty_targets_key

    try:
        # Очищуємо залишкові ключі від попередніх запусків перед тестом
        await redis_client.delete(buffer_key)
        await buffer.add(buffer_key, target_id)
        assert await buffer.count(buffer_key) == 1

        ctx: dict[str, object] = {
            "session_factory": session_factory,
            "set_buffer": buffer,
        }

        # 3. Виклик крон-задачі
        result = await process_dirty_target_ratings_task(ctx=ctx, batch_size=100)

        # 4. Перевірка результатів
        assert result["status"] == "success"
        assert result["processed"] == 1
        assert await buffer.count(buffer_key) == 0

        # Перевіряємо в тестовій БД, що bayesian_score оновився
        async with session_factory() as check_session:
            stmt = select(TargetRatingModel).where(TargetRatingModel.target_id == target_id)
            updated_rating = (await check_session.execute(stmt)).scalar_one()
            assert updated_rating.bayesian_score > Decimal("0.00")

    finally:
        # Прибирання за собою в тестовій БД та Redis
        async with test_engine.connect() as conn:
            await conn.execute(delete(TargetModel).where(TargetModel.id == target_id))
            await conn.commit()
        await redis_client.srem(buffer_key, str(target_id))
        await redis_client.aclose()  # type: ignore[attr-defined]
        await close_redis()
