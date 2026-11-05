"""데모용 상품과 데모 사용자. 여러 번 실행해도 이미 있는 상품·사용자는 다시 넣지 않는다.

실행: uv run python -m avengers_bank.seed  (Docker는 시작할 때 자동 실행)
상품 이름·금리는 데모용으로 지어낸 값이다.

- 이미 있는 상품은 **고치지 않는다**. 운영 중인 상품 금리를 seed가 덮어쓰면 안 되기 때문이다.
  데모 값을 바꾼 뒤 다시 넣으려면 DB를 초기화한다 (docker compose down -v).
- max_preferential_rate는 "우대 상한"이다. 데모 상품은 우대 조건을 모두 채운 합계를 상한으로 넣는다.
"""

import asyncio
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.database import SessionLocal, engine
from avengers_bank.core.security import hash_password
import avengers_bank.domains.approvals.models  # noqa: F401  장부의 action_id FK가 가리키는 테이블
import avengers_bank.domains.audit.models  # noqa: F401
from avengers_bank.domains.accounts.account_number import BANK_CODE, TYPE_CODES, make_account_num
from avengers_bank.domains.accounts.categories import classify
from avengers_bank.domains.accounts.repository import account_repository
from avengers_bank.domains.accounts.service import DEFAULT_DAILY_TRANSFER_LIMIT, DEFAULT_PER_TRANSFER_LIMIT
from avengers_bank.domains.accounts.models import Account, AccountTerms, AccountTransaction
from avengers_bank.domains.products.eligibility import add_months
from avengers_bank.domains.products.models import AccountProduct, ProductPreferentialRate
from avengers_bank.domains.users.models import User

# 데모 화면 확인용 로그인 정보 (실제 비밀이 아님). README "데모 계정"과 같다
DEMO_LOGIN_ID, DEMO_PASSWORD = "demo", "demo-password-1234"

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
         sale_start=date(2026, 11, 1), sale_end=date(2027, 12, 31),  # 데모 기간 내내 보이게
         description="정해진 기간에만 판매하는 특판 예금입니다.",
         conditions="판매 기간 2026-11-01 ~ 2027-12-31. 100만 원부터 3천만 원까지, 6~12개월.", rates=[]),
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


async def seed_demo_user(db: AsyncSession) -> bool:
    """메인 화면(총자산, 잔액 상위 3개 계좌)을 바로 볼 수 있는 데모 사용자. 상품 seed 뒤에 실행한다.

    shortcut: 잔액과 장부를 실행 함수(ADR 0007)를 거치지 않고 직접 넣는다. 초기 데이터라서이고,
    이체 기능이 생기면 seed도 그 함수를 쓰게 바꾼다.
    """
    async with db.begin():
        existing = await db.scalar(select(User).where(User.login_id == DEMO_LOGIN_ID))
        if existing is not None:
            # 비밀번호가 README에 공개돼 있어서 누구나 5번 틀려 잠글 수 있다. 시작할 때마다 잠금을 푼다
            existing.login_fail_count, existing.login_locked_until = 0, None
            return False
        user = User(
            login_id=DEMO_LOGIN_ID, hashed_password=hash_password(DEMO_PASSWORD), name="데모 사용자",
            phone="010-0000-0000", birth_date=date(1995, 3, 15), marketing_agreed=True,
        )
        db.add(user)
        await db.flush()
        products = {
            (p.type, p.product_code): p for p in await db.scalars(select(AccountProduct))
        }
        today = today_kst()

        async def account(kind, code, nickname, txs, terms=None):
            product = products[(kind, code)]
            serial = await account_repository.last_serial(db, f"{BANK_CODE}-{TYPE_CODES[kind]}{code:02d}-") + 1
            limits = dict(per_transfer_limit=DEFAULT_PER_TRANSFER_LIMIT, daily_transfer_limit=DEFAULT_DAILY_TRANSFER_LIMIT) if kind == "CHECKING" else {}
            acc = Account(
                user_id=user.user_id, product_id=product.product_id, account_type=kind, status="ACTIVE",
                account_num=make_account_num(kind, code, serial), nickname=nickname,
                balance=sum(a for _, a, _ in txs), **limits,
            )
            db.add(acc)
            await db.flush()
            balance = 0
            for tx_type, amount, memo in txs:
                balance += amount
                db.add(AccountTransaction(
                    account_id=acc.account_id, tx_type=tx_type, amount=amount, balance_after=balance, memo=memo,
                    category=classify(tx_type, memo),
                ))
            if terms:
                db.add(AccountTerms(account_id=acc.account_id, **terms))

        await account("CHECKING", 1, "생활비", [
            ("DEPOSIT", 3_000_000, "급여"), ("CARD_PAYMENT", -38_000, "편의점"),
            ("TRANSFER_OUT", -600_000, "월세"), ("CARD_PAYMENT", -12_000, "점심"),
        ])
        await account("CHECKING", 1, "비상금", [("DEPOSIT", 150_000, "용돈")])
        await account("DEPOSIT", 1, None, [("DEPOSIT", 5_000_000, "예금 가입")], dict(
            applied_rate=Decimal("3.20"), rate_detail=[{"code": "MARKETING_AGREED", "rate": "0.20"}],
            maturity_date=add_months(today, 12),
        ))
        await account("SAVINGS", 1, "휴대폰 모으기", [("DEPOSIT", 300_000, "1회차"), ("DEPOSIT", 300_000, "2회차")], dict(
            applied_rate=Decimal("3.70"),  # 예금을 먼저 열어서 첫 가입 우대는 없음
            rate_detail=[{"code": "MARKETING_AGREED", "rate": "0.20"}],
            maturity_date=add_months(today, 12), monthly_payment=300_000, payment_day=min(today.day, 28),
        ))
    return True


async def main() -> None:
    try:
        async with SessionLocal() as db:
            print(f"상품 {await seed_products(db)}개를 넣었습니다.")
        async with SessionLocal() as db:
            if await seed_demo_user(db):
                print(f"데모 사용자를 만들었습니다: {DEMO_LOGIN_ID}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    # Windows의 기본 이벤트 루프는 psycopg 비동기와 맞지 않는다 (alembic/env.py와 같은 처리)
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
