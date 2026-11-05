"""카드 상품과 카드 (docs/ERD.md, 결정 이유: ADR 0003·0009). 사용내역(card_transactions)은 카드 결제 PR에서"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base, in_sql

CARD_TYPES = ("CREDIT", "DEBIT")
CARD_STATUSES = ("ACTIVE", "SUSPENDED", "LOST")


class CardProduct(Base):
    __tablename__ = "card_products"
    __table_args__ = (
        UniqueConstraint("type", "product_code", name="uq_card_products_type_product_code"),
        CheckConstraint(in_sql("type", CARD_TYPES), name="ck_card_products_type"),
        CheckConstraint("product_code BETWEEN 1 AND 99", name="ck_card_products_product_code"),
        CheckConstraint("annual_fee >= 0", name="ck_card_products_annual_fee"),
    )

    product_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    product_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 카드번호의 PP
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    annual_fee: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    benefits: Mapped[str] = mapped_column(Text, nullable=False)  # 혜택 설명, RAG 문서로도 사용
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)


class Card(Base):
    """신용·체크카드를 한 테이블에 (ADR 0003). 누적 사용액은 저장하지 않고 사용내역 합계로 계산한다"""

    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint(in_sql("card_type", CARD_TYPES), name="ck_cards_card_type"),
        CheckConstraint(in_sql("status", CARD_STATUSES), name="ck_cards_status"),
        CheckConstraint("card_num LIKE '9410____________'", name="ck_cards_card_num"),
        CheckConstraint("daily_limit > 0", name="ck_cards_daily_limit"),
        # 월 한도와 대금 출금일은 신용카드에만 (CHECK는 NULL이면 통과라서 IS NOT NULL을 따로 적는다)
        CheckConstraint(
            "(card_type = 'CREDIT' AND monthly_limit IS NOT NULL AND monthly_limit >= daily_limit"
            " AND payment_day IS NOT NULL AND payment_day BETWEEN 1 AND 28)"
            " OR (card_type = 'DEBIT' AND monthly_limit IS NULL AND payment_day IS NULL)",
            name="ck_cards_credit_terms",
        ),
    )

    card_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("card_products.product_id"), nullable=False)
    # 결제 계좌: 체크카드는 결제할 때 바로 출금, 신용카드는 대금 출금일에 출금. 주인과 같은 사람의 입출금 계좌
    linked_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    card_type: Mapped[str] = mapped_column(String(10), nullable=False)
    card_num: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # 응답에는 가린 번호만
    nickname: Mapped[str | None] = mapped_column(String(50))
    daily_limit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    monthly_limit: Mapped[int | None] = mapped_column(BigInteger)  # 신용만
    payment_day: Mapped[int | None] = mapped_column(SmallInteger)  # 신용만, 1~28
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
