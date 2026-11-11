"""Store the user's benefit bundle preview."""

import sqlalchemy as sa
from alembic import op

revision = "76d5bb82ac41"
down_revision = "0910c4d93eb1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("benefit_bundle", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "benefit_bundle")
