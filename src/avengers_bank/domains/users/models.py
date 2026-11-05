from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, SmallInteger, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    nick_name: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    # 기존 행이 있는 DB에서도 마이그레이션이 되도록 NULL 허용. 회원가입 API에서는 필수 (ADR 0003)
    birth_date: Mapped[date | None] = mapped_column(Date)
    marketing_agreed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    transaction_pin_hash: Mapped[str | None] = mapped_column(String(255))  # 거래 PIN (ADR 0005)
    # 로그인 잠금과 PIN 잠금은 따로: PIN을 틀려도 로그인은 잠기지 않는다 (ADR 0005)
    login_fail_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pin_fail_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
