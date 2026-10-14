import re
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field
from uuid6 import uuid7

from src.core.context import get_correlation_id, get_current_user_id


def _to_snake_case(name: str) -> str:
    """Конвертує PascalCase назву класу в UPPER_SNAKE_CASE (напр. UserCreatedEvent -> USER_CREATED)."""
    if name.endswith("Event"):
        name = name[:-5]
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return s


class BaseEvent(BaseModel):
    """
    Базовий незмінний клас доменних та системних подій.
    Усі атрибути події є незмінними після створення (frozen=True).
    """

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(
        default_factory=uuid7,
        description="Унікальний часово-впорядкований ID події (UUIDv7)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC мітка часу події",
    )
    entity_id: UUID | None = Field(
        default=None,
        description="ID цільової сутності (якщо застосовно)",
    )
    actor_id: UUID | None = Field(
        default_factory=get_current_user_id,
        description="ID користувача, що ініціював дію (для аудит-логу)",
    )
    correlation_id: str | None = Field(
        default_factory=get_correlation_id,
        description="Request ID для наскрізного трасування",
    )
    event_name_override: str | None = Field(
        default=None,
        description="Опціональне явне перевизначення назви події",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def event_name(self) -> str:
        """Повертає назву події (явну або згенеровану з назви класу в UPPER_SNAKE_CASE)."""
        if self.event_name_override:
            return self.event_name_override
        return _to_snake_case(self.__class__.__name__)
