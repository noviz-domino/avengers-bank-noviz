from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.cards.models import CardTransaction
from tests.test_card_payments import bank, cancel, ledger, pay  # noqa: F401  bank는 fixture
from tests.test_transfers import balance

pytestmark = pytest.mark.anyio

KEY = {"X-System-Key": "test-system-key-test-system-key-0000"}
PAY_DAY = "2030-01-14"  # 신용카드 기본 결제일 14일. 테스트에서 오늘 결제한 것은 모두 이 날 전에 쓴 것


async def run(client, day=PAY_DAY, headers=KEY):
    return await client.post(f"/system/card-bills/run?run_date={day}", headers=headers)


async def billing(card_tx_id: int) -> str:
    async with SessionLocal() as db:
        return await db.scalar(select(CardTransaction.billing_status).where(CardTransaction.card_tx_id == card_tx_id))


async def set_balance(account_id: int, amount: int) -> None:
    async with SessionLocal() as db:
        await db.execute(update(Account).where(Account.account_id == account_id).values(balance=amount))
        await db.commit()


async def test_pays_used_amount_once(bank):
    client, me, checking, _, credit = bank
    a = (await pay(client, me, credit, amount=100_000, key="pay-00000001")).json()["data"]
    b = (await pay(client, me, credit, amount=50_000, key="pay-00000002")).json()["data"]
    res = (await run(client)).json()["data"]
    assert (res["paid_cards"], res["overdue_cards"], res["total_paid"]) == (1, 0, 150_000)
    assert await balance(checking["account_id"]) == 1_850_000
    assert await ledger(checking["account_id"]) == [("CARD_BILL", -150_000, "카드 대금")]
    assert [await billing(t["card_tx_id"]) for t in (a, b)] == ["PAID", "PAID"]
    again = (await run(client)).json()["data"]  # 같은 날 두 번 불러도
    assert (again["paid_cards"], again["total_paid"]) == (0, 0)
    assert await balance(checking["account_id"]) == 1_850_000
    limits = (await client.get(f"/cards/{credit['card_id']}/limits", headers=me)).json()["data"]
    assert limits["credit_used"] == 0  # 갚으면 한도가 돌아온다


async def test_only_on_payment_day_and_only_before_it(bank):
    client, me, checking, _, credit = bank
    early = (await pay(client, me, credit, amount=10_000, key="pay-00000001")).json()["data"]
    today = (await pay(client, me, credit, amount=20_000, key="pay-00000002")).json()["data"]
    assert (await run(client, day="2030-01-13")).json()["data"]["paid_cards"] == 0  # 결제일 아님
    async with SessionLocal() as db:  # 결제일 당일 오전(한국 10시)에 쓴 것
        await db.execute(update(CardTransaction).where(CardTransaction.card_tx_id == today["card_tx_id"])
                         .values(approved_at=datetime(2030, 1, 14, 1, tzinfo=UTC)))
        await db.commit()
    assert (await run(client)).json()["data"]["total_paid"] == 10_000
    assert (await billing(early["card_tx_id"]), await billing(today["card_tx_id"])) == ("PAID", "UNBILLED")


async def test_overdue_blocks_payments_until_paid(bank):
    client, me, checking, _, credit = bank
    await set_balance(checking["account_id"], 100_000)
    tx = (await pay(client, me, credit, amount=150_000, key="pay-00000001")).json()["data"]
    res = (await run(client)).json()["data"]
    assert (res["paid_cards"], res["overdue_cards"]) == (0, 1)
    assert await balance(checking["account_id"]) == 100_000  # 전액이 안 되면 출금하지 않음
    assert await billing(tx["card_tx_id"]) == "BILLED"
    blocked = await pay(client, me, credit, amount=1_000, key="pay-00000002")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CARD_OVERDUE"

    await set_balance(checking["account_id"], 200_000)
    res = (await run(client, day="2030-01-15")).json()["data"]  # 결제일이 아니어도 연체는 다시 시도
    assert (res["paid_cards"], res["total_paid"]) == (1, 150_000)
    assert await balance(checking["account_id"]) == 50_000
    assert (await pay(client, me, credit, amount=1_000, key="pay-00000003")).status_code == 201


async def test_cancel_after_bill(bank):
    client, me, checking, _, credit = bank
    await set_balance(checking["account_id"], 0)
    owed = (await pay(client, me, credit, amount=30_000, key="pay-00000001")).json()["data"]
    await run(client)  # 잔액 0 → 연체
    assert (await cancel(client, me, credit, owed)).status_code == 200  # 안 낸 것은 기록만 취소
    assert await ledger(checking["account_id"]) == []

    await set_balance(checking["account_id"], 100_000)
    paid = (await pay(client, me, credit, amount=40_000, key="pay-00000002")).json()["data"]
    await run(client, day="2030-02-14")
    assert await balance(checking["account_id"]) == 60_000
    assert (await cancel(client, me, credit, paid)).status_code == 200  # 이미 낸 것은 환불
    assert await balance(checking["account_id"]) == 100_000
    assert (await ledger(checking["account_id"]))[-1] == ("REFUND", 40_000, "카페·간식")


async def test_needs_system_key(bank):
    client, me, *_ = bank
    for headers in [{}, {"X-System-Key": "wrong"}, me]:
        res = await run(client, headers=headers)
        assert res.status_code == 403 and res.json()["error"]["code"] == "SYSTEM_KEY_INVALID"
