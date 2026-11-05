"""add card_transactions, rename cards.monthly_limit to credit_limit (ADR 0010)

Revision ID: c4f8a2d6e1b7
Revises: b6e1f3a8c442
Create Date: 2026-11-05 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4f8a2d6e1b7'
down_revision: Union[str, Sequence[str], None] = 'b6e1f3a8c442'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_cards_credit_terms": (
        "(card_type = 'CREDIT' AND credit_limit IS NOT NULL AND credit_limit >= daily_limit"
        " AND payment_day IS NOT NULL AND payment_day BETWEEN 1 AND 28)"
        " OR (card_type = 'DEBIT' AND credit_limit IS NULL AND payment_day IS NULL)"
    ),
    "ck_card_transactions_amount": "amount > 0",
    "ck_card_transactions_status": "status IN ('APPROVED', 'CANCELED')",
    "ck_card_transactions_kind": (
        "(account_tx_id IS NOT NULL AND billing_status IS NULL)"
        " OR (account_tx_id IS NULL AND billing_status IN ('UNBILLED', 'BILLED', 'PAID'))"
    ),
    "ck_card_transactions_canceled_at": (
        "(status = 'APPROVED' AND canceled_at IS NULL) OR (status = 'CANCELED' AND canceled_at IS NOT NULL)"
    ),
}
OLD_CREDIT_TERMS = (
    "(card_type = 'CREDIT' AND monthly_limit IS NOT NULL AND monthly_limit >= daily_limit"
    " AND payment_day IS NOT NULL AND payment_day BETWEEN 1 AND 28)"
    " OR (card_type = 'DEBIT' AND monthly_limit IS NULL AND payment_day IS NULL)"
)


def check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def upgrade() -> None:
    # 월 한도가 아니라 "안 갚은 사용액" 한도라서 이름을 바꾼다 (ADR 0010)
    op.drop_constraint('ck_cards_credit_terms', 'cards', type_='check')
    op.alter_column('cards', 'monthly_limit', new_column_name='credit_limit')
    op.create_check_constraint('ck_cards_credit_terms', 'cards', CHECKS['ck_cards_credit_terms'])

    op.create_table('card_transactions',
        sa.Column('card_tx_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('merchant_name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('billing_status', sa.String(length=10), nullable=True),
        sa.Column('account_tx_id', sa.Integer(), nullable=True),
        sa.Column('refund_tx_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['card_id'], ['cards.card_id']),
        sa.ForeignKeyConstraint(['account_tx_id'], ['account_transactions.tx_id']),
        sa.ForeignKeyConstraint(['refund_tx_id'], ['account_transactions.tx_id']),
        sa.PrimaryKeyConstraint('card_tx_id'),
        sa.UniqueConstraint('card_id', 'idempotency_key', name='uq_card_transactions_card_id_idempotency_key'),
        check('ck_card_transactions_amount'),
        check('ck_card_transactions_status'),
        check('ck_card_transactions_kind'),
        check('ck_card_transactions_canceled_at'),
    )
    op.create_index('ix_card_transactions_card_id_approved_at', 'card_transactions', ['card_id', 'approved_at'])


def downgrade() -> None:
    op.drop_index('ix_card_transactions_card_id_approved_at', table_name='card_transactions')
    op.drop_table('card_transactions')
    op.drop_constraint('ck_cards_credit_terms', 'cards', type_='check')
    op.alter_column('cards', 'credit_limit', new_column_name='monthly_limit')
    op.create_check_constraint('ck_cards_credit_terms', 'cards', OLD_CREDIT_TERMS)
