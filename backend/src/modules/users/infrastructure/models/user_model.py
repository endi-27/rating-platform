from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db import (
    Base,
    CreatedByMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.users.infrastructure.models.permission_model import PermissionModel
from src.modules.users.infrastructure.models.role_model import RoleModel

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.user_permission_model import UserPermissionModel


class UserModel(
    Base,
    UUIDPrimaryKeyMixin,
    SoftDeleteMixin,
    TimestampMixin,
    VersionedMixin,
    CreatedByMixin,
):
    """ORM модель користувача платформи (Aggregate Root)."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Зв'язки з обов'язковим lazy="raise" та явним foreign_keys
    role: Mapped[RoleModel] = relationship(
        back_populates="users",
        foreign_keys=[role_id],
        lazy="raise",
    )
    user_permissions: Mapped[list["UserPermissionModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    custom_permissions: Mapped[list[PermissionModel]] = relationship(
        secondary="user_permissions",
        back_populates="users",
        lazy="raise",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_users_role_id", "role_id"),
        Index("ix_users_deleted_at_role_id", "deleted_at", "role_id"),
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_username_lower", func.lower(username), unique=True),
        Index(
            "ix_users_name_username_trgm",
            "name",
            "username",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops", "username": "gin_trgm_ops"},
        ),
    )
