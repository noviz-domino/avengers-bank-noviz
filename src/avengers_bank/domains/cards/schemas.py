from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from avengers_bank.domains.approvals.schemas import ApproveRequest


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


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PhoneLocation(Location):
    accuracy_m: float = Field(gt=0, le=100_000)
    observed_at: AwareDatetime


class MerchantPayment(CardPayment):
    channel: Literal["IN_PERSON", "ONLINE"]
    terminal_location: Location | None = None

    @model_validator(mode="after")
    def validate_terminal_location(self):
        if (self.channel == "IN_PERSON") != (self.terminal_location is not None):
            raise ValueError("오프라인 결제에만 단말기 위치를 보내야 합니다.")
        return self


class CardProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_check: bool = False
    active_from: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    active_until: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def validate_activity_window(self):
        if (self.active_from is None) != (self.active_until is None):
            raise ValueError("활동 시작과 종료 시간을 함께 입력해 주세요.")
        if self.active_from is not None and self.active_from == self.active_until:
            raise ValueError("활동 시작과 종료 시간은 달라야 합니다.")
        return self


class CardProtectionUpdate(CardProtection, ApproveRequest):
    pass


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


class CardTxFilter(BaseModel):
    """카드 사용내역 검색 조건 (GET /cards/transactions). 날짜는 한국 날짜"""

    model_config = ConfigDict(extra="forbid")  # 오타 조건을 조용히 무시하면 거르지 않은 합계가 나간다

    card_id: int | None = None  # 없으면 내 모든 카드
    keyword: str | None = Field(default=None, min_length=1, max_length=50)  # 가맹점 이름
    category: str | None = Field(default=None, max_length=20)
    from_date: date | None = None
    to_date: date | None = None

    @model_validator(mode="after")
    def check_range(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date가 to_date보다 늦습니다.")
        return self


class CardTxSearchResponse(BaseModel):
    transactions: list[CardTransactionResponse]  # 최근 것부터 최대 100건
    total_amount: int  # 조건에 맞는 승인 금액 합계 (취소 제외, 건수 제한과 상관없이 전체)
    count: int  # 조건에 맞는 전체 건수


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
