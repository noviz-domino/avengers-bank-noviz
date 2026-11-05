"""add audit_logs

Revision ID: f2b8d4e6a913
Revises: e5a72c9d31f4
Create Date: 2026-11-05 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b8d4e6a913'
down_revision: Union[str, Sequence[str], None] = 'e5a72c9d31f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_audit_logs_actor": "actor IN ('USER', 'AGENT', 'MCP', 'SYSTEM')",
}


def upgrade() -> None:
    op.create_table('audit_logs',
        sa.Column('log_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('actor', sa.String(length=10), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('target', sa.String(length=100), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('log_id'),
        sa.CheckConstraint(CHECKS['ck_audit_logs_actor'], name='ck_audit_logs_actor'),
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')
