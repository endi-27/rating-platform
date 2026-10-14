import enum


class PermissionCode(enum.StrEnum):
    """Єдиний реєстр системних дозволів платформи (RBAC/PBAC)."""

    # Користувачі (Users)
    USERS_READ = "users:read"
    USERS_READ_SHORT = "users:read_short"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_PASSWORD_UPDATE = "users:password_update"
    USERS_DELETE = "users:delete"
    USERS_DEACTIVATE = "users:deactivate"
    USERS_RESTORE = "users:restore"
    USERS_SELF_UPDATE = "users:self_update"
    USERS_SELF_PASSWORD_UPDATE = "users:self_password_update"
    USERS_SELF_USERNAME_UPDATE = "users:self_username_update"

    # Ролі (Roles)
    ROLES_READ = "roles:read"
    ROLES_CREATE = "roles:create"
    ROLES_UPDATE = "roles:update"
    ROLES_DELETE = "roles:delete"
    ROLES_DEACTIVATE = "roles:deactivate"
    ROLES_RESTORE = "roles:restore"

    # Дозволи (Permissions)
    PERMISSIONS_READ = "permissions:read"
