"""계좌·예적금 조건·장부 (docs/ERD.md, 결정 이유: docs/decisions/0003)"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base, in_sql
from avengers_bank.domains.accounts.account_number import account_num_check_sql

ACCOUNT_TYPES = ("CHECKING", "DEPOSIT", "SAVINGS")
ACCOUNT_STATUSES = ("ACTIVE", "FROZEN", "CLOSED")
# 장부의 거래 종류. 들어오는 것은 +, 나가는 것은 -. 예산에서 어떻게 세는지는 docs/ERD.md "거래 종류"
TX_TYPES_IN = (
    "DEPOSIT", "TRANSFER_IN", "INTERNAL_IN", "GOAL_SAVING_IN", "INTEREST", "LOAN_DISBURSE", "REFUND",
)
TX_TYPES_OUT = (
    "WITHDRAW", "TRANSFER_OUT", "INTERNAL_OUT", "CARD_PAYMENT", "CARD_BILL", "GOAL_SAVING_OUT", "LOAN_REPAY",
)


class Account(Base):
    """입출금·예금·적금 계좌. 종류는 account_type으로 구분한다."""

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(in_sql("account_type", ACCOUNT_TYPES), name="ck_accounts_account_type"),
        CheckConstraint(account_num_check_sql(), name="ck_accounts_account_num"),
        CheckConstraint("balance >= 0", name="ck_accounts_balance"),
        # 이체 한도는 입출금 계좌에만 있다. CHECK는 NULL이면 통과라서 IS NOT NULL을 따로 적는다
        CheckConstraint(
            "(account_type = 'CHECKING' AND per_transfer_limit IS NOT NULL AND daily_transfer_limit IS NOT NULL"
            " AND per_transfer_limit > 0 AND daily_transfer_limit >= per_transfer_limit)"
            " OR (account_type <> 'CHECKING' AND per_transfer_limit IS NULL AND daily_transfer_limit IS NULL)",
            name="ck_accounts_transfer_limits",
        ),
        CheckConstraint(in_sql("status", ACCOUNT_STATUSES), name="ck_accounts_status"),
    )

    account_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 내 계좌 목록을 user_id로 찾는다. PostgreSQL은 FK에 인덱스를 자동으로 만들지 않는다
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("account_products.product_id"), nullable=False
    )
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_num: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50))
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    per_transfer_limit: Mapped[int | None] = mapped_column(BigInteger)
    daily_transfer_limit: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountTerms(Base):
    """예금·적금에만 있는 조건. accounts와 1:1"""

    __tablename__ = "account_terms"
    __table_args__ = (
        CheckConstraint(
            "payment_day IS NULL OR payment_day BETWEEN 1 AND 31", name="ck_account_terms_payment_day"
        ),
    )

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), primary_key=True)
    applied_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 가입 때 확정된 연 금리(%)
    # 적용된 우대 내역 스냅샷 예: [{"code": "SALARY_TRANSFER", "rate": 0.5}]
    rate_detail: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_payment: Mapped[int | None] = mapped_column(BigInteger)  # 적금만
    payment_day: Mapped[int | None] = mapped_column(SmallInteger)  # 적금 납입일 1~31


class AccountTransaction(Base):
    """모든 계좌의 장부. 들어오면 +, 나가면 -"""

    __tablename__ = "account_transactions"
    __table_args__ = (
        # 거래 종류가 목록에 있고, 금액 부호가 종류와 맞아야 한다 (WITHDRAW +1000 같은 실수를 막음)
        CheckConstraint(
            f"({in_sql('tx_type', TX_TYPES_IN)} AND amount > 0) OR ({in_sql('tx_type', TX_TYPES_OUT)} AND amount < 0)",
            name="ck_account_transactions_amount_sign",
        ),
        CheckConstraint("balance_after >= 0", name="ck_account_transactions_balance_after"),
        # 거래내역 조회와 1일 이체 한도 계산이 이 순서로 찾는다
        Index("ix_account_transactions_account_id_created_at", "account_id", "created_at"),
    )

    tx_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pending_actions.action_id"))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # 이체 두 줄을 묶음
    tx_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(101))
    counterparty_account: Mapped[str | None] = mapped_column(String(50))
    memo: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(30))  # 예산 기능에서 categories FK로 바꿈
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
