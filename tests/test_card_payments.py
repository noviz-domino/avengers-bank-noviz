import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.core.clock import KST
from avengers_bank.domains.accounts.models import AccountTransaction
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.cards.models import Card, CardTransaction
from avengers_bank.domains.users.models import User
from avengers_bank.seed import seed_card_products, seed_products
from tests.test_cards import issue
from tests.test_transfers import PIN, balance, open_account, user

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


def merchant_pay(client, card, key, *, terminal=None, headers=None, amount=12_000, merchant="테스트 가맹점"):
    return client.post(
        f"/system/card-payments/{card['card_id']}",
        headers=headers if headers is not None else {"X-System-Key": "test-system-key-test-system-key-0000"},
        json={
            "merchant_name": merchant, "amount": amount, "idempotency_key": key,
            "channel": "IN_PERSON" if terminal else "ONLINE", "terminal_location": terminal,
        },
    )


async def test_location_mismatch_holds_until_owner_pin_then_pays_once(bank):
    client, me, checking, debit, _ = bank
    peter = await user(client, "spidey", "피터")
    seoul = {"latitude": 37.57, "longitude": 126.98}
    busan = {"latitude": 35.18, "longitude": 129.08}
    location = {**seoul, "accuracy_m": 50, "observed_at": datetime.now(UTC).isoformat()}
    assert (await client.put("/cards/protection/location", json=location, headers=me)).status_code == 409
    assert (await client.put("/cards/protection", json={"location_check": True, "pin": PIN}, headers=me)).status_code == 200
    assert (await client.put("/cards/protection/location", json=location, headers=me)).status_code == 200
    assert (await merchant_pay(client, debit, "near-0001", terminal=seoul)).status_code == 201
    assert (await merchant_pay(client, debit, "far-00001", terminal=busan, headers=me)).status_code == 403
    assert (await pay(client, me, debit)).json()["error"]["code"] == "MERCHANT_CHANNEL_REQUIRED"

    held = await merchant_pay(client, debit, "far-00001", terminal=busan)
    assert held.status_code == 202
    action = held.json()["data"]
    assert (action["action_type"], action["requested_by"], action["status"]) == ("CARD_PAYMENT", "SYSTEM", "PENDING")
    assert "위치 불일치" in action["summary"]
    replay = await merchant_pay(client, debit, "far-00001", terminal=seoul)
    assert replay.status_code == 202 and replay.json()["data"]["action_id"] == action["action_id"]
    assert await balance(checking["account_id"]) == 1_988_000
    path = f"/approvals/{action['action_id']}/approve"
    assert (await client.post(path, json={"pin": PIN}, headers=peter)).status_code == 404
    assert (await client.post(path, json={"pin": "999999"}, headers=me)).status_code == 400
    approved = await client.post(path, json={"pin": PIN}, headers=me)
    assert approved.status_code == 200 and approved.json()["data"]["status"] == "EXECUTED"
    assert (await client.post(path, json={"pin": PIN}, headers=me)).status_code == 409
    replay = await merchant_pay(client, debit, "far-00001", terminal=busan)
    assert replay.status_code == 200
    assert replay.json()["data"]["card_tx_id"] == approved.json()["data"]["result"]["card_tx_id"]
    assert await balance(checking["account_id"]) == 1_976_000


