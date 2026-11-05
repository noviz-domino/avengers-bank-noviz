from datetime import datetime
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
    monthly_limit: int | None
    payment_day: int | None
    status: str
    issued_at: datetime
