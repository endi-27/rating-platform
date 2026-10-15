from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import Base, VersionedMixin

if TYPE_CHECKING:
    from src.modules.reviews.infrastructure.models.target_model import TargetModel


class TargetRatingModel(Base, VersionedMixin):
    """ORM таблиця агрегованого знімка рейтингу (TargetRating)."""

    __tablename__ = "target_ratings"

    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.00"), nullable=False)
    bayesian_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.00"), nullable=False)
    star_1_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_2_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_3_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_4_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_5_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Зв'язок
    target: Mapped["TargetModel"] = relationship("TargetModel", back_populates="rating")

    __table_args__ = (
        CheckConstraint("total_reviews >= 0", name="ck_target_ratings_total_reviews_positive"),
        Index("ix_target_ratings_bayesian_score", "bayesian_score"),
        Index("ix_target_ratings_average_score", "average_score"),
    )
