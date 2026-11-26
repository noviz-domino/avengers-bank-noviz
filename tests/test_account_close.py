import uuid

import pytest
from sqlalchemy import select

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.audit.models import AuditLog

from tests.test_card_bills import KEY, run, set_balance, today_is_2030  # noqa: F401  today_is_2030은 fixture
from tests.test_card_payments import bank, cancel, ledger, pay  # noqa: F401  bank는 fixture
from tests.test_cards import issue
from tests.test_transfers import PIN, balance, open_account, user

pytestmark = pytest.mark.anyio


async def approved(client, me, requested):
    """승인 대기를 만든 요청이면 PIN으로 승인한 응답을, 신청에서 막혔으면 그 응답을 돌려준다 (ADR 0033)"""
    if requested.status_code not in (200, 202):
        return requested
    return await client.post(f"/approvals/{requested.json()['data']['action_id']}/approve", json={"pin": PIN}, headers=me)


def request_close(client, me, account, **headers):
    key = {"idempotency_key": f"close-{uuid.uuid4().hex[:12]}"}
    return client.post(f"/accounts/{account['account_id']}/close", json=key, headers={**me, **headers})


async def close(client, me, account):
    return await approved(client, me, await request_close(client, me, account))


async def lost(client, me, card):
    key = {"idempotency_key": f"lost-{uuid.uuid4().hex[:12]}"}
    return await approved(client, me, await client.post(f"/cards/{card['card_id']}/report-lost", json=key, headers=me))


def code(res) -> str:
    return res.json()["error"]["code"]


async def test_close_empty_checking(bank):
    client, me, *_ = bank
    empty = await open_account(client, me)
    res = await close(client, me, empty)
    assert res.status_code == 200 and res.json()["data"]["status"] == "EXECUTED"
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


async def test_close_needs_pin_and_rechecks(bank):
    # 해지는 되돌릴 수 없어서 어느 입구든 PIN 승인 뒤에 (ADR 0033). 승인 사이에 돈이 들어오면 해지하지 않는다
    client, me, *_ = bank
    empty = await open_account(client, me)
    requested = await request_close(client, me, empty, **{"X-Requested-By": "MCP"})
    action = requested.json()["data"]
    assert requested.status_code == 202 and action["action_type"] == "CLOSE_ACCOUNT" and action["requested_by"] == "MCP"
    assert "되살릴 수 없어요" in action["summary"]
    listed = (await client.get("/accounts", headers=me)).json()["data"]["accounts"]
    assert empty["account_id"] in [a["account_id"] for a in listed]  # PIN 전에는 그대로

    await set_balance(empty["account_id"], 5_000)  # 승인 전에 돈이 들어옴
    res = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert code(res) == "BALANCE_REMAINING"
    assert (await client.get(f"/approvals/{action['action_id']}", headers=me)).json()["data"]["status"] == "FAILED"
    assert (await client.get(f"/accounts/{empty['account_id']}", headers=me)).json()["data"]["status"] == "ACTIVE"


async def test_report_lost_suspends_now_and_locks_after_pin(bank):
    # 분실 신고: 카드는 바로 일시정지(안전), 되돌릴 수 없는 분실 확정은 PIN 승인 뒤 (ADR 0033)
    client, me, checking, debit, _ = bank
    url = f"/cards/{debit['card_id']}"
    res = await client.post(f"{url}/report-lost", json={"idempotency_key": "lost-now-1"}, headers=me)
    action = res.json()["data"]
    assert res.status_code == 202 and action["action_type"] == "REPORT_LOST"
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "SUSPENDED"
    again = await client.post(f"{url}/report-lost", json={"idempotency_key": "lost-now-1"}, headers=me)
    assert again.status_code == 200 and again.json()["data"]["action_id"] == action["action_id"]  # 재전송은 대기 하나
    assert (await client.post(f"{url}/suspend", json={"reason": "LOST"}, headers=me)).status_code == 422  # 바로 분실은 없음

    await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "LOST"
    assert code(await client.post(f"{url}/report-lost", json={"idempotency_key": "lost-now-2"}, headers=me)) == "CARD_LOST"


