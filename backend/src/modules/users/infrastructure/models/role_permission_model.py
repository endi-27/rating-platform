from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db import Base

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.permission_model import PermissionModel
    from src.modules.users.infrastructure.models.role_model import RoleModel


class RolePermissionModel(Base):
    """ORM модель зв'язку роль <-> дозвіл (Association Object Pattern)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Зв'язки з обов'язковим lazy="raise"
    role: Mapped["RoleModel"] = relationship(
        back_populates="role_permissions",
        lazy="raise",
    )
    permission: Mapped["PermissionModel"] = relationship(
        back_populates="role_permissions",
        lazy="raise",
    )

    __table_args__ = (Index("ix_role_permissions_permission_id", "permission_id"),)
