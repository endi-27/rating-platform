from __future__ import annotations

from src.core import settings
from src.core.events import AsyncEventBus, BaseEvent
from src.infrastructure.cache import clear_cache_with_dependencies
from src.modules.users.domain.events import (
    RoleCreatedEvent,
    RoleDeactivatedEvent,
    RoleDeletedEvent,
    RoleRestoredEvent,
    RoleUpdatedEvent,
    UserCreatedEvent,
    UserCredentialsChangedEvent,
    UserDeactivatedEvent,
    UserDeletedEvent,
    UserPasswordChangedEvent,
    UserRestoredEvent,
    UserUpdatedEvent,
    UserUsernameChangedEvent,
)

# === 1. Обробники інвалідації кешу (Cache Invalidation) ===


async def invalidate_users_cache(event: BaseEvent) -> None:
    """Інвалідація простору імен користувачів при будь-яких мутаціях (створення, оновлення, видалення)."""
    await clear_cache_with_dependencies(settings.cache.namespace.users)


async def invalidate_roles_cache(event: BaseEvent) -> None:
    """
    Інвалідація простору ролей при будь-яких мутаціях ролей.
    Завдяки матриці залежностей каскадно очищує також простір користувачів.
    """
    await clear_cache_with_dependencies(settings.cache.namespace.roles)


# === 2. Реєстрація обробників у шині подій ===


def register_users_event_handlers(bus: AsyncEventBus) -> None:
    """Реєстрація обробників подій модуля users у шині AsyncEventBus."""
    # 1. Підписка кешу на всі мутації користувачів
    for user_event_cls in (
        UserCreatedEvent,
        UserUpdatedEvent,
        UserUsernameChangedEvent,
        UserCredentialsChangedEvent,
        UserPasswordChangedEvent,
        UserDeactivatedEvent,
        UserRestoredEvent,
        UserDeletedEvent,
    ):
        bus.on(user_event_cls)(invalidate_users_cache)

    # 2. Підписка кешу на всі мутації ролей
    for role_event_cls in (
        RoleCreatedEvent,
        RoleUpdatedEvent,
        RoleDeactivatedEvent,
        RoleRestoredEvent,
        RoleDeletedEvent,
    ):
        bus.on(role_event_cls)(invalidate_roles_cache)
