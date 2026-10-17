from __future__ import annotations

from src.core.events import AsyncEventBus
from src.modules.reviews.event_handlers import register_reviews_event_handlers
from src.modules.users import register_users_event_handlers


def setup_application_events(bus: AsyncEventBus) -> None:
    """
    Конфігурація обробників подій рівня застосунку (Composition Root).
    Підключає модульні слухачі подій (Domain Modules).
    """
    # Модульні слухачі подій (Domain Modules)
    register_users_event_handlers(bus)
    register_reviews_event_handlers(bus)
