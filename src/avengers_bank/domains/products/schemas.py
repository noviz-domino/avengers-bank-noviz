from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

AccountProductType = Literal["CHECKING", "DEPOSIT", "SAVINGS", "LOAN"]


class PreferentialRateResponse(BaseModel):
    code: str
    description: str
    rate: Decimal

    model_config = ConfigDict(from_attributes=True)


class AccountProductResponse(BaseModel):
    """GET /products/accounts — 목록 한 줄"""

    product_id: int
    type: str
    name: str
    base_rate: Decimal
    max_preferential_rate: Decimal
    min_term_months: int | None
    max_term_months: int | None
    min_amount: int | None
    max_amount: int | None
    min_age: int | None
    sale_start: date | None
    sale_end: date | None

    model_config = ConfigDict(from_attributes=True)


class AccountProductDetailResponse(AccountProductResponse):
    """GET /products/accounts/{product_id} — 설명·가입 조건·우대 조건까지"""

    description: str
    conditions: str | None
    preferential_rates: list[PreferentialRateResponse]


# TODO: 카드 상품 응답은 카드 기능 PR에서 card_products와 함께
