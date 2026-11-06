import pytest
from sqlalchemy import select

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.audit.models import AuditLog

from tests.test_card_bills import KEY, run, set_balance, today_is_2030  # noqa: F401  today_is_2030은 fixture
from tests.test_card_payments import bank, cancel, ledger, pay  # noqa: F401  bank는 fixture
from tests.test_cards import issue
from tests.test_transfers import balance, open_account, user

pytestmark = pytest.mark.anyio


def close(client, me, account):
    return client.post(f"/accounts/{account['account_id']}/close", headers=me)


def lost(client, me, card):
    return client.post(f"/cards/{card['card_id']}/suspend", json={"reason": "LOST"}, headers=me)


def code(res) -> str:
    return res.json()["error"]["code"]


async def test_close_empty_checking(bank):
    client, me, *_ = bank
    empty = await open_account(client, me)
    res = await close(client, me, empty)
    assert res.status_code == 200 and res.json()["data"]["status"] == "CLOSED"
    listed = (await client.get("/accounts", headers=me)).json()["data"]["accounts"]
    assert empty["account_id"] not in [a["account_id"] for a in listed]
    assert code(await close(client, me, empty)) == "ACCOUNT_NOT_ACTIVE"
    # 해지한 계좌로는 카드를 발급할 수 없다
    assert code(await issue(client, me, empty)) == "ACCOUNT_NOT_FOUND"


async def test_close_rules(bank):
    client, me, checking, debit, credit = bank
    assert code(await close(client, me, checking)) == "BALANCE_REMAINING"
    await set_balance(checking["account_id"], 0)
    assert code(await close(client, me, checking)) == "LINKED_CARD_EXISTS"  # 쓸 수 있는 카드가 연결돼 있음
    peter = await user(client, "spidey", "피터")
    assert code(await close(client, peter, checking)) == "ACCOUNT_NOT_FOUND"  # 남의 계좌는 404
    savings = await open_account(client, me, name="스타크 자유적금", term_months=12, monthly_payment=100_000, payment_day=25)
    assert code(await close(client, me, savings)) == "ACCOUNT_CANNOT_CLOSE"


async def test_unpaid_credit_blocks_even_if_lost(bank):
    client, me, checking, debit, credit = bank
    await pay(client, me, credit, amount=30_000)
    await lost(client, me, debit)
    await lost(client, me, credit)
    await set_balance(checking["account_id"], 0)
    assert code(await close(client, me, checking)) == "CARD_UNPAID"
    await set_balance(checking["account_id"], 30_000)
    await run(client)  # 대금을 내면
    assert await balance(checking["account_id"]) == 0
    assert (await close(client, me, checking)).status_code == 200


async def test_refund_after_close_waits_for_agent(bank):
    client, me, checking, debit, credit = bank
    other = await open_account(client, me)
    tx = (await pay(client, me, debit, amount=12_000)).json()["data"]
    await lost(client, me, debit)
    await lost(client, me, credit)
    await set_balance(checking["account_id"], 0)
    assert (await close(client, me, checking)).status_code == 200

    res = await cancel(client, me, debit, tx)  # 가맹점이 해지 뒤에 취소
    assert res.status_code == 200 and res.json()["data"]["refund_pending"] is True
    assert "상담원" in res.json()["message"]
    assert await balance(checking["account_id"]) == 0  # 해지 계좌로는 넣지 않음

    pending = (await client.get("/system/card-refunds", headers=KEY)).json()["data"]
    assert [p["card_tx_id"] for p in pending] == [tx["card_tx_id"]]
    peter = await user(client, "spidey", "피터")
    peters = await open_account(client, peter)
    url = f"/system/card-refunds/{tx['card_tx_id']}"
    for wrong in (peters, checking):  # 남의 계좌, 해지한 계좌
        assert code(await client.post(url, json={"to_account_id": wrong["account_id"]}, headers=KEY)) == "ACCOUNT_NOT_FOUND"
    assert (await client.post(url, json={"to_account_id": other["account_id"]}, headers=me)).status_code == 403

    done = await client.post(url, json={"to_account_id": other["account_id"]}, headers=KEY)
    assert done.status_code == 200 and done.json()["data"]["refund_pending"] is False
    assert await balance(other["account_id"]) == 12_000
    assert await ledger(other["account_id"]) == [("REFUND", 12_000, "카페·간식")]
    again = await client.post(url, json={"to_account_id": other["account_id"]}, headers=KEY)
    assert code(again) == "REFUND_NOT_PENDING"
    assert (await client.get("/system/card-refunds", headers=KEY)).json()["data"] == []


async def test_pending_list_matches_property(bank):
    # 목록 쿼리(find_pending_refunds)와 응답의 refund_pending 계산이 같은 조건이어야 한다
    client, me, checking, debit, credit = bank
    other = await open_account(client, me)
    paid_debit = (await pay(client, me, debit, amount=1_000, key="pay-00000001")).json()["data"]
    unpaid_credit = (await pay(client, me, credit, amount=2_000, key="pay-00000002")).json()["data"]
    assert (await cancel(client, me, credit, unpaid_credit)).json()["data"]["refund_pending"] is False  # 돈이 안 나감
    paid_credit = (await pay(client, me, credit, amount=3_000, key="pay-00000003")).json()["data"]
    await run(client)  # 신용 3,000원 대금을 냄 → PAID
    await lost(client, me, debit)
    await lost(client, me, credit)
    await set_balance(checking["account_id"], 0)
    assert (await close(client, me, checking)).status_code == 200

    results = [(await cancel(client, me, c, t)).json()["data"] for c, t in ((debit, paid_debit), (credit, paid_credit))]
    assert [r["refund_pending"] for r in results] == [True, True]  # 체크, 낸 신용 모두 대기
    pending = (await client.get("/system/card-refunds", headers=KEY)).json()["data"]
    assert [p["card_tx_id"] for p in pending] == [paid_debit["card_tx_id"], paid_credit["card_tx_id"]]
    async with SessionLocal() as db:
        owner = await db.scalar(select(Account.user_id).where(Account.account_id == checking["account_id"]))
    assert {(p["user_id"], p["linked_account_id"]) for p in pending} == {(owner, checking["account_id"])}

    await client.post(f"/system/card-refunds/{paid_credit['card_tx_id']}", json={"to_account_id": other["account_id"]}, headers=KEY)
    async with SessionLocal() as db:
        log = await db.scalar(select(AuditLog).where(AuditLog.action == "CARD_REFUND_TO"))
    assert (log.actor, log.target, log.detail["amount"]) == ("SYSTEM", str(paid_credit["card_tx_id"]), 3_000)
