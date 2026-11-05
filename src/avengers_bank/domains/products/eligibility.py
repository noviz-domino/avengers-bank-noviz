"""상품 가입 조건 검사와 적용 금리 계산. 계좌 개설이 쓴다 (계산은 코드, 설명은 AI: budget.md)"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from avengers_bank.core.exceptions import BadRequestException
from avengers_bank.domains.products.models import AccountProduct


def age_on(birth_date: date, today: date) -> int:
    """만 나이"""
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def add_months(start: date, months: int) -> date:
    """만기일: 같은 날짜, 그 달에 그날이 없으면 말일 (1/31 + 1개월 = 2/28)"""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def check_eligibility(
    product: AccountProduct, *, birth_date: date | None, today: date,
    term_months: int | None, amount: int | None,
) -> None:
    """가입 조건을 하나라도 못 채우면 400. 메시지는 화면과 Agent가 그대로 보여 준다."""
    def fail(code: str, message: str):
        raise BadRequestException(message=message, code=code)

    if product.min_age is not None:
        if birth_date is None or age_on(birth_date, today) < product.min_age:
            fail("AGE_NOT_ELIGIBLE", f"만 {product.min_age}세 이상만 가입할 수 있습니다.")
    lo, hi = product.min_term_months, product.max_term_months
    if (lo, hi) != (None, None) and not within(term_months, lo, hi):
        fail("TERM_OUT_OF_RANGE", f"가입 기간은 {lo or 1}~{hi or '제한 없음'}개월입니다.")
    lo, hi = product.min_amount, product.max_amount
    if (lo, hi) != (None, None) and not within(amount, lo, hi):
        fail("AMOUNT_OUT_OF_RANGE", f"금액은 {lo or 0:,}~{f'{hi:,}' if hi else '제한 없음'}원입니다.")


def within(value: int | None, lo: int | None, hi: int | None) -> bool:
    return value is not None and (lo is None or value >= lo) and (hi is None or value <= hi)


@dataclass
class AppliedRate:
    rate: Decimal
    detail: list[dict]  # account_terms.rate_detail 스냅샷


def applied_rate(product: AccountProduct, met_codes: set[str]) -> AppliedRate:
    """적용 금리 = 기본금리 + min(충족한 우대 합계, 우대 상한) (docs/ERD.md)"""
    met = [r for r in product.preferential_rates if r.code in met_codes]
    bonus = min(sum((r.rate for r in met), Decimal("0")), product.max_preferential_rate)
    return AppliedRate(
        rate=product.base_rate + bonus,
        detail=[{"code": r.code, "rate": str(r.rate)} for r in met],
    )
