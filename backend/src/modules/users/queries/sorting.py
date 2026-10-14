from enum import StrEnum


class PermissionSortField(StrEnum):
    """Дозволені поля для сортування списку дозволів."""

    CODE = "code"
    NAME = "name"
    CREATED_AT = "created_at"


class RoleSortField(StrEnum):
    """Дозволені поля для сортування списку ролей."""

    CREATED_AT = "created_at"
    NAME = "name"
    CODE = "code"
    UPDATED_AT = "updated_at"


class UserSortField(StrEnum):
    """Дозволені поля для сортування детального списку користувачів."""

    CREATED_AT = "created_at"
    USERNAME = "username"
    NAME = "name"
    UPDATED_AT = "updated_at"


class UserShortSortField(StrEnum):
    """Дозволені поля для сортування скороченого списку користувачів."""

    USERNAME = "username"
    NAME = "name"
