from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeletionAction(StrEnum):
    """Тип дії при оцінці видалення ресурсу."""

    HARD_DELETE = "hard_delete"
    DEACTIVATE = "deactivate"
    BLOCKED = "blocked"


class DeletionRelationDTO(BaseModel):
    """Інформація про залежні сутності, що блокують або впливають на видалення."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: Annotated[str, Field(description="Тип залежної сутності (наприклад, 'users', 'orders')")]
    count: Annotated[int, Field(ge=0, description="Кількість зв'язаних записів")]


class DeletionRestrictionDTO(BaseModel):
    """Опис обмеження, що блокує видалення сутності."""

    model_config = ConfigDict(from_attributes=True)

    code: Annotated[str, Field(description="Машиночитний код обмеження")]
    message: Annotated[str, Field(description="Зрозуміле повідомлення про причину блокування")]


class DeletionAssessmentDTO(BaseModel):
    """Загальносистемна схема попередньої оцінки видалення (delete-preview)."""

    model_config = ConfigDict(from_attributes=True)

    resource_id: Annotated[UUID, Field(description="Ідентифікатор ресурсу")]
    action: Annotated[DeletionAction, Field(description="Дозволена або рекомендована дія")]
    dependencies: list[DeletionRelationDTO] = Field(
        default_factory=list,
        description="Список знайдених залежностей",
    )
    restriction: Annotated[DeletionRestrictionDTO | None, Field(description="Обмеження або причина блокування")] = None
