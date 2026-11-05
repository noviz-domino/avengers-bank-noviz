"""add pending_actions.result

Revision ID: a7c3e9f15b20
Revises: f2b8d4e6a913
Create Date: 2026-11-05 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c3e9f15b20'
down_revision: Union[str, Sequence[str], None] = 'f2b8d4e6a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pending_actions', sa.Column('result', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('pending_actions', 'result')
