from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OCCVersionDTO(BaseModel):
    """Базовий контракт для PATCH та RPC операцій, що вимагають валідації версії (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(
            ge=1,
            description="Поточна версія запису для оптимістичного блокування (OCC)",
            examples=[1],
        ),
    ]
