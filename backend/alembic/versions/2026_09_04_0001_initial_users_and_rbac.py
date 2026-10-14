"""Initial users and RBAC schema for rating-platform.

Revision ID: 2026_09_04_0001
Revises:
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union
from uuid6 import uuid7
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2026_09_04_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = [
    # Users
    ("users:read", "Перегляд користувачів", "Дозвіл на читання списку та детальної інформації користувачів"),
    ("users:read_short", "Короткий перегляд користувачів", "Дозвіл на читання базових даних користувачів"),
    ("users:create", "Створення користувачів", "Дозвіл на створення нових користувачів"),
    ("users:update", "Оновлення користувачів", "Дозвіл на зміну профілю користувачів"),
    ("users:password_update", "Зміна пароля користувачів", "Дозвіл на зміну пароля будь-якого користувача"),
    ("users:delete", "Видалення користувачів", "Дозвіл на видалення користувачів"),
    ("users:deactivate", "Деактивація користувачів", "Дозвіл на деактивацію облікових записів"),
    ("users:restore", "Відновлення користувачів", "Дозвіл на відновлення видалених/деактивованих користувачів"),
    ("users:self_update", "Оновлення власного профілю", "Дозвіл на редагування власних даних"),
    ("users:self_password_update", "Зміна власного пароля", "Дозвіл на зміну власного пароля"),
    ("users:self_username_update", "Зміна власного логіна", "Дозвіл на зміну власного імені користувача"),
    # Roles
    ("roles:read", "Перегляд ролей", "Дозвіл на перегляд переліку та деталізації ролей"),
    ("roles:create", "Створення ролей", "Дозвіл на створення нових ролей"),
    ("roles:update", "Оновлення ролей", "Дозвіл на редагування існуючих ролей"),
    ("roles:delete", "Видалення ролей", "Дозвіл на видалення ролей"),
    ("roles:deactivate", "Деактивація ролей", "Дозвіл на тимчасове відключення ролі"),
    ("roles:restore", "Відновлення ролей", "Дозвіл на відновлення деактивованих ролей"),
    # Permissions
    ("permissions:read", "Перегляд дозволів", "Дозвіл на перегляд каталогу доступних прав"),
]


def upgrade() -> None:
    # 1. Enable pg_trgm extension for full-text / trigram fuzzy searches
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # 2. Table: roles
    roles_table = op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
    )
    op.create_index(op.f("ix_roles_deleted_at"), "roles", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_roles_created_by_id"), "roles", ["created_by_id"], unique=False)

    # 3. Table: permissions
    permissions_table = op.create_table(
        "permissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )

    # 4. Table: role_permissions
    role_permissions_table = op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], name=op.f("fk_role_permissions_permission_id_permissions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_role_permissions_role_id_roles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )
    op.create_index(op.f("ix_role_permissions_permission_id"), "role_permissions", ["permission_id"], unique=False)

    # 5. Table: users
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_users_created_by_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_users_role_id_roles"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_created_by_id"), "users", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"], unique=False)
    op.create_index("ix_users_deleted_at_role_id", "users", ["deleted_at", "role_id"], unique=False)
    op.create_index("ix_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.create_index(
        "ix_users_name_username_trgm",
        "users",
        ["name", "username"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops", "username": "gin_trgm_ops"},
    )

    # 6. Add deferred foreign key from roles.created_by_id -> users.id
    op.create_foreign_key(
        op.f("fk_roles_created_by_id_users"),
        "roles",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 7. Table: user_permissions
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], name=op.f("fk_user_permissions_permission_id_permissions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_permissions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "permission_id", name=op.f("pk_user_permissions")),
    )
    op.create_index(op.f("ix_user_permissions_permission_id"), "user_permissions", ["permission_id"], unique=False)

    # 8. Table: refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_session_expiration", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_remember_me", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_expires_at"), "refresh_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_max_session_expiration"), "refresh_tokens", ["max_session_expiration"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(
        "ix_refresh_tokens_user_active",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("is_revoked = false"),
    )

    # 9. Seed default roles and permissions
    superadmin_role_id = uuid7()
    viewer_role_id = uuid7()

    op.bulk_insert(
        roles_table,
        [
            {
                "id": superadmin_role_id,
                "code": "super_admin",
                "name": "Головний адміністратор",
                "description": "Повний безперешкодний доступ до всіх підсистем rating-platform",
                "version": 1,
            },
            {
                "id": viewer_role_id,
                "code": "viewer",
                "name": "Глядач",
                "description": "Базова роль: перегляд інформації без права внесення змін (Read-only)",
                "version": 1,
            },
        ],
    )

    perm_records = []
    role_perm_records = []
    viewer_allowed_prefixes = ("users:read", "users:read_short", "roles:read", "permissions:read")

    for code, name, desc in PERMISSIONS:
        p_id = uuid7()
        perm_records.append({
            "id": p_id,
            "code": code,
            "name": name,
            "description": desc,
        })
        role_perm_records.append({
            "role_id": superadmin_role_id,
            "permission_id": p_id,
        })
        if code in viewer_allowed_prefixes:
            role_perm_records.append({
                "role_id": viewer_role_id,
                "permission_id": p_id,
            })

    op.bulk_insert(permissions_table, perm_records)
    op.bulk_insert(role_permissions_table, role_perm_records)


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("user_permissions")
    op.drop_constraint(op.f("fk_roles_created_by_id_users"), "roles", type_="foreignkey")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
