from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core import PermissionCode


class PermissionResponseDTO(BaseModel):
    """Детальна інформація про системний дозвіл."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: PermissionCode
    name: str
    description: str | None = None
    created_at: datetime


class RoleShortResponseDTO(BaseModel):
    """Скорочене представлення ролі для вкладених відповідей."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class RoleResponseDTO(BaseModel):
    """Базове представлення ролі користувача."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    code: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class RoleDetailDTO(RoleResponseDTO):
    """Детальне представлення ролі разом зі списком дозволів."""

    permissions: Annotated[
        list[PermissionResponseDTO],
        Field(description="Список дозволів ролі"),
    ] = Field(default_factory=list)


class UserShortDTO(BaseModel):
    """Скорочене представлення користувача для селектів та швидких списків."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    name: str


class UserResponseDTO(BaseModel):
    """Базове представлення користувача у списку."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    username: str
    name: str
    role_id: UUID
    role: RoleShortResponseDTO | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class UserDetailDTO(UserResponseDTO):
    """Детальне представлення користувача з розрахунком прав."""

    custom_permissions: Annotated[
        list[PermissionResponseDTO],
        Field(description="Список персональних дозволів користувача"),
    ] = Field(default_factory=list)
    effective_permissions: Annotated[
        set[str],
        Field(description="Розраховані ефективні права"),
    ] = Field(default_factory=set)
