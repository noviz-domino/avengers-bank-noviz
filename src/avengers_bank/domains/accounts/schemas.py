from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from avengers_bank.domains.accounts.categories import CATEGORIES

Category = Literal[CATEGORIES]


class AccountCreate(BaseModel):
    """POST /accounts — 입출금·적금 개설. 종류는 상품(product_id)이 정한다"""

    product_id: int
    nickname: str | None = Field(default=None, min_length=1, max_length=50)  # 빈 이름 대신 null
    # 적금만
    term_months: int | None = Field(default=None, ge=1, le=120)
    monthly_payment: int | None = Field(default=None, gt=0)
    payment_day: int | None = Field(default=None, ge=1, le=28)  # 29~31일은 없는 달이 있어서 28일까지


class DepositCreate(BaseModel):
    """POST /accounts/deposits — 예금 개설 신청. 맡길 돈을 옮겨야 해서 승인 대기를 만든다"""

    product_id: int
    from_account_id: int  # 맡길 돈을 꺼낼 내 입출금 계좌
    amount: int = Field(gt=0)
    term_months: int = Field(ge=1, le=120)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=100)


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
    account_id: int
    tx_type: str
    amount: int
    balance_after: int
    counterparty_name: str | None
    counterparty_account: str | None
    memo: str | None
    category: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionFilter(BaseModel):
    """거래내역 검색 조건. 날짜는 한국 날짜, 금액은 부호와 상관없이 크기로 비교한다"""

    account_id: int | None = None  # 없으면 내 모든 계좌
    from_date: date | None = None
    to_date: date | None = None
    min_amount: int | None = Field(default=None, ge=0)
    max_amount: int | None = Field(default=None, ge=0)
    keyword: str | None = Field(default=None, min_length=1, max_length=50)  # 메모·상대방 이름
    direction: Literal["IN", "OUT"] | None = None
    category: Category | None = None
    limit: int = Field(default=20, ge=1, le=100)
    before: int | None = None  # 이전 쪽의 마지막 tx_id

    @model_validator(mode="after")
    def check_ranges(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date가 to_date보다 늦습니다.")
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("min_amount가 max_amount보다 큽니다.")
        return self


class TransactionSearchResponse(BaseModel):
    """GET /transactions — 이번 쪽 거래 + 조건 전체의 합계 (Agent가 \"지난달 식비 얼마?\"에 바로 답할 수 있게)"""

    transactions: list[TransactionResponse]
    total_in: int   # 조건에 맞는 들어온 돈 합계 (쪽과 상관없이 전체)
    total_out: int  # 조건에 맞는 나간 돈 합계 (양수)
    next_before: int | None  # 다음 쪽을 부를 때 before에 넣을 값. 없으면 끝


class TransactionUpdate(BaseModel):
    """사용자가 카테고리·메모를 고친다. 금액·상대방은 고칠 수 없다"""

    category: Category | None = None
    memo: str | None = Field(default=None, min_length=1, max_length=100)