async def test_close_request_is_idempotent(bank):
    client, me, *_ = bank
    empty, other = await open_account(client, me), await open_account(client, me)
    body = {"idempotency_key": "close-same-key"}
    first = await client.post(f"/accounts/{empty['account_id']}/close", json=body, headers=me)
    again = await client.post(f"/accounts/{empty['account_id']}/close", json=body, headers=me)
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["data"]["action_id"] == first.json()["data"]["action_id"]  # 재전송은 대기 하나
    assert code(await client.post(f"/accounts/{other['account_id']}/close", json=body, headers=me)) == "IDEMPOTENCY_KEY_REUSED"


async def test_card_issued_after_close_request_blocks_close(bank):
    # 신청 뒤 승인 전에 그 계좌로 카드가 생기면 PIN을 넣어도 해지하지 않는다 (ADR 0033)
    client, me, *_ = bank
    empty = await open_account(client, me)
    action = (await request_close(client, me, empty)).json()["data"]
    assert (await issue(client, me, empty)).status_code == 201
    res = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert code(res) == "LINKED_CARD_EXISTS"
    assert (await client.get(f"/accounts/{empty['account_id']}", headers=me)).json()["data"]["status"] == "ACTIVE"


async def test_rejected_lost_report_leaves_card_suspended(bank):
    # 분실 신청을 거절하면 카드는 일시정지로 남고 정지 해제(PIN)로 되살릴 수 있다
    client, me, checking, debit, _ = bank
    url = f"/cards/{debit['card_id']}"
    action = (await client.post(f"{url}/report-lost", json={"idempotency_key": "lost-reject-1"}, headers=me)).json()["data"]
    await client.post(f"/approvals/{action['action_id']}/reject", headers=me)
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "SUSPENDED"
    assert (await approved(client, me, await client.post(f"{url}/unsuspend", json={"idempotency_key": "unsuspend-after-reject"}, headers=me))).status_code == 200
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "ACTIVE"


async def test_unsuspend_blocked_while_lost_report_waits(bank):
    # 분실 신청은 카드를 정지만 해 둔다. 확정 전에 정지 해제가 승인되면 잃어버린 카드가 다시 결제된다 (리뷰 지적)
    client, me, checking, debit, _ = bank
    url = f"/cards/{debit['card_id']}"
    await client.post(f"{url}/suspend", json={}, headers=me)
    unsuspend = (await client.post(f"{url}/unsuspend", json={"idempotency_key": "unsuspend-before-lost"}, headers=me)).json()["data"]
    await client.post(f"{url}/report-lost", json={"idempotency_key": "lost-after-unsuspend"}, headers=me)
    res = await client.post(f"/approvals/{unsuspend['action_id']}/approve", json={"pin": PIN}, headers=me)
    assert code(res) == "CARD_LOST_PENDING"
    assert (await client.get(url, headers=me)).json()["data"]["status"] == "SUSPENDED"
    blocked = await client.post(f"{url}/unsuspend", json={"idempotency_key": "unsuspend-while-lost"}, headers=me)
    assert blocked.status_code == 409 and code(blocked) == "CARD_LOST_PENDING"


async def test_others_card_report_lost_is_404_and_changes_nothing(bank):
    client, me, checking, debit, _ = bank
    peter = await user(client, "spidey", "피터")
    res = await client.post(f"/cards/{debit['card_id']}/report-lost", json={"idempotency_key": "lost-not-mine"}, headers=peter)
    assert res.status_code == 404 and code(res) == "CARD_NOT_FOUND"
    assert (await client.get(f"/cards/{debit['card_id']}", headers=me)).json()["data"]["status"] == "ACTIVE"
    async with SessionLocal() as db:
        assert (await db.scalars(select(AuditLog).where(AuditLog.target == str(debit["card_id"])))).all() == []
