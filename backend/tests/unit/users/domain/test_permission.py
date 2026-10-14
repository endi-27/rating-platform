from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from uuid6 import uuid7

from src.core import PermissionCode
from src.modules.users.domain import Permission


def test_permission_initialization_defaults() -> None:
    perm_id = uuid7()
    perm = Permission(
        id=perm_id,
        code=PermissionCode.USERS_READ,
        name="Перегляд користувачів",
    )

    assert perm.id == perm_id
    assert perm.code == PermissionCode.USERS_READ
    assert perm.name == "Перегляд користувачів"
    assert perm.description is None
    assert isinstance(perm.created_at, datetime)
    assert perm.created_at.tzinfo == UTC


def test_permission_custom_attributes() -> None:
    perm_id = uuid7()
    custom_time = datetime(2025, 3, 1, 10, 0, tzinfo=UTC)
    perm = Permission(
        id=perm_id,
        code=PermissionCode.USERS_CREATE,
        name="Створення користувачів",
        description="Дозвіл на додавання нових користувачів у систему",
        created_at=custom_time,
    )

    assert perm.description == "Дозвіл на додавання нових користувачів у систему"
    assert perm.created_at == custom_time


def test_permission_is_immutable() -> None:
    perm = Permission(
        id=uuid7(),
        code=PermissionCode.USERS_UPDATE,
        name="Редагування користувачів",
    )

    with pytest.raises(FrozenInstanceError):
        perm.name = "Нова назва"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        perm.description = "Новий опис"  # type: ignore[misc]
