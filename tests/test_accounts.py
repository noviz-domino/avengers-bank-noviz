from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.products.eligibility import add_months, age_on, applied_rate
from avengers_bank.domains.products.models import AccountProduct, ProductPreferentialRate
from avengers_bank.domains.users.models import User
from avengers_bank.seed import DEMO_LOGIN_ID, DEMO_PASSWORD, seed_demo_user, seed_products

pytestmark = pytest.mark.anyio


async def product_id(name: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(AccountProduct.product_id).where(AccountProduct.name == name))


async def sign_in(client, login_id="ironman", birth="1990-05-29", marketing=False) -> dict:
    await client.post("/users/signup", json={
        "login_id": login_id, "password": "password1234", "name": "토니", "phone": "010-1234-5678",
        "birth_date": birth, "marketing_agreed": marketing,
    })
    token = (await client.post("/users/login", json={"login_id": login_id, "password": "password1234"})).json()["data"]
    return {"Authorization": f"Bearer {token['access_token']}"}


@pytest.fixture
async def app(client):
    async with SessionLocal() as db:
        await seed_products(db)
    return client


def test_add_months_and_age():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 5), 14) == date(2028, 1, 5)
    assert age_on(date(2007, 11, 6), date(2026, 11, 5)) == 18  # 생일 전날
    assert age_on(date(2007, 11, 5), date(2026, 11, 5)) == 19


async def test_open_checking_gets_number_and_limits(app):
    me = await sign_in(app)
    pid = await product_id("캡아메리카 입출금통장")
    first = (await app.post("/accounts", json={"product_id": pid, "nickname": "생활비"}, headers=me)).json()["data"]
    second = (await app.post("/accounts", json={"product_id": pid}, headers=me)).json()["data"]

    assert (first["account_num"], second["account_num"]) == ("110-101-000001", "110-101-000002")
    assert first["account_type"] == "CHECKING" and first["balance"] == 0 and first["terms"] is None
    assert (first["per_transfer_limit"], first["daily_transfer_limit"]) == (1_000_000, 5_000_000)


async def test_open_savings_applies_preferential_rate(app):
    me = await sign_in(app, marketing=True)
    body = {"product_id": await product_id("스타크 자유적금"), "term_months": 12, "monthly_payment": 100_000, "payment_day": 25}
    response = await app.post("/accounts", json=body, headers=me)
    assert response.status_code == 201
    terms = response.json()["data"]["terms"]
    # 기본 3.50 + 마케팅 0.20 + 첫 예·적금 0.30. 급여이체는 개설 때 알 수 없어서 빠짐
    assert Decimal(terms["applied_rate"]) == Decimal("4.00")
    assert [r["code"] for r in terms["rate_detail"]] == ["MARKETING_AGREED", "FIRST_PRODUCT"]
    assert terms["payment_day"] == 25 and terms["monthly_payment"] == 100_000

    again = (await app.post("/accounts", json=body, headers=me)).json()["data"]["terms"]
    assert Decimal(again["applied_rate"]) == Decimal("3.70")  # 두 번째부터는 첫 가입 우대 없음


@pytest.mark.parametrize("body, code", [
    ({"term_months": 36, "monthly_payment": 100_000}, "TERM_OUT_OF_RANGE"),
    ({"term_months": 12, "monthly_payment": 5_000}, "AMOUNT_OUT_OF_RANGE"),
    ({"term_months": 12}, "AMOUNT_OUT_OF_RANGE"),
])
async def test_savings_conditions(app, body, code):
    me = await sign_in(app)
    response = await app.post("/accounts", json={"product_id": await product_id("스타크 자유적금"), **body}, headers=me)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


async def test_age_condition(app):
    me = await sign_in(app, birth="2012-01-01")
    body = {"product_id": await product_id("주니어 캡아메리카 적금"), "term_months": 12, "monthly_payment": 10_000}
    response = await app.post("/accounts", json=body, headers=me)
    assert response.json()["error"]["code"] == "AGE_NOT_ELIGIBLE"


@pytest.mark.parametrize("name, code", [("히어로 정기예금", "DEPOSIT_NEEDS_TRANSFER"), ("캡아메리카 신용대출", "PRODUCT_NOT_OPENABLE")])
async def test_not_openable_here(app, name, code):
    me = await sign_in(app)
    response = await app.post("/accounts", json={"product_id": await product_id(name), "term_months": 12, "monthly_payment": 1_000_000}, headers=me)
    assert response.json()["error"]["code"] == code


