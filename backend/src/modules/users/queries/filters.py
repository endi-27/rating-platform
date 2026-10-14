from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class UserFilterDTO(BaseModel):
    """Параметри фільтрації списку користувачів."""

    ids: Annotated[set[UUID] | None, Field(description="Фільтр за списком ID")] = None
    role_ids: Annotated[set[UUID] | None, Field(description="Фільтр за списком ID ролей")] = None
    roles: Annotated[set[str] | None, Field(description="Фільтр за кодами ролей")] = None
    search: Annotated[str | None, Field(description="Пошуковий рядок (username або name)")] = None
    min_created_at: Annotated[date | None, Field(description="Початкова дата створення")] = None
    max_created_at: Annotated[date | None, Field(description="Кінцева дата створення")] = None
    include_inactive: Annotated[bool, Field(description="Включити деактивованих користувачів")] = False
    exclude_user_id: Annotated[UUID | None, Field(description="ID користувача для виключення з результатів")] = None

    @model_validator(mode="after")
    def validate_date_ranges(self) -> "UserFilterDTO":
        if self.min_created_at and self.max_created_at and self.min_created_at > self.max_created_at:
            raise ValueError("min_created_at не може бути пізніше за max_created_at")
        return self


class RoleFilterDTO(BaseModel):
    """Параметри фільтрації списку ролей."""

    ids: Annotated[set[UUID] | None, Field(description="Фільтр за списком ID")] = None
    codes: Annotated[set[str] | None, Field(description="Фільтр за списком кодів")] = None
    search: Annotated[str | None, Field(description="Пошуковий рядок (name)")] = None
    include_inactive: Annotated[bool, Field(description="Включити деактивовані ролі")] = False


class PermissionFilterDTO(BaseModel):
    """Параметри фільтрації списку дозволів."""

    ids: Annotated[set[UUID] | None, Field(description="Фільтр за списком ID")] = None
    codes: Annotated[set[str] | None, Field(description="Фільтр за списком кодів")] = None
    search: Annotated[str | None, Field(description="Пошуковий рядок (name)")] = None
