"""Add card protection settings and allow payment reviews created by the system."""

import sqlalchemy as sa
from alembic import op

revision = "0910c4d93eb1"
down_revision = "e8c1a4f7b3d2"
branch_labels = None
depends_on = None

CHECKS = {"ck_pending_actions_requested_by": "requested_by IN ('WEB', 'AGENT', 'MCP', 'SYSTEM')"}


def upgrade() -> None:
    op.add_column("users", sa.Column("card_protection", sa.JSON(), nullable=True))
    op.drop_constraint("ck_pending_actions_requested_by", "pending_actions", type_="check")
    op.create_check_constraint('ck_pending_actions_requested_by', 'pending_actions',
                               CHECKS['ck_pending_actions_requested_by'])


def downgrade() -> None:
    # The old application cannot execute these reviews. Refuse to downgrade while system reviews exist.
    op.drop_constraint("ck_pending_actions_requested_by", "pending_actions", type_="check")
    op.create_check_constraint(
        "ck_pending_actions_requested_by", "pending_actions", "requested_by IN ('WEB', 'AGENT', 'MCP')"
    )
    op.drop_column("users", "card_protection")
