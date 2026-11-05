from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from avengers_bank.core.clock import today_kst
from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account, AccountTerms, AccountTransaction
from avengers_bank.domains.products.models import AccountProduct
from tests.test_transfers import PIN, balance, open_account, user
from avengers_bank.seed import seed_products

pytestmark = pytest.mark.anyio


async def product_id(name: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(AccountProduct.product_id).where(AccountProduct.name == name))


async def deposit_count() -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(func.count()).where(Account.account_type == "DEPOSIT"))


@pytest.fixture
async def bank(client):
    async with SessionLocal() as db:
        await seed_products(db)
    await client.post("/users/signup", json={
        "login_id": "ironman", "password": "password1234", "name": "토니", "phone": "010-1234-5678",
        "birth_date": "1990-05-29", "marketing_agreed": True,
    })
    token = (await client.post("/users/login", json={"login_id": "ironman", "password": "password1234"})).json()["data"]
    me = {"Authorization": f"Bearer {token['access_token']}"}
    await client.put("/users/me/pin", json={"password": "password1234", "pin": PIN}, headers=me)
    src = await open_account(client, me, balance=3_000_000)
    return client, me, src


def body(src, pid, amount=2_000_000, key="dep-00000001", **kw):
    return {"product_id": pid, "from_account_id": src["account_id"], "amount": amount, "term_months": 12,
            "idempotency_key": key, **kw}


async def test_deposit_opens_only_after_pin(bank):
    client, me, src = bank
    pid = await product_id("히어로 정기예금")
    response = await client.post("/accounts/deposits", json=body(src, pid, nickname="목돈"), headers=me)
    assert response.status_code == 202
    action = response.json()["data"]
    assert action["action_type"] == "OPEN_DEPOSIT"
    assert action["summary"] == f"내 계좌({src['account_num']})에서 2,000,000원을 히어로 정기예금 12개월에 맡기기"
    assert await deposit_count() == 0 and await balance(src["account_id"]) == 3_000_000  # 승인 전엔 아무것도 안 생김

    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert response.status_code == 200 and response.json()["data"]["status"] == "EXECUTED"

    async with SessionLocal() as db:
        deposit = await db.scalar(select(Account).where(Account.account_type == "DEPOSIT"))
        terms = await db.get(AccountTerms, deposit.account_id)
        rows = list(await db.scalars(select(AccountTransaction).order_by(AccountTransaction.tx_id)))
    assert (deposit.balance, deposit.nickname, deposit.account_num) == (2_000_000, "목돈", "110-201-000001")
    assert terms.applied_rate == Decimal("3.20")  # 기본 3.00 + 마케팅 0.20 (급여이체는 개설 때 모름)
    assert terms.maturity_date.year == today_kst().year + 1 and terms.monthly_payment is None
    assert [(r.tx_type, r.amount, r.memo) for r in rows] == [("INTERNAL_OUT", -2_000_000, "예금 가입"), ("INTERNAL_IN", 2_000_000, "예금 가입")]
    assert await balance(src["account_id"]) == 1_000_000


@pytest.mark.parametrize("amount, code", [(500_000, "AMOUNT_OUT_OF_RANGE"), (3_000_001, "INSUFFICIENT_BALANCE")])
async def test_request_checks(bank, amount, code):
    client, me, src = bank
    response = await client.post("/accounts/deposits", json=body(src, await product_id("히어로 정기예금"), amount=amount), headers=me)
    assert response.status_code == 400 and response.json()["error"]["code"] == code


async def test_failed_approval_leaves_no_empty_account(bank):
    client, me, src = bank
    action = (await client.post("/accounts/deposits", json=body(src, await product_id("히어로 정기예금")), headers=me)).json()["data"]
    async with SessionLocal() as db:  # 승인 전에 다른 출금으로 잔액이 줄었다
        await db.execute(update(Account).where(Account.account_id == src["account_id"]).values(balance=100_000))
        await db.commit()

    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    detail = (await client.get(f"/approvals/{action['action_id']}", headers=me)).json()["data"]
    assert detail["status"] == "FAILED"
    assert await deposit_count() == 0  # 빈 예금 계좌가 남지 않음


async def test_sale_ended_before_approval(bank):
    client, me, src = bank
    pid = await product_id("쉴드 특판 예금")
    action = (await client.post("/accounts/deposits", json=body(src, pid, amount=1_000_000), headers=me)).json()["data"]
    async with SessionLocal() as db:
        await db.execute(update(AccountProduct).where(AccountProduct.product_id == pid).values(sale_end=today_kst() - timedelta(days=1)))
        await db.commit()
    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert await deposit_count() == 0 and await balance(src["account_id"]) == 3_000_000


async def test_cannot_transfer_into_deposit_afterwards(bank):
    client, me, src = bank
    action = (await client.post("/accounts/deposits", json=body(src, await product_id("히어로 정기예금")), headers=me)).json()["data"]
    await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    response = await client.post("/transfers", json={
        "from_account_id": src["account_id"], "to_account_num": "110-201-000001", "amount": 1000, "idempotency_key": "after-deposit",
    }, headers=me)
    assert response.json()["error"]["code"] == "ACCOUNT_CANNOT_RECEIVE"  # 예금은 가입 때 한 번만 넣는다


async def test_idempotency_and_wrong_product(bank):
    client, me, src = bank
    pid = await product_id("히어로 정기예금")
    first = await client.post("/accounts/deposits", json=body(src, pid), headers=me)
    again = await client.post("/accounts/deposits", json=body(src, pid), headers=me)
    assert again.status_code == 200 and again.json()["data"]["action_id"] == first.json()["data"]["action_id"]
    other = await client.post("/accounts/deposits", json=body(src, pid, amount=1_500_000), headers=me)
    assert other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    wrong = await client.post("/accounts/deposits", json=body(src, await product_id("스타크 자유적금"), key="dep-wrong-01"), headers=me)
    assert wrong.json()["error"]["code"] == "PRODUCT_NOT_OPENABLE"
