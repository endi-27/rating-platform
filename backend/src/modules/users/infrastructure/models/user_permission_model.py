from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db import Base

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.permission_model import PermissionModel
    from src.modules.users.infrastructure.models.user_model import UserModel


class UserPermissionModel(Base):
    """ORM модель зв'язку користувач <-> персональний дозвіл (Association Object Pattern)."""

    __tablename__ = "user_permissions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Зв'язки з обов'язковим lazy="raise"
    user: Mapped["UserModel"] = relationship(
        back_populates="user_permissions",
        lazy="raise",
    )
    permission: Mapped["PermissionModel"] = relationship(
        back_populates="user_permissions",
        lazy="raise",
    )

    __table_args__ = (Index("ix_user_permissions_permission_id", "permission_id"),)
