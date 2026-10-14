import enum


class LoginFailureReason(enum.StrEnum):
    """Причини відмови в автентифікації користувача (LoginFailedEvent)."""

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"


class TokenRefreshFailureReason(enum.StrEnum):
    """Причини відмови в ротації refresh-токена (TokenRefreshFailedEvent)."""

    TOKEN_NOT_FOUND = "TOKEN_NOT_FOUND"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"


class AuthOperationStatus(enum.StrEnum):
    """Статуси виконання сервісних або RPC операцій автентифікації."""

    OK = "ok"
    REFRESHED = "refreshed"
    LOGGED_OUT = "logged_out"
