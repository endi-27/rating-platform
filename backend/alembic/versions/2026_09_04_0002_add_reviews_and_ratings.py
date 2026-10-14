"""Add reviews and ratings schema.

Revision ID: 2026_09_04_0002
Revises: 2026_09_04_0001
Create Date: 2026-09-04 12:00:00.000000

"""
from typing import Sequence, Union
from uuid6 import uuid7
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "2026_09_04_0002"
down_revision: Union[str, None] = "2026_09_04_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = [
    ("targets:read", "Перегляд об'єктів оцінювання", "Дозвіл на перегляд каталогу та карток об'єктів"),
    ("targets:create", "Створення об'єктів оцінювання", "Дозвіл на додавання нових тарґетів у каталог"),
    ("targets:update", "Оновлення об'єктів оцінювання", "Дозвіл на редагування інформації про об'єкти"),
    ("targets:delete", "Видалення об'єктів оцінювання", "Дозвіл на деактивацію та видалення об'єктів"),
    ("reviews:read", "Перегляд відгуків", "Дозвіл на читання публічних відгуків та рейтингів"),
    ("reviews:create", "Публікація відгуків", "Дозвіл на залишення власного відгуку та оцінки"),
    ("reviews:update", "Оновлення власних відгуків", "Дозвіл на редагування власного відгуку"),
    ("reviews:delete", "Видалення власних відгуків", "Дозвіл на видалення власного відгуку"),
    ("reviews:moderate", "Модерація відгуків", "Дозвіл на приховування або блокування будь-яких відгуків"),
    ("reviews:vote", "Голосування за відгуки", "Дозвіл на оцінку корисності відгуків"),
]


def upgrade() -> None:
    # 1. Table: targets
    op.create_table(
        "targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name=op.f("fk_targets_created_by_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_targets")),
        sa.UniqueConstraint("slug", name=op.f("uq_targets_slug")),
    )
    op.create_index(op.f("ix_targets_category"), "targets", ["category"], unique=False)
    op.create_index(op.f("ix_targets_created_by_id"), "targets", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_targets_deleted_at"), "targets", ["deleted_at"], unique=False)
    op.create_index(
        "ix_targets_title_trgm",
        "targets",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    # 2. Table: target_ratings
    op.create_table(
        "target_ratings",
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("total_reviews", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("average_score", sa.Numeric(precision=3, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("bayesian_score", sa.Numeric(precision=3, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("star_1_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("star_2_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("star_3_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("star_4_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("star_5_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("total_reviews >= 0", name=op.f("ck_target_ratings_total_reviews_positive")),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], name=op.f("fk_target_ratings_target_id_targets"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("target_id", name=op.f("pk_target_ratings")),
    )
    op.create_index(op.f("ix_target_ratings_average_score"), "target_ratings", ["average_score"], unique=False)
    op.create_index(op.f("ix_target_ratings_bayesian_score"), "target_ratings", ["bayesian_score"], unique=False)

    # 3. Table: reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'published'"), nullable=False),
        sa.Column("helpful_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unhelpful_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("score >= 1 AND score <= 5", name=op.f("ck_reviews_score_range")),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], name=op.f("fk_reviews_target_id_targets"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_reviews_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("target_id", "user_id", name=op.f("uq_reviews_target_user")),
    )
    op.create_index("ix_reviews_target_status_created", "reviews", ["target_id", "status", "created_at"], unique=False)
    op.create_index(op.f("ix_reviews_target_id"), "reviews", ["target_id"], unique=False)
    op.create_index(op.f("ix_reviews_user_id"), "reviews", ["user_id"], unique=False)

    # 4. Table: review_votes
    op.create_table(
        "review_votes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("is_helpful", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], name=op.f("fk_review_votes_review_id_reviews"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_review_votes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_votes")),
        sa.UniqueConstraint("review_id", "user_id", name=op.f("uq_review_votes_review_user")),
    )
    op.create_index(op.f("ix_review_votes_created_at"), "review_votes", ["created_at"], unique=False)
    op.create_index(op.f("ix_review_votes_review_id"), "review_votes", ["review_id"], unique=False)
    op.create_index(op.f("ix_review_votes_user_id"), "review_votes", ["user_id"], unique=False)

    # 5. Seed new permissions for targets and reviews
    connection = op.get_bind()
    
    # Знаходимо роль super_admin та viewer
    res = connection.execute(sa.text("SELECT id, code FROM roles WHERE code IN ('super_admin', 'viewer')"))
    roles_map = {row.code: row.id for row in res}
    superadmin_role_id = roles_map.get("super_admin")
    viewer_role_id = roles_map.get("viewer")

    for code, name, desc in NEW_PERMISSIONS:
        p_id = uuid7()
        connection.execute(
            sa.text(
                "INSERT INTO permissions (id, code, name, description, created_at) "
                "VALUES (:id, :code, :name, :description, now())"
            ),
            {"id": p_id, "code": code, "name": name, "description": desc},
        )
        if superadmin_role_id:
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": superadmin_role_id, "permission_id": p_id},
            )
        if viewer_role_id and code in ("targets:read", "reviews:read"):
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": viewer_role_id, "permission_id": p_id},
            )


def downgrade() -> None:
    # 1. Remove seeded permissions
    connection = op.get_bind()
    perm_codes = tuple(p[0] for p in NEW_PERMISSIONS)
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes"),
        {"codes": perm_codes},
    )

    # 2. Drop tables
    op.drop_table("review_votes")
    op.drop_table("reviews")
    op.drop_table("target_ratings")
    op.drop_table("targets")
