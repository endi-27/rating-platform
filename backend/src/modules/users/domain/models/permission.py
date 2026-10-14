from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from src.core import PermissionCode


@dataclass(frozen=True, slots=True)
class Permission:
    """Доменна сутність системного права доступу (Read-Only)."""

    id: UUID
    code: PermissionCode
    name: str
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
