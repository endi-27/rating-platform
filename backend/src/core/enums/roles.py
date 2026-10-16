import enum


class SystemRole(enum.StrEnum):
    """Системні ролі платформи рейтингів та відгуків."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


RoleCode = SystemRole
