from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from src.modules.reviews.infrastructure.models.review_vote_model import ReviewVoteModel
    from src.modules.reviews.infrastructure.models.target_model import TargetModel


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
