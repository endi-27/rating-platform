from decimal import Decimal

import pytest
from uuid6 import uuid7

from src.core import settings
from src.modules.reviews.application.use_cases import BatchRecalculateRatingsUseCase
from src.modules.reviews.domain.events import (
    ReviewCreatedEvent,
    ReviewDeletedEvent,
    ReviewUpdatedEvent,
)
from src.modules.reviews.domain.models import TargetRating
from src.modules.reviews.event_handlers import (
    handle_review_mutation_buffer_target,
    register_reviews_event_handlers,
)
from tests.unit.fake_repositories import (
    FakeSetBuffer,
    FakeTargetRatingRepository,
)
from tests.unit.fakes import FakeUnitOfWork


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def rating_repo() -> FakeTargetRatingRepository:
    return FakeTargetRatingRepository()


@pytest.fixture
def buffer_key() -> str:
    return settings.redis_sets.dirty_targets_key


@pytest.fixture
def set_buffer() -> FakeSetBuffer:
    return FakeSetBuffer()


@pytest.fixture
def use_case(
    uow: FakeUnitOfWork,
    rating_repo: FakeTargetRatingRepository,
    set_buffer: FakeSetBuffer,
    buffer_key: str,
) -> BatchRecalculateRatingsUseCase:
    return BatchRecalculateRatingsUseCase(
        uow=uow,
        rating_repo=rating_repo,
        buffer=set_buffer,
        buffer_key=buffer_key,
    )


@pytest.mark.asyncio
async def test_batch_recalculate_ratings_empty_buffer(
    use_case: BatchRecalculateRatingsUseCase,
    uow: FakeUnitOfWork,
) -> None:
    """Якщо буфер порожній, Use Case одразу повертає 0 і не відкриває транзакцію."""
    processed = await use_case.execute()
    assert processed == 0
    assert not uow.committed


@pytest.mark.asyncio
async def test_batch_recalculate_ratings_happy_path(
    use_case: BatchRecalculateRatingsUseCase,
    rating_repo: FakeTargetRatingRepository,
    set_buffer: FakeSetBuffer,
    buffer_key: str,
    uow: FakeUnitOfWork,
) -> None:
    """Успішний пакетний перерахунок рейтингів для накопичених у буфері об'єктів."""
    rating_repo.global_mean = Decimal("3.50")

    target_id_1 = uuid7()
    target_id_2 = uuid7()
    target_id_3 = uuid7()

    r1 = TargetRating.create_empty(target_id_1)
    for _ in range(5):
        r1.apply_new_review(5)

    r2 = TargetRating.create_empty(target_id_2)
    for _ in range(10):
        r2.apply_new_review(1)

    r3 = TargetRating.create_empty(target_id_3)

    await rating_repo.save(r1)
    await rating_repo.save(r2)
    await rating_repo.save(r3)

    await set_buffer.add(buffer_key, target_id_1, target_id_2)

    assert await set_buffer.count(buffer_key) == 2

    processed = await use_case.execute(batch_size=10)

    assert processed == 2
    assert uow.committed
    assert await set_buffer.count(buffer_key) == 0

    saved_r1 = await rating_repo.get_by_target_id(target_id_1)
    saved_r2 = await rating_repo.get_by_target_id(target_id_2)
    saved_r3 = await rating_repo.get_by_target_id(target_id_3)

    assert saved_r1 is not None and saved_r1.bayesian_score > Decimal("0.00")
    assert saved_r2 is not None and saved_r2.bayesian_score > Decimal("0.00")
    assert saved_r3 is not None and saved_r3.bayesian_score == Decimal("0.00")


@pytest.mark.asyncio
async def test_batch_recalculate_ratings_respects_batch_size(
    use_case: BatchRecalculateRatingsUseCase,
    rating_repo: FakeTargetRatingRepository,
    set_buffer: FakeSetBuffer,
    buffer_key: str,
) -> None:
    """Use Case вилучає не більше ніж batch_size об'єктів за один запуск."""
    target_ids = [uuid7() for _ in range(5)]
    for tid in target_ids:
        r = TargetRating.create_empty(tid)
        r.apply_new_review(4)
        await rating_repo.save(r)
        await set_buffer.add(buffer_key, tid)

    assert await set_buffer.count(buffer_key) == 5

    processed = await use_case.execute(batch_size=2)
    assert processed == 2
    assert await set_buffer.count(buffer_key) == 3

    remaining_processed = await use_case.execute(batch_size=10)
    assert remaining_processed == 3
    assert await set_buffer.count(buffer_key) == 0


