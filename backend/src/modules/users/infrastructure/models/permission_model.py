from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.role_model import RoleModel
    from src.modules.users.infrastructure.models.role_permission_model import RolePermissionModel
    from src.modules.users.infrastructure.models.user_model import UserModel
    from src.modules.users.infrastructure.models.user_permission_model import UserPermissionModel


class PermissionModel(Base, UUIDPrimaryKeyMixin):
    """ORM модель системного дозволу (Read-Only / Aggregate Root)."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Зв'язки з обов'язковим lazy="raise"
    roles: Mapped[list["RoleModel"]] = relationship(
        secondary="role_permissions",
        back_populates="permissions",
        lazy="raise",
        viewonly=True,
    )
    role_permissions: Mapped[list["RolePermissionModel"]] = relationship(
        back_populates="permission",
        lazy="raise",
    )
    users: Mapped[list["UserModel"]] = relationship(
        secondary="user_permissions",
        back_populates="custom_permissions",
        lazy="raise",
        viewonly=True,
    )
    user_permissions: Mapped[list["UserPermissionModel"]] = relationship(
        back_populates="permission",
        lazy="raise",
    )
