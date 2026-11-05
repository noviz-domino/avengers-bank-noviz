"""add product_preferential_rates

Revision ID: d81f4b6c2e90
Revises: c3d9e1a47b20
Create Date: 2026-11-05 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd81f4b6c2e90'
down_revision: Union[str, Sequence[str], None] = 'c3d9e1a47b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_product_preferential_rates_rate": "rate > 0",
}


def upgrade() -> None:
    op.create_table('product_preferential_rates',
        sa.Column('rate_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['account_products.product_id']),
        sa.PrimaryKeyConstraint('rate_id'),
        sa.UniqueConstraint('product_id', 'code', name='uq_product_preferential_rates_product_id_code'),
        sa.CheckConstraint(CHECKS['ck_product_preferential_rates_rate'], name='ck_product_preferential_rates_rate'),
    )


def downgrade() -> None:
    op.drop_table('product_preferential_rates')
