from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CardProductResponse(BaseModel):
    product_id: int
    type: str  # CREDIT / DEBIT
    name: str
    annual_fee: int
    benefits: str

    model_config = ConfigDict(from_attributes=True)


class CardIssue(BaseModel):
    """POST /cards — 발급. 종류는 상품이 정한다"""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    linked_account_id: int  # 결제 계좌: 내 입출금 계좌
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    payment_day: int | None = Field(default=None, ge=1, le=28)  # 신용카드 대금 출금일. 없으면 14일


class CardSuspend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["SUSPENDED", "LOST"] = "SUSPENDED"  # LOST(분실)는 다시 풀 수 없다


class CardResponse(BaseModel):
    """카드번호는 앞 6자리·뒤 4자리만 (전체 번호는 응답에 싣지 않는다)"""

    card_id: int
    card_type: str
    product_name: str
    masked_card_num: str
    nickname: str | None
    linked_account_id: int
    daily_limit: int
    credit_limit: int | None  # 신용만: 안 갚은 사용액의 한도
    payment_day: int | None
    status: str
    issued_at: datetime


class CardPayment(BaseModel):
    """POST /cards/{card_id}/payments — 가맹점 결제 흉내 (ADR 0010). 업종은 서버가 가맹점 이름으로 정한다"""

    model_config = ConfigDict(extra="forbid")

    merchant_name: str = Field(min_length=1, max_length=100)
    amount: int = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=8, max_length=100)  # 가맹점이 다시 보내도 한 번만 결제


class CardTransactionResponse(BaseModel):
    card_tx_id: int
    card_id: int
    merchant_name: str
    category: str
    amount: int
    status: str  # APPROVED / CANCELED
    billing_status: str | None  # 신용만: UNBILLED / BILLED / PAID
    approved_at: datetime
    canceled_at: datetime | None
    refund_pending: bool  # 결제 계좌가 해지돼 상담원 확인 후 환불 (ADR 0012)

    model_config = ConfigDict(from_attributes=True)


class CardLimitsResponse(BaseModel):
    daily_limit: int
    daily_used: int  # 오늘(한국 날짜) 쓴 금액, 취소 제외
    credit_limit: int | None
    credit_used: int | None  # 신용만: 안 갚은 사용액


class CardBillRunResponse(BaseModel):
    """POST /system/card-bills/run 결과. 같은 날짜로 다시 부르면 이미 낸 것은 건너뛴다"""

    run_date: date
    paid_cards: int  # 대금을 출금한 카드 수
    overdue_cards: int  # 잔액 부족 등으로 못 낸 카드 수 (BILLED로 남음)
    failed_cards: int  # 예상 못 한 오류로 건너뛴 카드 수 (그 카드만 되돌림, 로그 확인)
    total_paid: int


class CardRefundTo(BaseModel):
    """POST /system/card-refunds/{card_tx_id} — 상담원이 고른 같은 사람의 입출금 계좌로 환불"""

    model_config = ConfigDict(extra="forbid")

    to_account_id: int


class PendingRefundResponse(CardTransactionResponse):
    """GET /system/card-refunds — 상담원이 누구에게 연락하고 어느 계좌로 보낼지 정할 수 있게"""

    user_id: int  # 카드 주인
    linked_account_id: int  # 해지된 원래 결제 계좌
