from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)


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
    )
    reviews: Mapped[list["ReviewModel"]] = relationship(
        "ReviewModel",
        back_populates="target",
        cascade="all, delete-orphan",
    )


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


class ReviewModel(Base, UUIDPrimaryKeyMixin, VersionedMixin, TimestampMixin, SoftDeleteMixin):
    """ORM таблиця відгуків користувачів (Review)."""

    __tablename__ = "reviews"

    target_id: Mapped[UUID] = mapped_column(
        ForeignKey("targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="published", default="published", nullable=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unhelpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Зв'язки
    target: Mapped["TargetModel"] = relationship("TargetModel", back_populates="reviews")
    votes: Mapped[list["ReviewVoteModel"]] = relationship(
        "ReviewVoteModel",
        back_populates="review",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("target_id", "user_id", name="uq_reviews_target_user"),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_reviews_score_range"),
        Index("ix_reviews_target_status_created", "target_id", "status", "created_at"),
    )


class ReviewVoteModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """ORM таблиця оцінок корисності відгуків (ReviewVote)."""

    __tablename__ = "review_votes"

    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Зв'язок
    review: Mapped["ReviewModel"] = relationship("ReviewModel", back_populates="votes")

    __table_args__ = (UniqueConstraint("review_id", "user_id", name="uq_review_votes_review_user"),)
