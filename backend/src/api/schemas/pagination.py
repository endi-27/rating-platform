import math
from collections.abc import Sequence
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field


class PaginationParams(BaseModel):
    """Стандартні параметри пагінації для Query Services."""

    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(ge=1, description="Номер сторінки (1-based)")] = 1
    page_size: Annotated[int, Field(ge=1, le=100, description="Кількість записів на сторінці")] = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse[TItem](BaseModel):
    """
    Уніфікована схема пагінованої відповіді для всіх Read-ендпоінтів (CQRS Query Services).
    Забезпечує консистентну структуру даних для фронтенду.
    """

    items: list[TItem]
    total: Annotated[int, Field(ge=0, description="Загальна кількість записів")]
    page: Annotated[int, Field(ge=1, description="Поточний номер сторінки")]
    page_size: Annotated[int, Field(ge=1, description="Розмір сторінки")]
    total_pages: Annotated[int, Field(ge=0, description="Загальна кількість сторінок")]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_next(self) -> bool:
        """Чи існує наступна сторінка результатів."""
        return self.page < self.total_pages

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_previous(self) -> bool:
        """Чи існує попередня сторінка результатів."""
        return self.page > 1

    @classmethod
    def create(
        cls,
        items: Sequence[Any],
        total: int,
        pagination: PaginationParams,
    ) -> Self:
        """Фабричний метод створення пагінованої відповіді з розрахунком total_pages."""
        total_pages = math.ceil(total / pagination.page_size) if total > 0 else 0
        return cls(
            items=list(items),
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
        )
