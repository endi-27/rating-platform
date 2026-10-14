from uuid import UUID

from src.core.events import BaseEvent


class UserCreatedEvent(BaseEvent):
    """Подія створення нового користувача."""

    username: str
    role_id: UUID


class UserUpdatedEvent(BaseEvent):
    """Подія оновлення даних користувача."""

    username: str
    role_id: UUID


class UserPasswordChangedEvent(BaseEvent):
    """Подія зміни пароля користувача (вимагає інвалідації сесій)."""

    username: str


class UserDeactivatedEvent(BaseEvent):
    """Подія деактивації (м'якого видалення) користувача."""

    username: str


class UserRestoredEvent(BaseEvent):
    """Подія відновлення користувача."""

    username: str


class UserDeletedEvent(BaseEvent):
    """Подія остаточного фізичного видалення користувача."""

    username: str


class RoleCreatedEvent(BaseEvent):
    """Подія створення нової ролі."""

    code: str
    name: str


class RoleUpdatedEvent(BaseEvent):
    """Подія оновлення ролі або її прав."""

    code: str
    name: str


class RoleDeactivatedEvent(BaseEvent):
    """Подія деактивації ролі."""

    code: str


class RoleRestoredEvent(BaseEvent):
    """Подія відновлення ролі."""

    code: str


class RoleDeletedEvent(BaseEvent):
    """Подія остаточного видалення ролі."""

    code: str


class UserUsernameChangedEvent(BaseEvent):
    """Подія зміни логіна (username) користувача (вимагає перелогіну та розриву SSE)."""

    old_username: str
    new_username: str


class UserCredentialsChangedEvent(BaseEvent):
    """Подія зміни облікових даних, ролі або прав користувача адміністратором."""

    username: str
    role_id: UUID
