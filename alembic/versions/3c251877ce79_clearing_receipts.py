"""ClearingHub 수신 영수증과 타행 거래내역 필드"""

import sqlalchemy as sa
from alembic import op

revision = "3c251877ce79"
down_revision = "76d5bb82ac41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clearing_receipts",
        sa.Column("transfer_id", sa.Uuid(), primary_key=True),
        sa.Column("holder_name", sa.String(50), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.alter_column("account_transactions", "counterparty_name", type_=sa.String(101))
    op.alter_column("account_transactions", "counterparty_account", type_=sa.String(50))


def downgrade() -> None:
    op.alter_column("account_transactions", "counterparty_account", type_=sa.String(30))
    op.alter_column("account_transactions", "counterparty_name", type_=sa.String(50))
    op.drop_table("clearing_receipts")
