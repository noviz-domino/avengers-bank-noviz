from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import AccountTransaction
from avengers_bank.domains.cards.models import Card, CardTransaction
from avengers_bank.seed import seed_card_products, seed_products
from tests.test_cards import issue
from tests.test_transfers import balance, open_account, user

pytestmark = pytest.mark.anyio


@pytest.fixture
async def bank(client):
    async with SessionLocal() as db:
        await seed_products(db)
    async with SessionLocal() as db:
        await seed_card_products(db)
    tony = await user(client, "ironman", "토니")
    checking = await open_account(client, tony, balance=2_000_000)
    debit = (await issue(client, tony, checking)).json()["data"]
    credit = (await issue(client, tony, checking, type_="CREDIT")).json()["data"]
    return client, tony, checking, debit, credit


def pay(client, me, card, amount=12_000, key="pay-00000001", merchant="스타벅스 강남점"):
    return client.post(f"/cards/{card['card_id']}/payments",
                       json={"merchant_name": merchant, "amount": amount, "idempotency_key": key}, headers=me)


def cancel(client, me, card, tx):
    return client.post(f"/cards/{card['card_id']}/transactions/{tx['card_tx_id']}/cancel", headers=me)


async def ledger(account_id: int) -> list[tuple[str, int, str]]:
    async with SessionLocal() as db:
        rows = await db.scalars(select(AccountTransaction).where(AccountTransaction.account_id == account_id)
                                .order_by(AccountTransaction.tx_id))
        return [(t.tx_type, t.amount, t.category) for t in rows]


async def test_debit_pays_from_account_once(bank):
    client, me, checking, debit, _ = bank
    res = await pay(client, me, debit)
    assert res.status_code == 201
    tx = res.json()["data"]
    assert (tx["status"], tx["billing_status"], tx["category"]) == ("APPROVED", None, "카페·간식")
    again = await pay(client, me, debit)  # 가맹점이 다시 보냄
    assert again.status_code == 200 and again.json()["data"]["card_tx_id"] == tx["card_tx_id"]
    assert again.json()["message"] == "이미 처리된 결제 요청입니다."
    assert await balance(checking["account_id"]) == 1_988_000
    assert await ledger(checking["account_id"]) == [("CARD_PAYMENT", -12_000, "카페·간식")]
    reused = await pay(client, me, debit, amount=99_000)
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_debit_needs_balance(bank):
    client, me, checking, debit, _ = bank
    res = await pay(client, me, debit, amount=2_000_001)
    assert res.status_code == 400 and res.json()["error"]["code"] in ("INSUFFICIENT_BALANCE", "CARD_DAILY_LIMIT_EXCEEDED")
    async with SessionLocal() as db:
        await db.execute(update(Card).where(Card.card_id == debit["card_id"]).values(daily_limit=5_000_000))
        await db.commit()
    res = await pay(client, me, debit, amount=2_000_001)
    assert res.status_code == 400 and res.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert await balance(checking["account_id"]) == 2_000_000
    assert (await client.get(f"/cards/{debit['card_id']}/transactions", headers=me)).json()["data"] == []


async def test_daily_limit_and_cancel_gives_it_back(bank):
    client, me, checking, debit, _ = bank
    first = (await pay(client, me, debit, amount=900_000, key="pay-00000001")).json()["data"]
    over = await pay(client, me, debit, amount=200_000, key="pay-00000002")
    assert over.status_code == 400 and over.json()["error"]["code"] == "CARD_DAILY_LIMIT_EXCEEDED"
    assert "100,000원" in over.json()["error"]["message"]

    res = await cancel(client, me, debit, first)
    assert res.status_code == 200 and res.json()["data"]["status"] == "CANCELED"
    assert await balance(checking["account_id"]) == 2_000_000
    assert (await ledger(checking["account_id"]))[-1] == ("REFUND", 900_000, "카페·간식")  # 쓴 업종 그대로
    again = await cancel(client, me, debit, first)
    assert again.status_code == 409 and again.json()["error"]["code"] == "CARD_TX_ALREADY_CANCELED"
    assert (await pay(client, me, debit, amount=200_000, key="pay-00000003")).status_code == 201
    limits = (await client.get(f"/cards/{debit['card_id']}/limits", headers=me)).json()["data"]
    assert limits == {"daily_limit": 1_000_000, "daily_used": 200_000, "credit_limit": None, "credit_used": None}


