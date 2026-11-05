"""데모용 상품 데이터. 여러 번 실행해도 (type, product_code)가 같은 상품은 다시 넣지 않는다.

실행: uv run python -m avengers_bank.seed  (Docker는 시작할 때 자동 실행)
상품 이름·금리는 데모용으로 지어낸 값이다.
"""

import asyncio
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import SessionLocal, engine
from avengers_bank.domains.products.models import AccountProduct, ProductPreferentialRate

SALARY = ("SALARY_TRANSFER", "이 은행 입출금 계좌로 급여를 받으면")
MARKETING = ("MARKETING_AGREED", "마케팅 정보 수신에 동의하면")
FIRST = ("FIRST_PRODUCT", "이 은행에서 처음 가입하는 예·적금이면")

PRODUCTS = [
    dict(type="CHECKING", product_code=1, name="어벤져스 입출금통장", base_rate=Decimal("0.10"),
         description="수수료 없이 쓰는 기본 입출금 통장입니다. 이체·카드 결제 계좌로 씁니다.",
         conditions="누구나 가입할 수 있습니다.", rates=[]),
    dict(type="DEPOSIT", product_code=1, name="히어로 정기예금", base_rate=Decimal("3.00"),
         min_term_months=12, max_term_months=36, min_amount=1_000_000, max_amount=100_000_000,
         description="목돈을 한 번에 맡기고 만기에 이자와 함께 받는 예금입니다.",
         conditions="100만 원부터 1억 원까지, 12~36개월.",
         rates=[(*SALARY, Decimal("0.30")), (*MARKETING, Decimal("0.20"))]),
    dict(type="DEPOSIT", product_code=2, name="쉴드 특판 예금", base_rate=Decimal("3.80"),
         min_term_months=6, max_term_months=12, min_amount=1_000_000, max_amount=30_000_000,
         sale_start=date(2026, 11, 1), sale_end=date(2026, 12, 31),
         description="연말까지만 판매하는 특판 예금입니다.",
         conditions="판매 기간 2026-11-01 ~ 2026-12-31. 100만 원부터 3천만 원까지, 6~12개월.", rates=[]),
    dict(type="SAVINGS", product_code=1, name="스타크 자유적금", base_rate=Decimal("3.50"),
         min_term_months=12, max_term_months=24, min_amount=10_000, max_amount=1_000_000,
         description="매달 정한 금액을 넣어 목돈을 만드는 적금입니다. 예산 관리의 목표 저축 계좌로 씁니다.",
         conditions="월 1만 원부터 100만 원까지, 12~24개월.",
         rates=[(*SALARY, Decimal("0.50")), (*MARKETING, Decimal("0.20")), (*FIRST, Decimal("0.30"))]),
    dict(type="SAVINGS", product_code=2, name="주니어 어벤져스 적금", base_rate=Decimal("4.00"),
         min_term_months=12, max_term_months=12, min_amount=10_000, max_amount=300_000, min_age=19,
         description="사회 초년생을 위한 1년 적금입니다.",
         conditions="만 19세 이상. 월 1만 원부터 30만 원까지, 12개월.",
         rates=[(*MARKETING, Decimal("0.30"))]),
    dict(type="LOAN", product_code=1, name="어벤져스 신용대출", base_rate=Decimal("5.50"),
         min_term_months=12, max_term_months=60, min_amount=1_000_000, max_amount=50_000_000, min_age=19,
         description="연소득을 기준으로 한도를 정하는 신용대출입니다. 원리금균등 상환.",
         conditions="만 19세 이상, 소득이 있는 분. 100만 원부터 5천만 원까지, 12~60개월.", rates=[]),
]


async def seed_products(db: AsyncSession) -> int:
    added = 0
    async with db.begin():
        for spec in PRODUCTS:
            spec = dict(spec)
            rates = spec.pop("rates")
            exists = await db.scalar(
                select(AccountProduct.product_id).where(
                    AccountProduct.type == spec["type"], AccountProduct.product_code == spec["product_code"]
                )
            )
            if exists is not None:
                continue
            product = AccountProduct(
                **spec,
                max_preferential_rate=sum((r for *_, r in rates), Decimal("0")),
                preferential_rates=[
                    ProductPreferentialRate(code=c, description=d, rate=r) for c, d, r in rates
                ],
            )
            db.add(product)
            added += 1
    return added


async def main() -> None:
    try:
        async with SessionLocal() as db:
            print(f"상품 {await seed_products(db)}개를 넣었습니다.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # Windows의 기본 이벤트 루프는 psycopg 비동기와 맞지 않는다 (alembic/env.py와 같은 처리)
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
