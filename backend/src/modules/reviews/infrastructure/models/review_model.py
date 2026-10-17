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
    text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.reviews.domain.enums import ReviewStatus

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
    status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(
            ReviewStatus,
            native_enum=False,
            length=20,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        server_default=ReviewStatus.PUBLISHED.value,
        default=ReviewStatus.PUBLISHED,
        nullable=False,
    )
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unhelpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Зв'язки
    target: Mapped["TargetModel"] = relationship("TargetModel", back_populates="reviews", lazy="raise")
    votes: Mapped[list["ReviewVoteModel"]] = relationship(
        "ReviewVoteModel",
        back_populates="review",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    __table_args__ = (
        Index(
            "uq_reviews_target_user_active",
            "target_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_reviews_score_range"),
        CheckConstraint("status IN ('published', 'hidden', 'flagged')", name="ck_reviews_status"),
        Index("ix_reviews_target_status_created", "target_id", "status", "created_at"),
    )
