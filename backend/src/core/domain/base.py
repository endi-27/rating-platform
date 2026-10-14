from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from src.core.exceptions import (
    InactiveEntityError,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
)


@dataclass(kw_only=True)
class BaseEntity:
    """Базова доменна сутність з ідентифікатором та часом створення."""

    id: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(kw_only=True)
class AggregateRoot(BaseEntity):
    """
    Базовий агрегат DDD із підтримкою версіонування (OCC),
    мітки часу модифікації та життєвого циклу Soft Delete.
    """

    version: int = 1
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Прапорець активності (відсутність мітки soft-delete)."""
        return self.deleted_at is None

    def ensure_active(
        self,
        action_phrase: str = "виконати дію над деактивованим ресурсом",
        restore_hint: str = "Спочатку відновіть його.",
    ) -> None:
        """Перевірка активності агрегата для захисту інваріантів від мутацій у деактивованому стані."""
        if not self.is_active:
            clean_action = action_phrase.strip().rstrip(".")
            hint = f" {restore_hint.strip()}" if restore_hint else ""
            raise InactiveEntityError(f"Неможливо {clean_action}.{hint}".strip())

    def soft_delete(self) -> None:
        """М'яке видалення (деактивація) агрегата."""
        if not self.is_active:
            raise ResourceAlreadyInactiveException("Цей ресурс вже є неактивним.")

        self.deleted_at = datetime.now(UTC)
        self.updated_at = self.deleted_at

    def restore(self) -> None:
        """Відновлення агрегата з неактивного стану."""
        if self.is_active:
            raise ResourceAlreadyActiveException("Цей ресурс вже є активним.")

        self.deleted_at = None
        self.updated_at = datetime.now(UTC)
