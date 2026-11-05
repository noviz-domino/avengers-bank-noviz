from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    """POST /accounts — 입출금·적금 개설. 종류는 상품(product_id)이 정한다"""

    product_id: int
    nickname: str | None = Field(default=None, min_length=1, max_length=50)  # 빈 이름 대신 null
    # 적금만
    term_months: int | None = Field(default=None, ge=1, le=120)
    monthly_payment: int | None = Field(default=None, gt=0)
    payment_day: int | None = Field(default=None, ge=1, le=28)  # 29~31일은 없는 달이 있어서 28일까지


class AccountUpdate(BaseModel):
    nickname: str | None = Field(min_length=1, max_length=50)  # null이면 별칭 지움 (화면은 상품명)


class AccountSummaryResponse(BaseModel):
    """계좌 목록 한 줄. 화면은 별칭이 없으면 상품명을 보여 준다"""

    account_id: int
    account_type: str  # CHECKING / DEPOSIT / SAVINGS
    account_num: str
    product_name: str
    nickname: str | None
    balance: int
    status: str
    opened_at: datetime


class AccountListResponse(BaseModel):
    """GET /accounts — 메인 화면: 총자산 + 잔액 많은 순 계좌 (docs/planning/screens.md)"""

    total_balance: int
    accounts: list[AccountSummaryResponse]


class AccountTermsResponse(BaseModel):
    applied_rate: Decimal
    rate_detail: list[dict]
    maturity_date: date
    monthly_payment: int | None
    payment_day: int | None

    model_config = ConfigDict(from_attributes=True)


class AccountDetailResponse(AccountSummaryResponse):
    per_transfer_limit: int | None
    daily_transfer_limit: int | None
    terms: AccountTermsResponse | None  # 예·적금만


class TransactionResponse(BaseModel):
    tx_id: int
    tx_type: str
    amount: int
    balance_after: int
    counterparty_name: str | None
    counterparty_account: str | None
    memo: str | None
    category: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
