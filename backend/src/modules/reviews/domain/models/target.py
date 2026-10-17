from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from uuid6 import uuid7

from src.core.domain.base import AggregateRoot
from src.core.exceptions import DomainException


@dataclass(kw_only=True)
class Target(AggregateRoot):
    """
    Доменний агрегат об'єкта оцінювання (Target).
    Це може бути фільм, книга, товар, заклад, курс чи послуга.
    """

    slug: str
    title: str
    category: str
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by_id: UUID | None = None

    def __post_init__(self) -> None:
        self.slug = self.slug.strip().lower()
        self.title = self.title.strip()
        self.category = self.category.strip().lower()
        if self.description is not None:
            clean_desc = self.description.strip()
            self.description = clean_desc if clean_desc else None

        if not self.slug:
            raise DomainException("URL-ідентифікатор (slug) об'єкта не може бути порожнім.")
        if not self.title or len(self.title) > 255:
            raise DomainException("Назва об'єкта повинна містити від 1 до 255 символів.")
        if not self.category or len(self.category) > 100:
            raise DomainException("Категорія повинна містити від 1 до 100 символів.")

    @classmethod
    def create(
        cls,
        *,
        slug: str,
        title: str,
        category: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by_id: UUID | None = None,
    ) -> "Target":
        """Фабричний метод створення нового об'єкта оцінювання."""
        return cls(
            id=uuid7(),
            slug=slug,
            title=title,
            category=category,
            description=description.strip() if description and description.strip() else None,
            metadata=dict(metadata or {}),
            created_by_id=created_by_id,
        )

    def update_details(
        self,
        *,
        title: str | None = None,
        category: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Оновлення інформаційних полів об'єкта."""
        self.ensure_active(action_phrase="оновити деактивований об'єкт")

        if title is not None:
            clean_title = title.strip()
            if not clean_title or len(clean_title) > 255:
                raise DomainException("Назва об'єкта повинна містити від 1 до 255 символів.")
            self.title = clean_title

        if category is not None:
            clean_category = category.strip().lower()
            if not clean_category or len(clean_category) > 100:
                raise DomainException("Категорія повинна містити від 1 до 100 символів.")
            self.category = clean_category

        if description is not None:
            self.description = description.strip() if description.strip() else None

        if metadata is not None:
            self.metadata = dict(metadata)

        self.updated_at = datetime.now(UTC)
