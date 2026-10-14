from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateTargetDTO(BaseModel):
    """Схема створення нового об'єкта оцінювання."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: Annotated[
        str,
        Field(
            min_length=2,
            max_length=200,
            pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
            description="URL-slug у форматі kebab-case (наприклад, interstellar-2014)",
            examples=["interstellar-2014"],
        ),
    ]
    title: Annotated[
        str,
        Field(min_length=1, max_length=255, description="Назва об'єкта", examples=["Інтерстеллар"]),
    ]
    category: Annotated[
        str,
        Field(min_length=1, max_length=100, description="Категорія об'єкта", examples=["movie"]),
    ]
    description: Annotated[
        str | None,
        Field(default=None, max_length=2000, description="Детальний опис"),
    ] = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Специфічні властивості об'єкта (JSONB)",
    )


class UpdateTargetDTO(BaseModel):
    """Схема оновлення інформації про об'єкт."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    category: Annotated[str | None, Field(default=None, min_length=1, max_length=100)] = None
    description: Annotated[str | None, Field(default=None, max_length=2000)] = None
    metadata: Annotated[dict[str, Any] | None, Field(default=None)] = None
    version: Annotated[int, Field(ge=1, description="OCC версія")]


class TargetRatingResponseDTO(BaseModel):
    """Схема агрегованого рейтингу об'єкта."""

    model_config = ConfigDict(from_attributes=True)

    total_reviews: int
    average_score: Decimal
    bayesian_score: Decimal
    star_1_count: int
    star_2_count: int
    star_3_count: int
    star_4_count: int
    star_5_count: int
    last_calculated_at: datetime


class TargetResponseDTO(BaseModel):
    """Схема детальної картки об'єкта оцінювання."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    category: str
    description: str | None
    metadata: dict[str, Any]
    is_active: bool
    version: int
    rating: TargetRatingResponseDTO | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CreateReviewDTO(BaseModel):
    """Схема створення відгуку."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    score: Annotated[int, Field(ge=1, le=5, description="Оцінка від 1 до 5 зірок", examples=[5])]
    title: Annotated[
        str | None,
        Field(default=None, max_length=150, description="Короткий заголовок враження"),
    ] = None
    content: Annotated[
        str,
        Field(
            min_length=10,
            max_length=5000,
            description="Текст відгуку (від 10 до 5000 символів)",
            examples=["Неймовірний фільм, візуальний ряд та музика на найвищому рівні!"],
        ),
    ]


class ReviewResponseDTO(BaseModel):
    """Схема відповіді для відгуку."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_id: UUID
    user_id: UUID
    score: int
    title: str | None
    content: str
    status: str
    helpful_count: int
    unhelpful_count: int
    version: int
    created_at: datetime
    updated_at: datetime | None = None


class VoteReviewDTO(BaseModel):
    """Схема голосування за корисність."""

    model_config = ConfigDict(extra="forbid")

    is_helpful: Annotated[
        bool,
        Field(description="True — корисно (👍), False — не корисно (👎)"),
    ]


class ModerateReviewDTO(BaseModel):
    """Схема модерації відгуку."""

    model_config = ConfigDict(extra="forbid")

    action: Annotated[
        str,
        Field(
            pattern="^(hide|publish|flag)$",
            description="Дія модерації: hide (приховати), publish (опублікувати), flag (позначити)",
        ),
    ]