async def test_main_screen_total_and_order(app):
    async with SessionLocal() as db:
        await seed_demo_user(db)
    token = (await app.post("/users/login", json={"login_id": DEMO_LOGIN_ID, "password": DEMO_PASSWORD})).json()["data"]
    me = {"Authorization": f"Bearer {token['access_token']}"}

    data = (await app.get("/accounts", headers=me)).json()["data"]
    balances = [a["balance"] for a in data["accounts"]]
    assert balances == sorted(balances, reverse=True)  # 잔액 많은 순: 화면은 앞의 3개
    assert data["total_balance"] == sum(balances) == 5_000_000 + 2_350_000 + 600_000 + 150_000
    assert data["accounts"][0]["product_name"] == "히어로 정기예금"


async def test_other_users_account_is_not_found(app):
    owner = await sign_in(app)
    other = await sign_in(app, login_id="thor")
    account = (await app.post("/accounts", json={"product_id": await product_id("캡아메리카 입출금통장")}, headers=owner)).json()["data"]

    for path in [f"/accounts/{account['account_id']}", f"/accounts/{account['account_id']}/transactions", "/accounts/999"]:
        response = await app.get(path, headers=other)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
    response = await app.patch(f"/accounts/{account['account_id']}", json={"nickname": "내꺼"}, headers=other)
    assert response.status_code == 404
    assert (await app.get("/accounts", headers=other)).json()["data"] == {"total_balance": 0, "accounts": []}


async def test_transactions_paging_and_rename(app):
    async with SessionLocal() as db:
        await seed_demo_user(db)
    token = (await app.post("/users/login", json={"login_id": DEMO_LOGIN_ID, "password": DEMO_PASSWORD})).json()["data"]
    me = {"Authorization": f"Bearer {token['access_token']}"}
    living = next(a for a in (await app.get("/accounts", headers=me)).json()["data"]["accounts"] if a["nickname"] == "생활비")

    page1 = (await app.get(f"/accounts/{living['account_id']}/transactions", params={"limit": 3}, headers=me)).json()["data"]
    page2 = (await app.get(f"/accounts/{living['account_id']}/transactions",
                           params={"limit": 3, "before": page1[-1]["tx_id"]}, headers=me)).json()["data"]
    assert [t["memo"] for t in page1 + page2] == ["점심", "월세", "편의점", "급여"]  # 최근부터
    assert page1[0]["balance_after"] == living["balance"]

    response = await app.patch(f"/accounts/{living['account_id']}", json={"nickname": None}, headers=me)
    assert response.json()["data"]["nickname"] is None


async def test_requires_login(app):
    assert (await app.get("/accounts")).status_code == 401


async def test_closed_accounts_not_in_total(app):
    me = await sign_in(app)
    pid = await product_id("캡아메리카 입출금통장")
    for _ in range(2):
        await app.post("/accounts", json={"product_id": pid}, headers=me)
    async with SessionLocal() as db:
        await db.execute(update(Account).values(balance=1000))
        await db.execute(update(Account).where(Account.account_id == 1).values(status="CLOSED"))
        await db.commit()
    data = (await app.get("/accounts", headers=me)).json()["data"]
    assert [a["account_id"] for a in data["accounts"]] == [2]
    assert data["total_balance"] == 1000


def test_rate_detail_adds_up_when_capped():
    product = AccountProduct(base_rate=Decimal("3.00"), max_preferential_rate=Decimal("0.50"), preferential_rates=[
        ProductPreferentialRate(code="A", description="a", rate=Decimal("0.40")),
        ProductPreferentialRate(code="B", description="b", rate=Decimal("0.30")),
    ])
    result = applied_rate(product, {"A", "B"})
    assert result.rate == Decimal("3.50")
    assert product.base_rate + sum(Decimal(d["rate"]) for d in result.detail) == result.rate
    assert result.detail[-1] == {"code": "PREFERENTIAL_CAP", "rate": "-0.20"}


async def test_blank_nickname_rejected(app):
    me = await sign_in(app)
    response = await app.post("/accounts", json={"product_id": await product_id("캡아메리카 입출금통장"), "nickname": ""}, headers=me)
    assert response.status_code == 422


async def test_seed_unlocks_demo_user(app):
    async with SessionLocal() as db:
        await seed_demo_user(db)
    async with SessionLocal() as db:
        await db.execute(update(User).values(login_fail_count=3))
        await db.commit()
    async with SessionLocal() as db:
        assert await seed_demo_user(db) is False  # 다시 만들지 않고
    async with SessionLocal() as db:
        assert await db.scalar(select(User.login_fail_count).where(User.login_id == DEMO_LOGIN_ID)) == 0  # 잠금만 풂
