"""Standardize system roles to user, admin, super_admin.

Revision ID: 2026_09_04_0003
Revises: 2026_09_04_0002
Create Date: 2026-09-04 02:00:00.000000

"""
from collections.abc import Sequence
from uuid6 import uuid7
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2026_09_04_0003"
down_revision: str | None = "2026_09_04_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_PERMISSIONS = (
    "users:self_update",
    "users:self_password_update",
    "users:self_username_update",
    "users:read_short",
    "targets:read",
    "reviews:read",
    "reviews:create",
    "reviews:vote",
    "reviews:update",
    "reviews:delete",
)

ADMIN_EXTRA_PERMISSIONS = (
    "targets:create",
    "targets:update",
    "targets:delete",
    "reviews:moderate",
    "users:read",
    "users:update",
    "users:deactivate",
    "users:restore",
    "roles:read",
    "permissions:read",
)


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Перейменування ролі viewer на user
    connection.execute(
        sa.text(
            "UPDATE roles "
            "SET code = 'user', name = 'Користувач', "
            "    description = 'Базова роль зареєстрованого користувача' "
            "WHERE code = 'viewer'"
        )
    )

    # 2. Створення або отримання ролі admin
    res = connection.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'"))
    admin_row = res.first()
    if admin_row is None:
        admin_role_id = uuid7()
        connection.execute(
            sa.text(
                "INSERT INTO roles (id, code, name, description, version, created_at) "
                "VALUES (:id, 'admin', 'Адміністратор', "
                "'Адміністратор платформи: модерація відгуків, управління таргетами та користувачами', 1, now())"
            ),
            {"id": admin_role_id},
        )
    else:
        admin_role_id = admin_row[0]

    # 3. Отримання ID ролей
    res_roles = connection.execute(sa.text("SELECT id, code FROM roles WHERE code IN ('user', 'admin', 'super_admin')"))
    roles_map = {row.code: row.id for row in res_roles}
    user_role_id = roles_map.get("user")
    admin_role_id = roles_map.get("admin")
    super_admin_role_id = roles_map.get("super_admin")

    # 4. Отримання словника дозволів {code: id}
    res_perms = connection.execute(sa.text("SELECT id, code FROM permissions"))
    perms_map = {row.code: row.id for row in res_perms}

    # 5. Оновлення прав для ролі user
    if user_role_id:
        for perm_code in USER_PERMISSIONS:
            perm_id = perms_map.get(perm_code)
            if perm_id:
                connection.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id) "
                        "VALUES (:role_id, :permission_id) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role_id": user_role_id, "permission_id": perm_id},
                )

    # 6. Оновлення прав для ролі admin (права user + адмінські права)
    if admin_role_id:
        all_admin_perms = set(USER_PERMISSIONS) | set(ADMIN_EXTRA_PERMISSIONS)
        for perm_code in all_admin_perms:
            perm_id = perms_map.get(perm_code)
            if perm_id:
                connection.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id) "
                        "VALUES (:role_id, :permission_id) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role_id": admin_role_id, "permission_id": perm_id},
                )

    # 7. Гарантія 100% усіх прав для super_admin
    if super_admin_role_id:
        for perm_id in perms_map.values():
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"role_id": super_admin_role_id, "permission_id": perm_id},
            )


def downgrade() -> None:
    connection = op.get_bind()

    # Очищення ролі admin
    connection.execute(sa.text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code = 'admin')"))
    connection.execute(sa.text("DELETE FROM roles WHERE code = 'admin'"))

    # Повернення ролі user назад у viewer
    connection.execute(
        sa.text(
            "UPDATE roles "
            "SET code = 'viewer', name = 'Глядач', "
            "    description = 'Базова роль: перегляд інформації без права внесення змін (Read-only)' "
            "WHERE code = 'user'"
        )
    )
