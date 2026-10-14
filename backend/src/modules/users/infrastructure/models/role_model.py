from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db import (
    Base,
    CreatedByMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.permission_model import PermissionModel
    from src.modules.users.infrastructure.models.role_permission_model import RolePermissionModel
    from src.modules.users.infrastructure.models.user_model import UserModel


class RoleModel(
    Base,
    UUIDPrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
    VersionedMixin,
    CreatedByMixin,
):
    """ORM модель ролі користувача (Aggregate Root)."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Зв'язки з обов'язковим lazy="raise"
    role_permissions: Mapped[list["RolePermissionModel"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    permissions: Mapped[list["PermissionModel"]] = relationship(
        secondary="role_permissions",
        back_populates="roles",
        lazy="raise",
        viewonly=True,
    )
    users: Mapped[list["UserModel"]] = relationship(
        back_populates="role",
        foreign_keys="UserModel.role_id",
        lazy="raise",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_roles_deleted_at", "deleted_at"),)
