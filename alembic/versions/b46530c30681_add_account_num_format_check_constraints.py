"""add account_num format check constraints

Revision ID: b46530c30681
Revises: fa43c0fac2bf
Create Date: 2026-11-04 02:14:26.012799

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b46530c30681'
down_revision: Union[str, Sequence[str], None] = 'fa43c0fac2bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 계좌번호 110-TPP-NNNNNN, T = 1 입출금 / 2 예금 / 3 적금 (domains/accounts/account_number.py)
CHECKS = {
    "checking_accounts": "account_num LIKE '110-1__-______'",
    "deposit_accounts": "account_num LIKE '110-2__-______'",
    "savings_accounts": "account_num LIKE '110-3__-______'",
}


def upgrade() -> None:
    for table, condition in CHECKS.items():
        op.create_check_constraint(f"ck_{table}_account_num", table, condition)


def downgrade() -> None:
    for table in CHECKS:
        op.drop_constraint(f"ck_{table}_account_num", table, type_="check")
