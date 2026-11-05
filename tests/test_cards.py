import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.cards.card_number import is_valid, make_card_num, mask
from avengers_bank.domains.cards.models import Card, CardProduct
from avengers_bank.seed import seed_card_products, seed_products
from tests.test_transfers import PIN, open_account, user

pytestmark = pytest.mark.anyio


async def card_product_id(type_: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(CardProduct.product_id).where(CardProduct.type == type_))


@pytest.fixture
async def bank(client):
    async with SessionLocal() as db:
        await seed_products(db)
    async with SessionLocal() as db:
        await seed_card_products(db)
    tony = await user(client, "ironman", "토니")
    checking = await open_account(client, tony)
    return client, tony, checking


async def issue(client, me, account, type_="DEBIT", **kw):
    return await client.post("/cards", json={"product_id": await card_product_id(type_),
                                              "linked_account_id": account["account_id"], **kw}, headers=me)


def test_card_number_rules():
    num = make_card_num("CREDIT", 1, 7)
    assert num.startswith("9410101") and len(num) == 16 and is_valid(num)
    assert not is_valid(num[:-1] + str((int(num[-1]) + 1) % 10))  # 한 자리 오타
    assert is_valid("4111111111111111")  # 잘 알려진 Luhn 예시 번호
    assert mask(num) == f"9410-10**-****-{num[12:]}"


async def test_issue_debit_and_credit(bank):
    client, me, checking = bank
    debit = (await issue(client, me, checking, nickname="생활카드")).json()["data"]
    credit = (await issue(client, me, checking, "CREDIT", payment_day=25)).json()["data"]
    assert (debit["card_type"], debit["daily_limit"], debit["monthly_limit"], debit["payment_day"]) == ("DEBIT", 1_000_000, None, None)
    assert (credit["card_type"], credit["monthly_limit"], credit["payment_day"]) == ("CREDIT", 3_000_000, 25)
    assert debit["masked_card_num"].startswith("9410-20**-****-") and "card_num" not in debit  # 전체 번호는 안 나감
    second = (await issue(client, me, checking)).json()["data"]
    async with SessionLocal() as db:
        nums = list(await db.scalars(select(Card.card_num).order_by(Card.card_id)))
    assert [n[7:15] for n in nums] == ["00000001", "00000001", "00000002"] and all(map(is_valid, nums))
    assert len((await client.get("/cards", headers=me)).json()["data"]) == 3
    assert second["card_id"] != debit["card_id"]


async def test_credit_default_payment_day_and_products(bank):
    client, me, checking = bank
    assert (await issue(client, me, checking, "CREDIT")).json()["data"]["payment_day"] == 14
    products = (await client.get("/products/cards", params={"type": "CREDIT"})).json()["data"]
    assert [p["name"] for p in products] == ["스타크 신용카드"]


async def test_linked_account_must_be_my_checking(bank):
    client, me, _ = bank
    savings = await open_account(client, me, "스타크 자유적금", term_months=12, monthly_payment=100_000)
    other = await user(client, "spidey", "피터")
    others = await open_account(client, other)
    for account in [savings, others]:
        response = await issue(client, me, account)
        assert response.status_code == 400 and response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


async def test_suspend_now_unsuspend_with_pin(bank):
    client, me, checking = bank
    card = (await issue(client, me, checking)).json()["data"]
    suspended = (await client.post(f"/cards/{card['card_id']}/suspend", json={}, headers=me)).json()["data"]
    assert suspended["status"] == "SUSPENDED"  # 바로

    response = await client.post(f"/cards/{card['card_id']}/unsuspend", json={"idempotency_key": "unsuspend-1"}, headers=me)
    assert response.status_code == 202
    action = response.json()["data"]
    assert action["action_type"] == "UNSUSPEND_CARD" and "정지 풀기" in action["summary"]
    assert (await client.get(f"/cards/{card['card_id']}", headers=me)).json()["data"]["status"] == "SUSPENDED"  # 승인 전

    await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert (await client.get(f"/cards/{card['card_id']}", headers=me)).json()["data"]["status"] == "ACTIVE"


async def test_lost_cannot_come_back(bank):
    client, me, checking = bank
    card = (await issue(client, me, checking)).json()["data"]
    url = f"/cards/{card['card_id']}"
    await client.post(f"{url}/suspend", json={}, headers=me)
    action = (await client.post(f"{url}/unsuspend", json={"idempotency_key": "unsuspend-2"}, headers=me)).json()["data"]
    await client.post(f"{url}/suspend", json={"reason": "LOST"}, headers=me)  # 승인 전에 분실 신고

    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert response.json()["error"]["code"] == "CARD_NOT_SUSPENDED"  # 분실 카드는 승인해도 안 풀림
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "LOST"
    assert (await client.post(f"{url}/unsuspend", json={"idempotency_key": "unsuspend-3"}, headers=me)).json()["error"]["code"] == "CARD_LOST"
    assert (await client.post(f"{url}/suspend", json={}, headers=me)).json()["error"]["code"] == "CARD_LOST"


async def test_other_users_card_is_not_found(bank):
    client, me, checking = bank
    card = (await issue(client, me, checking)).json()["data"]
    other = await user(client, "spidey", "피터")
    for method, path, body in [("get", "", None), ("post", "/suspend", {}), ("post", "/unsuspend", {"idempotency_key": "x-unsuspend"})]:
        response = await getattr(client, method)(f"/cards/{card['card_id']}{path}", headers=other, **({"json": body} if body is not None else {}))
        assert response.status_code == 404 and response.json()["error"]["code"] == "CARD_NOT_FOUND"


async def test_db_rejects_debit_with_credit_terms(bank):
    client, me, checking = bank
    async with SessionLocal() as db:
        db.add(Card(user_id=1, product_id=await card_product_id("DEBIT"), linked_account_id=checking["account_id"],
                    card_type="DEBIT", card_num=make_card_num("DEBIT", 1, 99), daily_limit=1, monthly_limit=10, status="ACTIVE"))
        with pytest.raises(IntegrityError):
            await db.commit()
