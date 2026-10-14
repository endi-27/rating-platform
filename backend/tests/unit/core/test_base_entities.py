from datetime import UTC, datetime

import pytest
from uuid6 import uuid7

from src.core.domain import AggregateRoot, BaseEntity
from src.core.exceptions import (
    InactiveEntityError,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
)


class DummyEntity(BaseEntity):
    """Тестова конкретна сутність для перевірки BaseEntity."""


class DummyAggregate(AggregateRoot):
    """Тестовий конкретний агрегат для перевірки AggregateRoot."""


def test_base_entity_initialization() -> None:
    entity_id = uuid7()
    entity = DummyEntity(id=entity_id)

    assert entity.id == entity_id
    assert isinstance(entity.created_at, datetime)
    assert entity.created_at.tzinfo == UTC


def test_base_entity_custom_created_at() -> None:
    entity_id = uuid7()
    custom_time = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    entity = DummyEntity(id=entity_id, created_at=custom_time)

    assert entity.id == entity_id
    assert entity.created_at == custom_time


def test_aggregate_root_defaults() -> None:
    agg_id = uuid7()
    agg = DummyAggregate(id=agg_id)

    assert agg.id == agg_id
    assert agg.version == 1
    assert agg.updated_at is None
    assert agg.deleted_at is None
    assert agg.is_active is True


def test_aggregate_root_ensure_active_success() -> None:
    agg = DummyAggregate(id=uuid7())
    # Should not raise exception when active
    agg.ensure_active()


def test_aggregate_root_ensure_active_inactive_raises_default() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active()

    assert "Неможливо виконати дію над деактивованим ресурсом. Спочатку відновіть його." in str(exc_info.value)


def test_aggregate_root_ensure_active_custom_phrase_and_hint() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active(
            action_phrase="змінити логін деактивованого користувача.",
            restore_hint="Потрібне відновлення.",
        )

    assert "Неможливо змінити логін деактивованого користувача. Потрібне відновлення." in str(exc_info.value)


def test_aggregate_root_ensure_active_empty_hint() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active(
            action_phrase="видалити",
            restore_hint="",
        )

    assert str(exc_info.value) == "Неможливо видалити."


def test_aggregate_root_soft_delete_success() -> None:
    agg = DummyAggregate(id=uuid7())
    assert agg.is_active is True
    assert agg.deleted_at is None
    assert agg.updated_at is None

    agg.soft_delete()

    assert agg.is_active is False
    assert agg.deleted_at is not None
    assert agg.updated_at is not None
    assert agg.deleted_at == agg.updated_at
    assert agg.deleted_at.tzinfo == UTC


def test_aggregate_root_soft_delete_already_inactive_raises() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    with pytest.raises(ResourceAlreadyInactiveException) as exc_info:
        agg.soft_delete()

    assert "Цей ресурс вже є неактивним." in str(exc_info.value)


def test_aggregate_root_restore_success() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    agg.restore()

    assert agg.is_active is True
    assert agg.deleted_at is None
    assert agg.updated_at is not None
    assert agg.updated_at.tzinfo == UTC


def test_aggregate_root_restore_already_active_raises() -> None:
    agg = DummyAggregate(id=uuid7())
    assert agg.is_active is True

    with pytest.raises(ResourceAlreadyActiveException) as exc_info:
        agg.restore()

    assert "Цей ресурс вже є активним." in str(exc_info.value)