async def test_credit_records_use_within_unpaid_limit(bank):
    client, me, checking, _, credit = bank
    async with SessionLocal() as db:
        await db.execute(update(Card).where(Card.card_id == credit["card_id"]).values(credit_limit=1_200_000))
        await db.commit()
    tx = (await pay(client, me, credit, amount=800_000, key="pay-00000001")).json()["data"]
    assert tx["billing_status"] == "UNBILLED"
    assert await balance(checking["account_id"]) == 2_000_000  # 돈은 대금 출금일에
    assert await ledger(checking["account_id"]) == []
    async with SessionLocal() as db:  # 어제 쓴 것으로: 1일 한도와 떼어서 날을 넘겨 쌓이는 금액만 본다
        await db.execute(update(CardTransaction).where(CardTransaction.card_tx_id == tx["card_tx_id"])
                         .values(approved_at=datetime.now(UTC) - timedelta(days=1)))
        await db.commit()
    assert (await pay(client, me, credit, amount=250_000, key="pay-00000003")).status_code == 201
    # 오늘 쓴 금액(25만+40만)은 1일 한도 안이지만, 안 갚은 금액이 신용 한도(120만)를 넘는다
    over = await pay(client, me, credit, amount=400_000, key="pay-00000004")
    assert over.status_code == 400 and over.json()["error"]["code"] == "CREDIT_LIMIT_EXCEEDED"
    limits = (await client.get(f"/cards/{credit['card_id']}/limits", headers=me)).json()["data"]
    assert (limits["credit_limit"], limits["credit_used"]) == (1_200_000, 1_050_000)

    assert (await cancel(client, me, credit, tx)).status_code == 200
    limits = (await client.get(f"/cards/{credit['card_id']}/limits", headers=me)).json()["data"]
    assert limits["credit_used"] == 250_000 and await ledger(checking["account_id"]) == []


async def test_stopped_card_cannot_pay_but_can_cancel(bank):
    client, me, checking, debit, _ = bank
    tx = (await pay(client, me, debit)).json()["data"]
    await client.post(f"/cards/{debit['card_id']}/suspend", json={"reason": "LOST"}, headers=me)
    res = await pay(client, me, debit, key="pay-00000002")
    assert res.status_code == 409 and res.json()["error"]["code"] == "CARD_NOT_ACTIVE"
    assert (await pay(client, me, debit)).status_code == 200  # 분실 전 결제의 재전송은 처음 결과
    assert (await cancel(client, me, debit, tx)).status_code == 200
    assert await balance(checking["account_id"]) == 2_000_000


async def test_others_card_and_tx_are_404(bank):
    client, me, checking, debit, credit = bank
    peter = await user(client, "spidey", "피터")
    tx = (await pay(client, me, debit)).json()["data"]
    for res in [
        await pay(client, peter, debit, key="pay-00000009"),
        await cancel(client, peter, debit, tx),
        await client.get(f"/cards/{debit['card_id']}/transactions", headers=peter),
        await client.get(f"/cards/{debit['card_id']}/limits", headers=peter),
    ]:
        assert res.status_code == 404 and res.json()["error"]["code"] == "CARD_NOT_FOUND"
    wrong_card = await cancel(client, me, credit, tx)  # 다른 카드의 사용내역
    assert wrong_card.status_code == 404 and wrong_card.json()["error"]["code"] == "CARD_TX_NOT_FOUND"
    assert await balance(checking["account_id"]) == 1_988_000
