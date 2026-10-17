"""Add check constraint for review status.

Revision ID: 2026_10_17_0004
Revises: 2026_09_04_0003
Create Date: 2026-10-17 18:30:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_10_17_0004"
down_revision: str | None = "2026_09_04_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_reviews_status",
        "reviews",
        "status IN ('published', 'hidden', 'flagged')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_reviews_status", "reviews", type_="check")