async def test_online_outside_activity_rejection_and_expiry_prevent_charge(bank):
    client, me, checking, debit, _ = bank
    now = datetime.now(KST)
    start, end = ((now + timedelta(hours=hours)).strftime("%H:%M") for hours in (1, 2))
    settings = {"active_from": start, "active_until": end, "pin": PIN}
    assert (await client.put("/cards/protection", json=settings, headers=me)).status_code == 200
    for key in ("night-0001", "night-0002"):
        held = await merchant_pay(client, debit, key)
        assert held.status_code == 202
        action = held.json()["data"]
        assert "활동시간 외" in action["summary"]
        path = f"/approvals/{action['action_id']}"
        if key == "night-0001":
            assert (await client.post(path + "/reject", headers=me)).json()["data"]["status"] == "REJECTED"
        else:
            async with SessionLocal.begin() as db:
                await db.execute(update(PendingAction).where(
                    PendingAction.action_id == uuid.UUID(action["action_id"])
                ).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        assert (await client.post(path + "/approve", json={"pin": PIN}, headers=me)).status_code == 409
        assert (await merchant_pay(client, debit, key)).status_code == 409
    assert await balance(checking["account_id"]) == 2_000_000
    assert await ledger(checking["account_id"]) == []
    start, end = ((now + timedelta(hours=hours)).strftime("%H:%M") for hours in (-1, 1))
    assert (await client.put(
        "/cards/protection", json={"active_from": start, "active_until": end, "pin": PIN}, headers=me
    )).status_code == 200
    assert (await merchant_pay(client, debit, "active-001")).status_code == 201


async def test_mobile_activity_allows_ordinary_online_payment_but_does_not_clear_other_risk(bank):
    client, me, checking, debit, _ = bank
    now = datetime.now(KST)
    start, end = ((now + timedelta(hours=hours)).strftime("%H:%M") for hours in (1, 2))
    settings = {"active_from": start, "active_until": end, "pin": PIN}
    assert (await client.put("/cards/protection", json=settings, headers=me)).status_code == 200
    before = await merchant_pay(client, debit, "no-signal-01")
    assert before.status_code == 202
    assert (await client.put("/cards/protection/activity")).status_code == 401
    assert (await client.put("/cards/protection/activity", headers=me)).status_code == 200

    replay = await merchant_pay(client, debit, "no-signal-01")
    assert replay.status_code == 202 and replay.json()["data"]["action_id"] == before.json()["data"]["action_id"]
    assert (await merchant_pay(client, debit, "has-signal-01")).status_code == 201
    unfamiliar = await merchant_pay(client, debit, "unusual-01", amount=500_000, merchant="처음 보는 온라인몰")
    assert unfamiliar.status_code == 202 and "고액 온라인 결제" in unfamiliar.json()["data"]["summary"]
    assert (await merchant_pay(client, debit, "familiar-01", amount=500_000)).status_code == 201
    assert await balance(checking["account_id"]) == 1_488_000

    async with SessionLocal.begin() as db:
        customer = await db.scalar(select(User).where(User.login_id == "ironman"))
        customer.card_protection = customer.card_protection | {
            "activity_at": (datetime.now(UTC) - timedelta(minutes=6)).isoformat(),
        }
    assert (await merchant_pay(client, debit, "old-signal-01")).status_code == 202


async def test_recent_phone_movement_can_allow_online_but_offline_location_still_matters(bank):
    client, me, _, debit, _ = bank
    now = datetime.now(UTC)
    start, end = ((now.astimezone(KST) + timedelta(hours=hours)).strftime("%H:%M") for hours in (1, 2))
    assert (await client.put("/cards/protection", json={
        "location_check": True, "active_from": start, "active_until": end, "pin": PIN,
    }, headers=me)).status_code == 200
    location = {"latitude": 37.57, "longitude": 126.98, "accuracy_m": 50}
    for minutes in (2, 1):
        assert (await client.put("/cards/protection/location", headers=me, json={
            **location, "observed_at": (now - timedelta(minutes=minutes)).isoformat(),
        })).status_code == 200
    assert (await merchant_pay(client, debit, "stationary-01")).status_code == 202
    assert (await client.put("/cards/protection/location", headers=me, json={
        **location, "latitude": 37.61, "observed_at": now.isoformat(),
    })).status_code == 200
    assert (await merchant_pay(client, debit, "moving-01")).status_code == 201
    assert (await merchant_pay(client, debit, "far-while-moving", terminal={
        "latitude": 35.18, "longitude": 129.08,
    })).status_code == 202


async def test_offline_without_fresh_location_requires_confirmation(bank):
    client, me, checking, debit, _ = bank
    assert (await client.put("/cards/protection", json={"location_check": True, "pin": PIN}, headers=me)).status_code == 200
    seoul = {"latitude": 37.57, "longitude": 126.98}
    stale = {**seoul, "accuracy_m": 50, "observed_at": (datetime.now(UTC) - timedelta(minutes=16)).isoformat()}
    assert (await client.put("/cards/protection/location", json=stale, headers=me)).status_code == 400
    held = await merchant_pay(client, debit, "stale-0001", terminal=seoul)
    assert held.status_code == 202 and "최근 스마트폰 위치 없음" in held.json()["data"]["summary"]
    action_id = held.json()["data"]["action_id"]
    assert (await client.post(f"/cards/{debit['card_id']}/suspend", json={}, headers=me)).status_code == 200
    failed = await client.post(f"/approvals/{action_id}/approve", json={"pin": PIN}, headers=me)
    assert failed.status_code == 400 and failed.json()["error"]["code"] == "CARD_NOT_ACTIVE"
    assert (await client.get(f"/approvals/{action_id}", headers=me)).json()["data"]["status"] == "FAILED"
    assert await balance(checking["account_id"]) == 2_000_000


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


async def test_search_card_transactions_across_my_cards(bank):
    # 카드 탭의 카드 검색: 내 모든 카드에서 가맹점·카테고리·기간으로 찾고, 합계는 승인 건만 (취소 제외)
    client, me, _, debit, credit = bank
    coffee = (await pay(client, me, debit, 5_000, "search-01", "스타벅스 강남점")).json()["data"]
    await pay(client, me, credit, 30_000, "search-02", "스타벅스 역삼점")
    await pay(client, me, credit, 9_000, "search-03", "GS25 편의점")
    await cancel(client, me, debit, coffee)

    found = (await client.get("/cards/transactions", params={"keyword": "스타벅스"}, headers=me)).json()["data"]
    assert [t["merchant_name"] for t in found["transactions"]] == ["스타벅스 역삼점", "스타벅스 강남점"]  # 최근 것부터
    assert found["count"] == 2 and found["total_amount"] == 30_000  # 취소한 5,000원은 합계에서 빠짐

    only_credit = (await client.get("/cards/transactions", params={"card_id": credit["card_id"]}, headers=me)).json()["data"]
    assert only_credit["count"] == 2 and only_credit["total_amount"] == 39_000

    other = await user(client, "spidey", "피터")
    assert (await client.get("/cards/transactions", headers=other)).json()["data"]["count"] == 0  # 남의 카드는 안 보임
    assert (await client.get("/cards/transactions", params={"card_id": credit["card_id"]}, headers=other)).json()["data"]["count"] == 0

    bad = await client.get("/cards/transactions", params={"from_date": "2026-11-12", "to_date": "2026-11-01"}, headers=me)
    assert bad.status_code == 422
    typo = await client.get("/cards/transactions", params={"keywrd": "x"}, headers=me)
    assert typo.status_code == 422  # 오타 조건을 조용히 무시하지 않음
