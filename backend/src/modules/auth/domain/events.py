from uuid import UUID

from src.core.events import BaseEvent
from src.modules.auth.domain.enums import LoginFailureReason, TokenRefreshFailureReason


class UserLoggedOutEvent(BaseEvent):
    """Подія виходу користувача із системи (Logout)."""

    session_id: UUID | None = None
    username: str | None = None
    ip_address: str | None = None


class UserLoggedInEvent(BaseEvent):
    """Подія успішної автентифікації користувача (для витіснення старих сесій / single session)."""

    username: str | None = None
    ip_address: str | None = None


class LoginFailedEvent(BaseEvent):
    """Подія невдалої спроби автентифікації користувача."""

    username: str
    reason: LoginFailureReason
    ip_address: str | None = None


class TokenRefreshFailedEvent(BaseEvent):
    """Подія невдалої спроби ротації сесійного refresh-токена."""

    reason: TokenRefreshFailureReason
    username: str | None = None
    ip_address: str | None = None


class TokenCompromisedEvent(BaseEvent):
    """Подія виявлення компрометації токена (RFC 6819 Token Reuse Detection)."""

    username: str | None = None
    ip_address: str | None = None


class SessionExpiredEvent(BaseEvent):
    """Подія закінчення максимального терміну дії сесії (max_session_expiration)."""

    username: str | None = None
    ip_address: str | None = None
