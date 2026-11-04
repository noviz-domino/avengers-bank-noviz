"""add product_code to account_products

Revision ID: ac577183c7ec
Revises: b46530c30681
Create Date: 2026-11-04 02:30:03.774828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac577183c7ec'
down_revision: Union[str, Sequence[str], None] = 'b46530c30681'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRODUCT_CODE_CHECK = "product_code BETWEEN 1 AND 99"


def upgrade() -> None:
    """Upgrade schema."""
    # 상품 데이터가 이미 있으면 NOT NULL 컬럼 추가가 실패한다 (docs/decisions/0001 참고)
    op.add_column('account_products', sa.Column('product_code', sa.SmallInteger(), nullable=False))
    op.create_unique_constraint('uq_account_products_type_product_code', 'account_products', ['type', 'product_code'])
    # alembic autogenerate는 CHECK를 감지하지 못해서 직접 추가
    op.create_check_constraint('ck_account_products_product_code', 'account_products', PRODUCT_CODE_CHECK)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_account_products_product_code', 'account_products', type_='check')
    op.drop_constraint('uq_account_products_type_product_code', 'account_products', type_='unique')
    op.drop_column('account_products', 'product_code')
