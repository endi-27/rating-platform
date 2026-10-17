from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from src.modules.reviews.domain.enums import ReviewStatus


class TargetFilterDTO(BaseModel):
    """Параметри фільтрації списку об'єктів оцінювання."""

    category: Annotated[str | None, Field(description="Фільтр за категорією об'єкта")] = None
    search: Annotated[str | None, Field(description="Пошуковий рядок (назва або slug)")] = None
    min_rating: Annotated[Decimal | None, Field(ge=0, le=5, description="Мінімальний середній бал")] = None
    include_inactive: Annotated[bool, Field(description="Включити деактивовані об'єкти")] = False


class ReviewFilterDTO(BaseModel):
    """Параметри фільтрації стрічки відгуків об'єкта."""

    target_id: Annotated[UUID, Field(description="ID об'єкта оцінювання (Shard Key)")]
    status: Annotated[ReviewStatus, Field(description="Статус модерації відгуку")] = ReviewStatus.PUBLISHED
    score: Annotated[int | None, Field(ge=1, le=5, description="Фільтр за точною оцінкою (1..5)")] = None
    min_score: Annotated[int | None, Field(ge=1, le=5, description="Мінімальна оцінка зірок")] = None
    author_id: Annotated[UUID | None, Field(description="Фільтр за автором відгуку")] = None
