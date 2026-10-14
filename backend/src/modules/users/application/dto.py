from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.api import OCCVersionDTO
from src.utils import deduplicate_preserve_order, normalize_human_name, normalize_spaces

# --- Користувачі (Users) ---


class UserCredentialsDTO(BaseModel):
    """Публічний DTO облікових даних користувача для автентифікації та перевірки прав."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        from_attributes=True,
    )

    id: Annotated[UUID, Field(description="Унікальний ідентифікатор користувача")]
    username: Annotated[str, Field(description="Логін користувача")]
    password_hash: Annotated[str, Field(description="Хеш пароля (bcrypt)")]
    role_code: Annotated[str, Field(description="Системний код ролі")]
    is_active: Annotated[bool, Field(description="Статус активності облікового запису")]


class CreateUserDTO(BaseModel):
    """Контракт створення нового користувача."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=50,
            pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$",
            description="Логін користувача (латиниця, цифри, дефіс, крапка, підкреслення)",
            examples=["ivan.ivanov"],
        ),
    ]
    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="ПІБ або ім'я користувача",
            examples=["Іван Іванов"],
        ),
    ]
    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=128,
            description="Пароль",
            examples=["StrongP@ssw0rd!"],
        ),
    ]
    role_id: Annotated[UUID, Field(description="ID призначеної ролі")]
    custom_permission_ids: Annotated[
        list[UUID] | None,
        Field(description="Персональні права"),
    ] = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return normalize_human_name(v)

    @field_validator("custom_permission_ids", mode="after")
    @classmethod
    def deduplicate_permissions(cls, v: list[UUID] | None) -> list[UUID] | None:
        return deduplicate_preserve_order(v)


class UpdateUserDTO(OCCVersionDTO):
    """Контракт повного оновлення профілю користувача (Full PUT)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=50,
            pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$",
            description="Логін користувача (латиниця, цифри, дефіс, крапка, підкреслення)",
            examples=["ivan.ivanov"],
        ),
    ]
    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="ПІБ або ім'я користувача",
            examples=["Іван Іванов"],
        ),
    ]
    role_id: Annotated[UUID, Field(description="ID призначеної ролі")]
    custom_permission_ids: Annotated[
        list[UUID] | None,
        Field(description="Персональні права"),
    ] = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return normalize_human_name(v)

    @field_validator("custom_permission_ids", mode="after")
    @classmethod
    def deduplicate_permissions(cls, v: list[UUID] | None) -> list[UUID] | None:
        return deduplicate_preserve_order(v)


class UpdateSelfProfileDTO(OCCVersionDTO):
    """Контракт оновлення власного профілю поточним користувачем."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="ПІБ або ім'я користувача",
            examples=["Іван Іванов"],
        ),
    ]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return normalize_human_name(v)


class ChangeSelfPasswordDTO(BaseModel):
    """Контракт зміни власного пароля користувачем."""

    model_config = ConfigDict(extra="forbid")

    old_password: Annotated[
        str,
        Field(
            description="Поточний діючий пароль",
            min_length=8,
            max_length=128,
            examples=["OldP@ssw0rd1!"],
        ),
    ]
    new_password: Annotated[
        str,
        Field(
            description="Новий надійний пароль",
            min_length=8,
            max_length=128,
            examples=["NewStrongP@ssw0rd2!"],
        ),
    ]

    @model_validator(mode="after")
    def verify_passwords_differ(self) -> Self:
        """Заборона зміни пароля на такий самий поточний пароль."""
        if self.old_password == self.new_password:
            raise ValueError("Новий пароль не може збігатися з поточним паролем.")
        return self


class ChangeSelfUsernameDTO(OCCVersionDTO):
    """Контракт зміни власного логіна користувачем."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    current_password: Annotated[
        str,
        Field(
            description="Поточний діючий пароль для підтвердження особи",
            min_length=8,
            max_length=128,
            examples=["CurrentP@ssw0rd!"],
        ),
    ]
    new_username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=50,
            pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$",
            description="Новий логін користувача (латиниця, цифри, дефіс, крапка, підкреслення)",
            examples=["ivan.new"],
        ),
    ]

    @field_validator("new_username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.lower()


class ResetUserPasswordDTO(BaseModel):
    """Контракт примусового скидання пароля користувача адміністратором."""

    model_config = ConfigDict(extra="forbid")

    new_password: Annotated[
        str,
        Field(
            description="Новий надійний пароль користувача",
            min_length=8,
            max_length=128,
            examples=["NewStrongP@ssw0rd2!"],
        ),
    ]


class UserActionStatusDTO(BaseModel):
    """Контракт успішної відповіді на дію над користувачем."""

    model_config = ConfigDict(extra="forbid")

    status: Annotated[
        Literal["password_changed", "username_changed", "password_reset"],
        Field(description="Статус виконання дії", examples=["password_changed"]),
    ]


class SoftDeleteUserDTO(OCCVersionDTO):
    """DTO деактивації користувача."""


class RestoreUserDTO(OCCVersionDTO):
    """DTO відновлення користувача."""


# --- Ролі (Roles) ---


class CreateRoleDTO(BaseModel):
    """Контракт створення нової ролі."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            pattern=r"^[a-zA-Z0-9]+(?:_[a-zA-Z0-9]+)*$",
            description="Унікальний код ролі у форматі snake_case",
            examples=["operator"],
        ),
    ]
    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="Назва ролі",
            examples=["Оператор лінії"],
        ),
    ]
    description: Annotated[
        str | None,
        Field(max_length=255, description="Опис ролі", examples=["Працівник зміни"]),
    ] = None
    permission_ids: Annotated[
        list[UUID] | None,
        Field(description="Список ID дозволів"),
    ] = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return normalize_spaces(v)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_spaces(v)

    @field_validator("permission_ids", mode="after")
    @classmethod
    def deduplicate_permissions(cls, v: list[UUID] | None) -> list[UUID] | None:
        return deduplicate_preserve_order(v)


class UpdateRoleDTO(OCCVersionDTO):
    """Контракт повного оновлення ролі (Full PUT)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="Назва ролі",
            examples=["Старший оператор"],
        ),
    ]
    description: Annotated[
        str | None,
        Field(max_length=255, description="Опис ролі", examples=["Бригадир зміни"]),
    ] = None
    permission_ids: Annotated[
        list[UUID],
        Field(description="Повний список ID дозволів ролі (Full PUT)", examples=[[]]),
    ]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return normalize_spaces(v)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_spaces(v)

    @field_validator("permission_ids", mode="after")
    @classmethod
    def deduplicate_permissions(cls, v: list[UUID]) -> list[UUID]:
        return deduplicate_preserve_order(v) or []


class SoftDeleteRoleDTO(OCCVersionDTO):
    """DTO деактивації ролі."""


class RestoreRoleDTO(OCCVersionDTO):
    """DTO відновлення ролі."""
