"""카드 상품, 카드, 카드 사용내역 (docs/ERD.md, 결정 이유: ADR 0003·0009·0010)"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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
CARD_TX_STATUSES = ("APPROVED", "CANCELED")
# 신용카드 사용분의 대금 상태: 쓴 뒤 UNBILLED → 결제일에 BILLED → 출금되면 PAID. 출금 못 하면 BILLED(연체)로 남음 (ADR 0011). 체크카드는 NULL
BILLING_STATUSES = ("UNBILLED", "BILLED", "PAID")


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
        # 신용 한도와 대금 출금일은 신용카드에만 (CHECK는 NULL이면 통과라서 IS NOT NULL을 따로 적는다)
        CheckConstraint(
            "(card_type = 'CREDIT' AND credit_limit IS NOT NULL AND credit_limit >= daily_limit"
            " AND payment_day IS NOT NULL AND payment_day BETWEEN 1 AND 28)"
            " OR (card_type = 'DEBIT' AND credit_limit IS NULL AND payment_day IS NULL)",
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
    credit_limit: Mapped[int | None] = mapped_column(BigInteger)  # 신용만. 안 갚은 사용액 합계의 한도 (ADR 0010)
    payment_day: Mapped[int | None] = mapped_column(SmallInteger)  # 신용만, 1~28
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CardTransaction(Base):
    """카드 사용내역. 체크카드는 장부 줄(account_tx_id)과 함께, 신용카드는 청구 상태(billing_status)만 갖는다"""

    __tablename__ = "card_transactions"
    __table_args__ = (
        # 같은 결제 요청을 두 번 보내도 한 번만 결제 (가맹점이 다시 보내는 경우)
        UniqueConstraint("card_id", "idempotency_key", name="uq_card_transactions_card_id_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_card_transactions_amount"),
        CheckConstraint(in_sql("status", CARD_TX_STATUSES), name="ck_card_transactions_status"),
        CheckConstraint(
            f"(account_tx_id IS NOT NULL AND billing_status IS NULL)"
            f" OR (account_tx_id IS NULL AND {in_sql('billing_status', BILLING_STATUSES)})",
            name="ck_card_transactions_kind",
        ),
        CheckConstraint(
            "(status = 'APPROVED' AND canceled_at IS NULL) OR (status = 'CANCELED' AND canceled_at IS NOT NULL)",
            name="ck_card_transactions_canceled_at",
        ),
        # 갚은(PAID) 사용분만 대금 출금 줄이 있다 (billing_status가 NULL인 체크카드는 둘째 줄)
        CheckConstraint(
            "(billing_status = 'PAID' AND bill_tx_id IS NOT NULL)"
            " OR (COALESCE(billing_status, '') <> 'PAID' AND bill_tx_id IS NULL)",
            name="ck_card_transactions_bill_tx",
        ),
        Index("ix_card_transactions_card_id_approved_at", "card_id", "approved_at"),
    )

    card_tx_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.card_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # 가맹점 이름으로 서버가 정함
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="APPROVED", nullable=False)
    billing_status: Mapped[str | None] = mapped_column(String(10))  # 신용만
    account_tx_id: Mapped[int | None] = mapped_column(ForeignKey("account_transactions.tx_id"))  # 체크만: 출금 줄
    refund_tx_id: Mapped[int | None] = mapped_column(ForeignKey("account_transactions.tx_id"))  # 취소 환불 줄
    bill_tx_id: Mapped[int | None] = mapped_column(ForeignKey("account_transactions.tx_id"))  # 신용: 갚은 대금 출금 줄
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def refund_pending(self) -> bool:
        """취소됐는데 돈을 못 돌려줌: 결제 계좌가 해지돼 상담원이 다른 계좌로 보낼 때까지 (ADR 0012)"""
        paid_out = self.account_tx_id is not None or self.billing_status == "PAID"
        return self.status == "CANCELED" and paid_out and self.refund_tx_id is None
