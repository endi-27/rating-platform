from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    CreatedByMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from src.modules.reviews.infrastructure.models.review_model import ReviewModel
    from src.modules.reviews.infrastructure.models.target_rating_model import TargetRatingModel


class TargetModel(Base, UUIDPrimaryKeyMixin, VersionedMixin, TimestampMixin, SoftDeleteMixin, CreatedByMixin):
    """ORM таблиця об'єктів оцінювання (Target)."""

    __tablename__ = "targets"

    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        default=dict,
        nullable=False,
    )

    # Зв'язки
    rating: Mapped["TargetRatingModel | None"] = relationship(
        "TargetRatingModel",
        back_populates="target",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="raise",
    )
    reviews: Mapped[list["ReviewModel"]] = relationship(
        "ReviewModel",
        back_populates="target",
        cascade="all, delete-orphan",
        lazy="raise",
    )
