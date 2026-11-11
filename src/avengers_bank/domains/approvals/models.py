"""승인 대기 작업: 사람이 PIN으로 승인해야 실행되는 요청 (docs/ERD.md 승인·실행 규칙, ADR 0004·0007)"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base, in_sql

ACTION_STATUSES = ("PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED", "FAILED")
REQUESTERS = ("WEB", "AGENT", "MCP")


class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        # 요청한 쪽이 만든 키라서 사용자마다 따로 unique
        UniqueConstraint("user_id", "idempotency_key", name="uq_pending_actions_user_id_idempotency_key"),
        CheckConstraint(in_sql("status", ACTION_STATUSES), name="ck_pending_actions_status"),
        CheckConstraint(in_sql("requested_by", REQUESTERS), name="ck_pending_actions_requested_by"),
        CheckConstraint(
            "approval_method IS NULL OR approval_method IN ('PIN', 'PASSKEY')",
            name="ck_pending_actions_approval_method",
        ),
    )

    action_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)  # 요청 내용. 만든 뒤에는 바꾸지 않는다 (멱등키 비교)
    result: Mapped[dict | None] = mapped_column(JSON)  # 실행 결과 (예: 새로 연 예금의 account_id)
    summary: Mapped[str] = mapped_column(Text, nullable=False)  # 서버가 payload로 만든 승인 화면 문장
    requested_by: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    approval_method: Mapped[str | None] = mapped_column(String(10))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def budget_check(self) -> dict:
        """요청 때 저장한 예산 미리 계산 {"free_before", "amount", "over", "impact"} (ADR 0007). 없으면 {}"""
        return self.payload.get("budget_check") or {}

    @property
    def needs_budget_reason(self) -> bool:
        """예산을 넘는 건: 승인할 때 사유를 받아야 한다"""
        return bool(self.budget_check.get("over"))

    @property
    def budget_impact(self) -> str | None:
        return self.budget_check.get("impact") if self.needs_budget_reason else None
