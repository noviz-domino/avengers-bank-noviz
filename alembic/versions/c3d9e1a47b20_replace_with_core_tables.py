"""replace team skeleton tables with core tables (ADR 0003)

계좌 3종·거래내역 3종·카드 5개를 지우고 accounts, account_terms, account_transactions,
pending_actions를 만든다. users와 account_products에는 컬럼을 추가한다.
데이터가 없는 테이블만 지운다 (users 행은 유지).

Revision ID: c3d9e1a47b20
Revises: ac577183c7ec
Create Date: 2026-11-05 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d9e1a47b20'
down_revision: Union[str, Sequence[str], None] = 'ac577183c7ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# alembic check는 CHECK를 감지하지 못해서 직접 적는다. 모델과 같은지는 tests/test_account_number.py가 확인
CHECKS = {
    "ck_account_products_type": "type IN ('CHECKING', 'DEPOSIT', 'SAVINGS', 'LOAN')",
    "ck_accounts_account_type": "account_type IN ('CHECKING', 'DEPOSIT', 'SAVINGS')",
    "ck_accounts_account_num": (
        "(account_type = 'CHECKING' AND account_num LIKE '110-1__-______')"
        " OR (account_type = 'DEPOSIT' AND account_num LIKE '110-2__-______')"
        " OR (account_type = 'SAVINGS' AND account_num LIKE '110-3__-______')"
    ),
    "ck_accounts_balance": "balance >= 0",
    "ck_accounts_transfer_limits": (
        "(account_type = 'CHECKING' AND per_transfer_limit IS NOT NULL AND daily_transfer_limit IS NOT NULL)"
        " OR (account_type <> 'CHECKING' AND per_transfer_limit IS NULL AND daily_transfer_limit IS NULL)"
    ),
    "ck_accounts_status": "status IN ('ACTIVE', 'FROZEN', 'CLOSED')",
    "ck_account_terms_payment_day": "payment_day IS NULL OR payment_day BETWEEN 1 AND 31",
    "ck_pending_actions_status": "status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED', 'FAILED')",
    "ck_pending_actions_requested_by": "requested_by IN ('WEB', 'AGENT', 'MCP')",
    "ck_pending_actions_approval_method": "approval_method IS NULL OR approval_method IN ('PIN', 'PASSKEY')",
    "ck_account_transactions_tx_type": (
        "tx_type IN ('DEPOSIT', 'WITHDRAW', 'TRANSFER_IN', 'TRANSFER_OUT', 'INTERNAL_IN', 'INTERNAL_OUT',"
        " 'CARD_PAYMENT', 'CARD_BILL', 'GOAL_SAVING_IN', 'GOAL_SAVING_OUT', 'INTEREST',"
        " 'LOAN_DISBURSE', 'LOAN_REPAY', 'REFUND')"
    ),
    "ck_account_transactions_amount": "amount <> 0",
    "ck_account_transactions_balance_after": "balance_after >= 0",
}

# 팀 뼈대 테이블. downgrade에서 다시 만들 때 쓴다 (b46530c30681의 CHECK와 같음)
OLD_ACCOUNT_NUM_CHECKS = {
    "checking_accounts": "account_num LIKE '110-1__-______'",
    "deposit_accounts": "account_num LIKE '110-2__-______'",
    "savings_accounts": "account_num LIKE '110-3__-______'",
}
OLD_TABLES = [  # 지우는 순서 (FK를 가진 쪽부터)
    "debit_card_histories", "credit_card_histories", "debit_cards", "credit_cards", "card_products",
    "savings_account_histories", "deposit_account_histories", "checking_account_histories",
    "savings_accounts", "deposit_accounts", "checking_accounts",
]


def check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def upgrade() -> None:
    for table in OLD_TABLES:
        op.drop_table(table)

    # 기존 users 행이 있어도 되도록 NULL 허용이거나 server_default가 있다
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('marketing_agreed', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('users', sa.Column('transaction_pin_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('login_fail_count', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('login_locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('pin_fail_count', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('pin_locked_until', sa.DateTime(timezone=True), nullable=True))

    op.alter_column('account_products', 'interest_rate', new_column_name='base_rate')
    op.add_column('account_products', sa.Column('max_preferential_rate', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    op.add_column('account_products', sa.Column('min_term_months', sa.SmallInteger(), nullable=True))
    op.add_column('account_products', sa.Column('max_term_months', sa.SmallInteger(), nullable=True))
    op.add_column('account_products', sa.Column('min_amount', sa.BigInteger(), nullable=True))
    op.add_column('account_products', sa.Column('max_amount', sa.BigInteger(), nullable=True))
    op.add_column('account_products', sa.Column('min_age', sa.SmallInteger(), nullable=True))
    op.add_column('account_products', sa.Column('conditions', sa.Text(), nullable=True))
    op.add_column('account_products', sa.Column('sale_start', sa.Date(), nullable=True))
    op.add_column('account_products', sa.Column('sale_end', sa.Date(), nullable=True))
    op.add_column('account_products', sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_check_constraint('ck_account_products_type', 'account_products', CHECKS['ck_account_products_type'])

    op.create_table('accounts',
        sa.Column('account_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('account_type', sa.String(length=20), nullable=False),
        sa.Column('account_num', sa.String(length=20), nullable=False),
        sa.Column('nickname', sa.String(length=50), nullable=True),
        sa.Column('balance', sa.BigInteger(), nullable=False),
        sa.Column('per_transfer_limit', sa.BigInteger(), nullable=True),
        sa.Column('daily_transfer_limit', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['account_products.product_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('account_id'),
        sa.UniqueConstraint('account_num'),
        check('ck_accounts_account_type'),
        check('ck_accounts_account_num'),
        check('ck_accounts_balance'),
        check('ck_accounts_transfer_limits'),
        check('ck_accounts_status'),
    )
    op.create_table('account_terms',
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('applied_rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('rate_detail', sa.JSON(), nullable=False),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        sa.Column('monthly_payment', sa.BigInteger(), nullable=True),
        sa.Column('payment_day', sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.account_id']),
        sa.PrimaryKeyConstraint('account_id'),
        check('ck_account_terms_payment_day'),
    )
    op.create_table('pending_actions',
        sa.Column('action_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('requested_by', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('approval_method', sa.String(length=10), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('action_id'),
        sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_pending_actions_user_id_idempotency_key'),
        check('ck_pending_actions_status'),
        check('ck_pending_actions_requested_by'),
        check('ck_pending_actions_approval_method'),
    )
    op.create_table('account_transactions',
        sa.Column('tx_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('action_id', sa.Uuid(), nullable=True),
        sa.Column('transfer_id', sa.Uuid(), nullable=True),
        sa.Column('tx_type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('balance_after', sa.BigInteger(), nullable=False),
        sa.Column('counterparty_name', sa.String(length=50), nullable=True),
        sa.Column('counterparty_account', sa.String(length=30), nullable=True),
        sa.Column('memo', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.account_id']),
        sa.ForeignKeyConstraint(['action_id'], ['pending_actions.action_id']),
        sa.PrimaryKeyConstraint('tx_id'),
        check('ck_account_transactions_tx_type'),
        check('ck_account_transactions_amount'),
        check('ck_account_transactions_balance_after'),
    )
    op.create_index('ix_account_transactions_account_id_created_at', 'account_transactions', ['account_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_account_transactions_account_id_created_at', table_name='account_transactions')
    op.drop_table('account_transactions')
    op.drop_table('pending_actions')
    op.drop_table('account_terms')
    op.drop_table('accounts')

    op.drop_constraint('ck_account_products_type', 'account_products', type_='check')
    for column in ['is_active', 'sale_end', 'sale_start', 'conditions', 'min_age', 'max_amount',
                   'min_amount', 'max_term_months', 'min_term_months', 'max_preferential_rate']:
        op.drop_column('account_products', column)
    op.alter_column('account_products', 'base_rate', new_column_name='interest_rate')

    for column in ['pin_locked_until', 'pin_fail_count', 'login_locked_until', 'login_fail_count',
                   'transaction_pin_hash', 'marketing_agreed', 'birth_date']:
        op.drop_column('users', column)

    # 팀 뼈대 테이블을 fa43c0fac2bf, b46530c30681과 같은 모양으로 되돌린다
    op.create_table('card_products',
        sa.Column('product_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('product_id'),
    )
    common = lambda prefix: [  # noqa: E731
        sa.Column(f'{prefix}_account_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('account_num', sa.String(length=20), nullable=False),
        sa.Column('balance', sa.BigInteger(), nullable=False),
    ]
    tail = lambda prefix: [  # noqa: E731
        sa.Column('nickname', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['account_products.product_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint(f'{prefix}_account_id'),
        sa.UniqueConstraint('account_num'),
        sa.CheckConstraint(OLD_ACCOUNT_NUM_CHECKS[f'{prefix}_accounts'], name=f'ck_{prefix}_accounts_account_num'),
    ]
    op.create_table('checking_accounts', *common('checking'),
        sa.Column('per_transfer_limit', sa.BigInteger(), nullable=False),
        sa.Column('daily_transfer_limit', sa.BigInteger(), nullable=False),
        *tail('checking'))
    op.create_table('deposit_accounts', *common('deposit'),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        *tail('deposit'))
    op.create_table('savings_accounts', *common('savings'),
        sa.Column('monthly_payment', sa.BigInteger(), nullable=False),
        sa.Column('monthly_deposit_date', sa.SmallInteger(), nullable=False),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        *tail('savings'))

    op.create_table('checking_account_histories',
        sa.Column('checking_account_history_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('checking_account_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('change_amount', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('from_account', sa.String(length=20), nullable=True),
        sa.Column('sending_account', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['checking_account_id'], ['checking_accounts.checking_account_id']),
        sa.PrimaryKeyConstraint('checking_account_history_id'),
    )
    for prefix in ['deposit', 'savings']:
        op.create_table(f'{prefix}_account_histories',
            sa.Column(f'{prefix}_account_history_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(f'{prefix}_account_id', sa.Integer(), nullable=False),
            sa.Column('date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('deposit_amount', sa.BigInteger(), nullable=False),
            sa.Column('type', sa.String(length=20), nullable=False),
            sa.Column('from_account', sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint([f'{prefix}_account_id'], [f'{prefix}_accounts.{prefix}_account_id']),
            sa.PrimaryKeyConstraint(f'{prefix}_account_history_id'),
        )

    for kind in ['credit', 'debit']:
        op.create_table(f'{kind}_cards',
            sa.Column(f'{kind}_card_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('checking_account_id', sa.Integer(), nullable=False),
            sa.Column('card_num', sa.String(length=19), nullable=False),
            sa.Column('accumulated_amount', sa.BigInteger(), nullable=False),
            *([sa.Column('payment_date', sa.SmallInteger(), nullable=False)] if kind == 'credit' else []),
            sa.ForeignKeyConstraint(['checking_account_id'], ['checking_accounts.checking_account_id']),
            sa.ForeignKeyConstraint(['product_id'], ['card_products.product_id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
            sa.PrimaryKeyConstraint(f'{kind}_card_id'),
            sa.UniqueConstraint('card_num'),
        )
        op.create_table(f'{kind}_card_histories',
            sa.Column(f'{kind}_card_history_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(f'{kind}_card_id', sa.Integer(), nullable=False),
            sa.Column('place_of_use', sa.String(length=100), nullable=False),
            sa.Column('used_amount', sa.BigInteger(), nullable=False),
            sa.Column('time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint([f'{kind}_card_id'], [f'{kind}_cards.{kind}_card_id']),
            sa.PrimaryKeyConstraint(f'{kind}_card_history_id'),
        )
