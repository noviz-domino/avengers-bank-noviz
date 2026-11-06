"""add card_transactions.bill_tx_id (ADR 0011)

Revision ID: d7b3e5f9a2c1
Revises: c4f8a2d6e1b7
Create Date: 2026-11-06 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7b3e5f9a2c1'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2d6e1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_card_transactions_bill_tx": (
        "(billing_status = 'PAID' AND bill_tx_id IS NOT NULL)"
        " OR (COALESCE(billing_status, '') <> 'PAID' AND bill_tx_id IS NULL)"
    ),
}


def upgrade() -> None:
    op.add_column('card_transactions', sa.Column('bill_tx_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'card_transactions_bill_tx_id_fkey', 'card_transactions', 'account_transactions', ['bill_tx_id'], ['tx_id']
    )
    # 아직 PAID인 행은 없다 (대금 출금이 이 마이그레이션부터 생김)
    op.create_check_constraint('ck_card_transactions_bill_tx', 'card_transactions', CHECKS['ck_card_transactions_bill_tx'])


def downgrade() -> None:
    op.drop_constraint('ck_card_transactions_bill_tx', 'card_transactions', type_='check')
    op.drop_constraint('card_transactions_bill_tx_id_fkey', 'card_transactions', type_='foreignkey')
    op.drop_column('card_transactions', 'bill_tx_id')
