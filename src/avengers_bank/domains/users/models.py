import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, SmallInteger, String, Uuid, false, func
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

    @property
    def has_pin(self) -> bool:
        return self.transaction_pin_hash is not None


class RefreshToken(Base):
    """로그인 유지용 토큰. 원문은 저장하지 않고 SHA-256 해시만 둔다 (ADR 0005)

    쓸 때마다 새 토큰으로 바꾸고(rotation), 같은 로그인에서 이어진 토큰은 family_id로 묶는다.
    이미 바꾼 토큰이 다시 오면 도난으로 보고 그 family 전체를 폐기한다.
    """

    __tablename__ = "refresh_tokens"

    token_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[int | None] = mapped_column(ForeignKey("refresh_tokens.token_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
