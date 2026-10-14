from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.auth.domain.enums import AuthOperationStatus


class LoginDTO(BaseModel):
    """DTO входу за логіном та паролем."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str,
        Field(
            description="Логін користувача (системний username)",
            min_length=3,
            max_length=50,
            examples=["ivan.ivanov"],
        ),
    ]
    password: Annotated[
        str,
        Field(
            description="Пароль користувача",
            min_length=8,
            max_length=128,
            examples=["StrongP@ssw0rd!"],
        ),
    ]
    is_remember_me: Annotated[
        bool,
        Field(
            default=False,
            description="Прапорець довготривалої сесії (до 7-30 днів замість сесійного cookie)",
        ),
    ] = False

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        """Нормалізація логіна: обрізання пробілів та приведення до нижнього регістру."""
        return v.strip().lower()


class RefreshTokenDTO(BaseModel):
    """DTO запиту на оновлення токенів за активним refresh_token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: Annotated[
        str,
        Field(
            description="Криптографічний рядок сесійного refresh-токена",
            min_length=32,
            max_length=128,
        ),
    ]


class LogoutDTO(BaseModel):
    """DTO виходу з системи та анулювання сесії."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: Annotated[
        str | None,
        Field(
            default=None,
            description="Криптографічний рядок сесійного refresh-токена для анулювання",
            min_length=32,
            max_length=128,
        ),
    ] = None


class AuthResultDTO(BaseModel):
    """Внутрішній DTO результату автентифікації/ротації для встановлення Cookies."""

    model_config = ConfigDict(extra="forbid")

    access_token: Annotated[str, Field(description="JWT токен доступу")]
    refresh_token: Annotated[str, Field(description="Opaque сесійний токен")]
    user_id: Annotated[UUID, Field(description="ID автентифікованого користувача")]
    is_remember_me: Annotated[bool, Field(description="Прапорець довготривалої сесії")]


class StatusResponseDTO(BaseModel):
    """Типізована відповідь для сервісних або RPC операцій (auth, logout, refresh)."""

    model_config = ConfigDict(extra="forbid")

    status: Annotated[
        AuthOperationStatus | str,
        Field(
            description="Статус виконання операції",
            examples=["ok", "refreshed", "logged_out"],
        ),
    ]
