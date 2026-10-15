from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.modules.reviews.infrastructure.models.review_model import ReviewModel


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
