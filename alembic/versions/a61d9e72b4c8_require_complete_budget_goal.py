"""Require every goal field when a budget goal is configured (ADR 0024).

Revision ID: a61d9e72b4c8
Revises: d9fc087bbcd1
"""

from alembic import op

revision = 'a61d9e72b4c8'
down_revision = 'd9fc087bbcd1'
branch_labels = None
depends_on = None

CHECKS = {
    "ck_budget_profiles_goal": (
        "(goal_name IS NULL AND goal_target_amount IS NULL AND goal_months IS NULL AND goal_monthly_amount IS NULL)"
        " OR (goal_name IS NOT NULL AND goal_target_amount IS NOT NULL AND goal_months IS NOT NULL"
        " AND goal_monthly_amount IS NOT NULL AND goal_target_amount > 0 AND goal_months BETWEEN 1 AND 60"
        " AND goal_monthly_amount > 0)"
    ),
}
OLD_CHECK = (
    "(goal_name IS NULL AND goal_target_amount IS NULL AND goal_months IS NULL AND goal_monthly_amount IS NULL)"
    " OR (goal_name IS NOT NULL AND goal_target_amount > 0 AND goal_months BETWEEN 1 AND 60"
    " AND goal_monthly_amount > 0)"
)


def upgrade() -> None:
    with op.batch_alter_table('budget_profiles') as batch:
        batch.drop_constraint('ck_budget_profiles_goal', type_='check')
        batch.create_check_constraint('ck_budget_profiles_goal', CHECKS['ck_budget_profiles_goal'])


def downgrade() -> None:
    with op.batch_alter_table('budget_profiles') as batch:
        batch.drop_constraint('ck_budget_profiles_goal', type_='check')
        batch.create_check_constraint('ck_budget_profiles_goal', OLD_CHECK)
