"""예산 관리: 신청 정보, 고정 지출, 주기(결제 검사 때 잠그는 행), 예산 초과 결정 기록 (docs/ERD.md, ADR 0022)"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class BudgetProfile(Base):
    """사용자당 하나. 해지하면 지우지 않고 active=False (다시 신청하면 이 행을 덮어씀)"""

    __tablename__ = "budget_profiles"
    __table_args__ = (
        CheckConstraint("monthly_income > 0", name="ck_budget_profiles_monthly_income"),
        CheckConstraint("payday BETWEEN 1 AND 28", name="ck_budget_profiles_payday"),
        # 목표는 네 칸이 모두 있거나 모두 없다 (CHECK는 NULL이면 통과라서 IS NULL을 따로 적는다)
        CheckConstraint(
            "(goal_name IS NULL AND goal_target_amount IS NULL AND goal_months IS NULL AND goal_monthly_amount IS NULL)"
            " OR (goal_name IS NOT NULL AND goal_target_amount > 0 AND goal_months BETWEEN 1 AND 60"
            " AND goal_monthly_amount > 0)",
            name="ck_budget_profiles_goal",
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    monthly_income: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 주기 시작일 1~28 (모든 달에 있는 날)
    essentials: Mapped[dict] = mapped_column(JSON, nullable=False)  # 필수 생활비 하루 금액 {"식사": 15000}
    always_allow: Mapped[list] = mapped_column(JSON, nullable=False)  # 항상 통과 업종 (카드 결제만) ["의료"]
    goal_name: Mapped[str | None] = mapped_column(String(50))
    goal_target_amount: Mapped[int | None] = mapped_column(BigInteger)
    goal_months: Mapped[int | None] = mapped_column(SmallInteger)
    goal_monthly_amount: Mapped[int | None] = mapped_column(BigInteger)  # 신청 때 계산 (목표 ÷ 개월, 올림)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fixed_expenses_amount"),
        CheckConstraint("day BETWEEN 1 AND 31", name="ck_fixed_expenses_day"),
    )

    fixed_expense_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("budget_profiles.user_id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 나가는 날. 그 달에 없으면 말일


class BudgetCycle(Base):
    """월급날 ~ 다음 월급날 전날. 지출을 실행할 때 이 행을 가장 먼저 잠근다 (같은 사용자의 지출을 한 줄로)"""

    __tablename__ = "budget_cycles"
    __table_args__ = (
        UniqueConstraint("user_id", "start_date", name="uq_budget_cycles_user_id_start_date"),
        CheckConstraint("end_date >= start_date", name="ck_budget_cycles_dates"),
    )

    cycle_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BudgetDecision(Base):
    """예산을 넘는 지출을 사람이 확인한 기록(사유·긴급), 항상 통과 업종으로 지나간 결제 기록"""

    __tablename__ = "budget_decisions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_budget_decisions_amount"),)

    decision_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True, nullable=False)
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pending_actions.action_id"))  # 항상 통과는 NULL
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    free_to_spend_at_confirm: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 확인 때 본 자유 사용 가능액
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
