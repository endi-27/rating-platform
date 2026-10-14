from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from uuid6 import uuid7

from src.utils import ensure_utc_datetime


@dataclass(frozen=True)
class RevokedTokenDTO:
    """DTO відкликаного сесійного токена для фіксації аудиту при масових операціях."""

    id: UUID
    user_id: UUID


@dataclass
class RefreshToken:
    """Доменна сутність сесійного refresh-токена (Rich Domain Model)."""

    id: UUID
    user_id: UUID
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    max_session_expiration: datetime
    is_revoked: bool = False
    is_remember_me: bool = False

    def __post_init__(self) -> None:
        if not self.token_hash or not self.token_hash.strip():
            raise ValueError("Хеш токена (token_hash) не може бути порожнім.")

        self.issued_at = ensure_utc_datetime(self.issued_at)
        self.expires_at = ensure_utc_datetime(self.expires_at)
        self.max_session_expiration = ensure_utc_datetime(self.max_session_expiration)

        if self.expires_at < self.issued_at:
            raise ValueError("Дата завершення дії токена (expires_at) не може бути меншою за дату видачі (issued_at).")
        if self.max_session_expiration < self.issued_at:
            raise ValueError(
                "Абсолютний ліміт сесії (max_session_expiration) не може бути меншим за дату видачі (issued_at)."
            )

    @classmethod
    def create(
        cls,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        max_session_expiration: datetime,
        is_remember_me: bool = False,
        issued_at: datetime | None = None,
        token_id: UUID | None = None,
    ) -> "RefreshToken":
        """
        Фабричний метод створення нового сесійного токена.
        Генерує часово-впорядкований UUIDv7 та фіксує поточний UTC час видачі.
        """
        now = ensure_utc_datetime(issued_at) if issued_at is not None else datetime.now(UTC)
        return cls(
            id=token_id or uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            issued_at=now,
            expires_at=expires_at,
            max_session_expiration=max_session_expiration,
            is_revoked=False,
            is_remember_me=is_remember_me,
        )

    def rotate(
        self,
        new_token_hash: str,
        new_expires_at: datetime,
        rotated_at: datetime | None = None,
    ) -> "RefreshToken":
        """
        Ротація refresh-токена:
        - Поточний токен обов'язково анулюється (is_revoked = True).
        - Новий токен успадковує абсолютний ліміт сесії (max_session_expiration).
        - Термін дії нового токена обмежується абсолютним лімітом (min(new_expires_at, max_session_expiration)).
        - Новий токен успадковує прапорець is_remember_me.
        """
        now = ensure_utc_datetime(rotated_at) if rotated_at is not None else datetime.now(UTC)
        norm_new_expires = ensure_utc_datetime(new_expires_at)
        effective_expires_at = min(norm_new_expires, self.max_session_expiration)

        self.revoke()
        return RefreshToken(
            id=uuid7(),
            user_id=self.user_id,
            token_hash=new_token_hash,
            issued_at=now,
            expires_at=effective_expires_at,
            max_session_expiration=self.max_session_expiration,
            is_revoked=False,
            is_remember_me=self.is_remember_me,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        """Перевіряє чи сплив ковзний термін дії токена (expires_at)."""
        current_time = ensure_utc_datetime(now) if now is not None else datetime.now(UTC)
        return current_time > self.expires_at

    def is_session_expired(self, now: datetime | None = None) -> bool:
        """Перевіряє чи вичерпано абсолютний ліміт тривалості сесії (max_session_expiration)."""
        current_time = ensure_utc_datetime(now) if now is not None else datetime.now(UTC)
        return current_time > self.max_session_expiration

    def is_valid(self, now: datetime | None = None) -> bool:
        """Перевіряє чи є токен активним (не анульований, не протермінований і в межах сесії)."""
        current_time = ensure_utc_datetime(now) if now is not None else datetime.now(UTC)
        return not self.is_revoked and not self.is_expired(current_time) and not self.is_session_expired(current_time)

    def revoke(self) -> None:
        """Анулювання токена."""
        self.is_revoked = True
