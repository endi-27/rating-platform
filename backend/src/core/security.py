import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import bcrypt
import jwt
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import get_settings, settings
from src.core.enums import SystemRole
from src.core.protocols import IPasswordHasher


class CurrentUserRole(BaseModel):
    """Скорочене представлення ролі користувача в контексті сесії."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    code: str
    name: str


class CurrentUser(BaseModel):
    """Контекст поточного автентифікованого користувача (Security Principal)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    username: str
    name: str
    role_id: UUID
    role: CurrentUserRole | None = None
    effective_permissions: Annotated[
        frozenset[str],
        Field(description="Розраховані ефективні права"),
    ] = Field(default_factory=frozenset)
    created_at: datetime
    updated_at: datetime | None = None

    @property
    def is_super_admin(self) -> bool:
        """Прапорець супер-адміністратора платформи."""
        return bool(self.role and self.role.code == SystemRole.SUPER_ADMIN)


def generate_opaque_token(nbytes: int = 32) -> str:
    """Генерація криптографічно стійкого непрозорого токена (для refresh токенів або скидання паролю)."""
    return secrets.token_hex(nbytes)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Генерація короткоживучого JWT access токена з клеймами exp та iat."""
    now = datetime.now(UTC)
    to_encode = data.copy()
    expire = now + (expires_delta or timedelta(minutes=settings.auth.access_token_expire_minutes))
    to_encode.update({"iat": now, "exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.auth.access_secret_key, algorithm=settings.auth.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Декодування та перевірка валідності JWT токена."""
    return jwt.decode(
        token,
        settings.auth.access_secret_key,
        algorithms=[settings.auth.algorithm],
    )


class BcryptPasswordHasher:
    """Реалізація IPasswordHasher на базі бібліотеки bcrypt."""

    def __init__(self, default_rounds: int | None = None) -> None:
        self._default_rounds = default_rounds

    def hash(self, password: str, rounds: int | None = None) -> str:
        """Хешування пароля за допомогою bcrypt."""
        cost = rounds if rounds is not None else (self._default_rounds or get_settings().auth.bcrypt_rounds)
        salt = bcrypt.gensalt(rounds=cost)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Перевірка відповідності відкритого пароля збереженому хешу."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False


default_password_hasher: IPasswordHasher = BcryptPasswordHasher()
