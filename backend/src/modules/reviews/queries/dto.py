from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
