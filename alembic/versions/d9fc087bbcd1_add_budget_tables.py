"""add budget tables: budget_profiles, fixed_expenses, budget_cycles, budget_decisions (ADR 0024)

Revision ID: d9fc087bbcd1
Revises: e8c1a4f7b3d2
Create Date: 2026-11-09 13:57:52.215165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9fc087bbcd1'
down_revision: Union[str, Sequence[str], None] = 'e8c1a4f7b3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 모델의 CHECK를 그대로 적는다 (앱 코드를 import하지 않음, tests/test_account_number.py가 모델과 비교)
CHECKS = {
    "ck_budget_profiles_monthly_income": "monthly_income > 0",
    "ck_budget_profiles_payday": "payday BETWEEN 1 AND 28",
    "ck_budget_profiles_goal": (
        "(goal_name IS NULL AND goal_target_amount IS NULL AND goal_months IS NULL AND goal_monthly_amount IS NULL)"
        " OR (goal_name IS NOT NULL AND goal_target_amount > 0 AND goal_months BETWEEN 1 AND 60"
        " AND goal_monthly_amount > 0)"
    ),
    "ck_fixed_expenses_amount": "amount > 0",
    "ck_fixed_expenses_day": "day BETWEEN 1 AND 31",
    "ck_budget_cycles_dates": "end_date >= start_date",
    "ck_budget_decisions_amount": "amount > 0",
}


def check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def upgrade() -> None:
    op.create_table('budget_profiles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('monthly_income', sa.BigInteger(), nullable=False),
        sa.Column('payday', sa.SmallInteger(), nullable=False),
        sa.Column('essentials', sa.JSON(), nullable=False),
        sa.Column('always_allow', sa.JSON(), nullable=False),
        sa.Column('goal_name', sa.String(length=50), nullable=True),
        sa.Column('goal_target_amount', sa.BigInteger(), nullable=True),
        sa.Column('goal_months', sa.SmallInteger(), nullable=True),
        sa.Column('goal_monthly_amount', sa.BigInteger(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('user_id'),
        check('ck_budget_profiles_monthly_income'),
        check('ck_budget_profiles_payday'),
        check('ck_budget_profiles_goal'),
    )
    op.create_table('fixed_expenses',
        sa.Column('fixed_expense_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('day', sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['budget_profiles.user_id']),
        sa.PrimaryKeyConstraint('fixed_expense_id'),
        check('ck_fixed_expenses_amount'),
        check('ck_fixed_expenses_day'),
    )
    op.create_index('ix_fixed_expenses_user_id', 'fixed_expenses', ['user_id'])
    op.create_table('budget_cycles',
        sa.Column('cycle_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('cycle_id'),
        sa.UniqueConstraint('user_id', 'start_date', name='uq_budget_cycles_user_id_start_date'),
        check('ck_budget_cycles_dates'),
    )
    op.create_table('budget_decisions',
        sa.Column('decision_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action_id', sa.Uuid(), nullable=True),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('free_to_spend_at_confirm', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('emergency', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['pending_actions.action_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('decision_id'),
        check('ck_budget_decisions_amount'),
    )
    op.create_index('ix_budget_decisions_user_id', 'budget_decisions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_budget_decisions_user_id', table_name='budget_decisions')
    op.drop_table('budget_decisions')
    op.drop_table('budget_cycles')
    op.drop_index('ix_fixed_expenses_user_id', table_name='fixed_expenses')
    op.drop_table('fixed_expenses')
    op.drop_table('budget_profiles')
