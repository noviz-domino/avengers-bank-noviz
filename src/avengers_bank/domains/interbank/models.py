"""ClearingHub 외부 입금 기록 모델."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class InterbankReceipt(Base):
    """외부 은행에서 들어온 이체의 중복 처리 방지 기록."""

    __tablename__ = "interbank_receipts"

    # 허브의 이체 ID: 기본키이므로 중복 저장 불가
    transfer_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)

    # 입금받는 우리 은행 계좌
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id"),
        nullable=False,
    )

    # 입금 금액
    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 송금 은행 및 송금 계좌
    sender_bank_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    sender_account: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # 입금 완료 시각
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
