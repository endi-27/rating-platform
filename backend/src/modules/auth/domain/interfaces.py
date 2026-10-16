from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from src.core import CurrentUser
from src.modules.auth.domain.models import RefreshToken, RevokedTokenDTO

if TYPE_CHECKING:
    from src.core import IUnitOfWork


class IUserCredentials(Protocol):
    """Мінімальний протокол облікових даних користувача для перевірки автентифікації."""

    @property
    def id(self) -> UUID: ...

    @property
    def username(self) -> str: ...

    @property
    def password_hash(self) -> str: ...

    @property
    def role_code(self) -> str: ...

    @property
    def is_active(self) -> bool: ...


class IRefreshTokenRepository(Protocol):
    """Протокол репозиторію сесійних refresh-токенів."""

    async def create(self, refresh_token: RefreshToken) -> None:
        """Створення нового запису токена."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Пошук токена за його SHA-256 хешем (з блокуванням SELECT FOR UPDATE)."""
        ...

    async def save(self, refresh_token: RefreshToken) -> None:
        """Оновлення стану токена (анулювання, оновлення дати)."""
        ...

    async def bulk_revoke_for_users(self, user_ids: set[UUID]) -> list[RevokedTokenDTO]:
        """Масове або поодиноке відкликання токенів для списку користувачів."""
        ...

    async def delete_expired_before(self, cutoff: datetime, limit: int | None = None) -> int:
        """
        Фізичне видалення протермінованих токенів, строк дії яких вичерпано до cutoff
        (з опціональним лімітом розміру порції).
        """
        ...


class IUserAuthGateway(Protocol):
    """Протокол шлюзу до модуля Users для перевірки креденшалів."""

    async def get_credentials_by_username(self, username: str) -> IUserCredentials | None:
        """Отримання облікових даних (credentials) користувача за логіном."""
        ...

    async def get_credentials_by_id(self, user_id: UUID) -> IUserCredentials | None:
        """Отримання облікових даних (credentials) користувача за ID."""
        ...

    async def get_cached_current_user(self, user_id: UUID) -> CurrentUser | None:
        """Отримання кешованих даних профілю користувача з ефективними правами."""
        ...

    async def register_public_user(
        self,
        username: str,
        name: str,
        password: str,
        *,
        external_uow: IUnitOfWork | None = None,
    ) -> IUserCredentials:
        """Публічна реєстрація користувача з роллю за замовчуванням 'user'."""
        ...