@pytest.mark.asyncio
async def test_batch_recalculate_ratings_missing_target_skipped(
    use_case: BatchRecalculateRatingsUseCase,
    set_buffer: FakeSetBuffer,
    buffer_key: str,
    uow: FakeUnitOfWork,
) -> None:
    """Якщо об'єкт із буфера не знайдено в базі, він пропускається без падіння процесу."""
    missing_id = uuid7()
    await set_buffer.add(buffer_key, missing_id)

    processed = await use_case.execute()
    assert processed == 0
    assert uow.committed


@pytest.mark.asyncio
async def test_event_handler_deduplicates_and_buffers(
    set_buffer: FakeSetBuffer,
    buffer_key: str,
) -> None:
    """Обробник подій мутації відгуку додає target_id у буфер і відсікає дублікати."""
    target_id = uuid7()
    user_id = uuid7()

    events = [
        ReviewCreatedEvent(target_id=target_id, review_id=uuid7(), user_id=user_id, score=5),
        ReviewCreatedEvent(target_id=target_id, review_id=uuid7(), user_id=uuid7(), score=4),
        ReviewUpdatedEvent(target_id=target_id, review_id=uuid7(), user_id=user_id, old_score=4, new_score=5),
        ReviewDeletedEvent(target_id=target_id, review_id=uuid7(), user_id=user_id, score=5),
    ]

    for ev in events:
        await handle_review_mutation_buffer_target(ev, buffer=set_buffer)

    assert await set_buffer.count(buffer_key) == 1
    dirty_batch = await set_buffer.pop_batch(buffer_key, batch_size=10)
    assert dirty_batch == [str(target_id)]


@pytest.mark.asyncio
async def test_register_reviews_event_handlers_subscribes_both_handlers(
    set_buffer: FakeSetBuffer,
    buffer_key: str,
) -> None:
    """Перевірка, що шина подій викликає як інвалідацію кешу, так і буферизацію."""
    from src.core.events import AsyncEventBus

    bus = AsyncEventBus()
    register_reviews_event_handlers(bus, buffer=set_buffer)

    target_id = uuid7()
    user_id = uuid7()
    ev = ReviewCreatedEvent(target_id=target_id, review_id=uuid7(), user_id=user_id, score=5)

    await bus.publish(ev)

    assert await set_buffer.count(buffer_key) == 1
    dirty_batch = await set_buffer.pop_batch(buffer_key, batch_size=10)
    assert dirty_batch == [str(target_id)]


@pytest.mark.asyncio
async def test_set_buffer_generic_arbitrary_key(
    set_buffer: FakeSetBuffer,
) -> None:
    """Буфер ISetBuffer є універсальним інструментом і може працювати з довільними ключами модулів платформи."""
    custom_key = "orders:pending_recalc"
    added = await set_buffer.add(custom_key, "order-1", "order-2")
    assert added == 2
    assert await set_buffer.count(custom_key) == 2

    # Перевірка ідемпотентності
    duplicate_added = await set_buffer.add(custom_key, "order-1")
    assert duplicate_added == 0
    assert await set_buffer.count(custom_key) == 2

    batch = await set_buffer.pop_batch(custom_key, batch_size=1)
    assert len(batch) == 1
    assert await set_buffer.count(custom_key) == 1


@pytest.mark.asyncio
async def test_batch_recalculate_ratings_invalid_uuid_in_buffer(
    use_case: BatchRecalculateRatingsUseCase,
    rating_repo: FakeTargetRatingRepository,
    set_buffer: FakeSetBuffer,
    buffer_key: str,
    uow: FakeUnitOfWork,
) -> None:
    """Невалідні UUID-рядки у буфері ігноруються без падіння Use Case."""
    # 1. Тільки невалідні UUID -> повертає 0 і не відкриває транзакцію
    await set_buffer.add(buffer_key, "not-a-valid-uuid", "12345")
    processed_only_invalid = await use_case.execute()
    assert processed_only_invalid == 0
    assert not uow.committed

    # 2. Суміш невалідного та валідного UUID -> валідний обробляється
    valid_tid = uuid7()
    r = TargetRating.create_empty(valid_tid)
    r.apply_new_review(5)
    await rating_repo.save(r)

    await set_buffer.add(buffer_key, "corrupted-uuid", valid_tid)
    processed_mixed = await use_case.execute()
    assert processed_mixed == 1
    assert uow.committed


@pytest.mark.asyncio
async def test_event_handler_buffer_exception_logged_not_raised() -> None:
    """Якщо буфер Redis кидає виняток, обробник перехоплює його і не валить потік."""
    broken_buffer = FakeSetBuffer()

    async def broken_add(key: str, *values: object) -> int:
        raise RuntimeError("Redis connection lost")

    broken_buffer.add = broken_add  # type: ignore[method-assign]

    ev = ReviewCreatedEvent(target_id=uuid7(), review_id=uuid7(), user_id=uuid7(), score=5)
    await handle_review_mutation_buffer_target(ev, buffer=broken_buffer)
