"""add card_products and cards (ADR 0009)

Revision ID: b6e1f3a8c442
Revises: a7c3e9f15b20
Create Date: 2026-11-05 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6e1f3a8c442'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f15b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_card_products_type": "type IN ('CREDIT', 'DEBIT')",
    "ck_card_products_product_code": "product_code BETWEEN 1 AND 99",
    "ck_card_products_annual_fee": "annual_fee >= 0",
    "ck_cards_card_type": "card_type IN ('CREDIT', 'DEBIT')",
    "ck_cards_status": "status IN ('ACTIVE', 'SUSPENDED', 'LOST')",
    "ck_cards_card_num": "card_num LIKE '9410____________'",
    "ck_cards_daily_limit": "daily_limit > 0",
    "ck_cards_credit_terms": (
        "(card_type = 'CREDIT' AND monthly_limit IS NOT NULL AND monthly_limit >= daily_limit"
        " AND payment_day IS NOT NULL AND payment_day BETWEEN 1 AND 28)"
        " OR (card_type = 'DEBIT' AND monthly_limit IS NULL AND payment_day IS NULL)"
    ),
}


def check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def upgrade() -> None:
    op.create_table('card_products',
        sa.Column('product_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('product_code', sa.SmallInteger(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('annual_fee', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('benefits', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint('product_id'),
        sa.UniqueConstraint('type', 'product_code', name='uq_card_products_type_product_code'),
        check('ck_card_products_type'),
        check('ck_card_products_product_code'),
        check('ck_card_products_annual_fee'),
    )
    op.create_table('cards',
        sa.Column('card_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('linked_account_id', sa.Integer(), nullable=False),
        sa.Column('card_type', sa.String(length=10), nullable=False),
        sa.Column('card_num', sa.String(length=16), nullable=False),
        sa.Column('nickname', sa.String(length=50), nullable=True),
        sa.Column('daily_limit', sa.BigInteger(), nullable=False),
        sa.Column('monthly_limit', sa.BigInteger(), nullable=True),
        sa.Column('payment_day', sa.SmallInteger(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['linked_account_id'], ['accounts.account_id']),
        sa.ForeignKeyConstraint(['product_id'], ['card_products.product_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('card_id'),
        sa.UniqueConstraint('card_num'),
        check('ck_cards_card_type'),
        check('ck_cards_status'),
        check('ck_cards_card_num'),
        check('ck_cards_daily_limit'),
        check('ck_cards_credit_terms'),
    )
    op.create_index('ix_cards_user_id', 'cards', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_cards_user_id', table_name='cards')
    op.drop_table('cards')
    op.drop_table('card_products')
