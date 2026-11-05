"""감사 기록: 장부와 승인 대기에 남지 않는 보안 사건만 (로그인 실패, PIN 실패·설정 등). docs/ERD.md"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base, in_sql

ACTORS = ("USER", "AGENT", "MCP", "SYSTEM")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (CheckConstraint(in_sql("actor", ACTORS), name="ck_audit_logs_actor"),)

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), index=True)
    actor: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # LOGIN_FAILED, PIN_FAILED, PIN_SET ...
    target: Mapped[str | None] = mapped_column(String(100))  # 대상 id (예: pending_actions.action_id)
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
