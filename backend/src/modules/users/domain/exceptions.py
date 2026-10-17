from src.core import (
    ConflictException,
    DomainException,
    ForbiddenException,
    NotFoundException,
    ProtectedResourceException,
    UserAlreadyExistsException,
)


class UserNotFoundError(NotFoundException):
    """Користувача не знайдено."""

    default_error_code: str = "USER_NOT_FOUND"
    default_message: str = "Користувача не знайдено."


class RoleNotFoundError(NotFoundException):
    """Роль не знайдено."""

    default_error_code: str = "ROLE_NOT_FOUND"
    default_message: str = "Роль не знайдено."


class PermissionNotFoundError(NotFoundException):
    """Право доступу не знайдено."""

    default_error_code: str = "PERMISSION_NOT_FOUND"
    default_message: str = "Право доступу не знайдено."


class UserAlreadyExistsError(UserAlreadyExistsException):
    """Користувач із таким логіном вже існує."""


class RoleAlreadyExistsError(ConflictException):
    """Роль із таким кодом вже існує."""

    default_error_code: str = "ROLE_ALREADY_EXISTS"
    default_message: str = "Роль із таким кодом вже існує."


class SuperAdminProtectionError(ProtectedResourceException):
    """Помилка спроби модифікації або видалення системного SuperAdmin."""

    default_error_code: str = "SUPER_ADMIN_PROTECTED"
    default_message: str = "Системну роль або обліковий запис SuperAdmin заборонено змінювати чи видаляти."


class SelfActionForbiddenError(ForbiddenException):
    """Помилка спроби виконати дію над власним обліковим записом (наприклад, самовидалення чи самодеактивація)."""

    default_error_code: str = "SELF_ACTION_FORBIDDEN"
    default_message: str = "Ви не можете виконати цю дію над власним обліковим записом."


class InactiveRoleAssignmentError(DomainException):
    """Спроба призначення деактивованої ролі користувачу."""

    default_error_code: str = "INACTIVE_ROLE_ASSIGNMENT"
    default_message: str = "Неможливо призначити користувачу деактивовану роль."


__all__ = [
    "InactiveRoleAssignmentError",
    "PermissionNotFoundError",
    "RoleAlreadyExistsError",
    "RoleNotFoundError",
    "SelfActionForbiddenError",
    "SuperAdminProtectionError",
    "UserAlreadyExistsError",
    "UserAlreadyExistsException",
    "UserNotFoundError",
]
