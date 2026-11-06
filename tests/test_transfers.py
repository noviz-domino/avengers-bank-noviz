import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import Account, AccountTransaction
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.audit.models import AuditLog
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.users.models import User
from avengers_bank.domains.users.repository import user_repository
from avengers_bank.seed import seed_products

pytestmark = pytest.mark.anyio
PIN = "123456"


async def user(client, login_id: str, name: str, pin: str | None = PIN) -> dict:
    await client.post("/users/signup", json={
        "login_id": login_id, "password": "password1234", "name": name, "phone": "010-1234-5678",
        "birth_date": "1990-05-29",
    })
    token = (await client.post("/users/login", json={"login_id": login_id, "password": "password1234"})).json()["data"]
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    if pin:
        assert (await client.put("/users/me/pin", json={"password": "password1234", "pin": pin}, headers=headers)).status_code == 200
    return headers


async def open_account(client, headers, name="캡아메리카 입출금통장", balance=0, **body) -> dict:
    async with SessionLocal() as db:
        pid = await db.scalar(select(AccountProduct.product_id).where(AccountProduct.name == name))
    account = (await client.post("/accounts", json={"product_id": pid, **body}, headers=headers)).json()["data"]
    if balance:
        async with SessionLocal() as db:
            await db.execute(update(Account).where(Account.account_id == account["account_id"]).values(balance=balance))
            await db.commit()
    return account


async def balance(account_id: int) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(Account.balance).where(Account.account_id == account_id))


@pytest.fixture
async def bank(client):
    async with SessionLocal() as db:
        await seed_products(db)
    tony = await user(client, "ironman", "토니")
    peter = await user(client, "spidey", "피터")
    src = await open_account(client, tony, balance=1_000_000)
    dst = await open_account(client, peter)
    return client, tony, peter, src, dst


def transfer(src, dst, amount=50_000, key="key-00000001", **kw):
    return {"from_account_id": src["account_id"], "to_account_num": dst["account_num"], "amount": amount,
            "idempotency_key": key, **kw}


async def test_transfer_waits_for_pin_then_moves_money(bank):
    client, tony, peter, src, dst = bank
    response = await client.post("/transfers", json=transfer(src, dst, memo="밥값"), headers=tony)
    assert response.status_code == 202
    action = response.json()["data"]
    assert action["status"] == "PENDING"
    assert action["summary"] == f"내 계좌({src['account_num']})에서 피터님({dst['account_num']})에게 50,000원 보내기"
    assert await balance(src["account_id"]) == 1_000_000  # 승인 전에는 그대로
    assert [a["action_id"] for a in (await client.get("/approvals", headers=tony)).json()["data"]] == [action["action_id"]]

    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=tony)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "EXECUTED"
    assert (await balance(src["account_id"]), await balance(dst["account_id"])) == (950_000, 50_000)

    async with SessionLocal() as db:
        rows = list(await db.scalars(select(AccountTransaction).order_by(AccountTransaction.tx_id)))
    out, in_ = rows
    assert (out.tx_type, out.amount, out.balance_after, out.counterparty_name) == ("TRANSFER_OUT", -50_000, 950_000, "피터")
    assert (in_.tx_type, in_.amount, in_.balance_after, in_.counterparty_name) == ("TRANSFER_IN", 50_000, 50_000, "토니")
    assert out.transfer_id == in_.transfer_id and str(out.action_id) == action["action_id"]


async def test_approve_twice_moves_money_once(bank):
    client, tony, _, src, dst = bank
    action = (await client.post("/transfers", json=transfer(src, dst), headers=tony)).json()["data"]
    await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=tony)
    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=tony)
    assert response.status_code == 409 and response.json()["error"]["code"] == "ACTION_NOT_PENDING"
    assert await balance(src["account_id"]) == 950_000


async def test_idempotency_key(bank):
    client, tony, _, src, dst = bank
    first = await client.post("/transfers", json=transfer(src, dst), headers=tony)
    again = await client.post("/transfers", json=transfer(src, dst), headers=tony)
    assert again.status_code == 200 and again.json()["data"]["action_id"] == first.json()["data"]["action_id"]
    other = await client.post("/transfers", json=transfer(src, dst, amount=60_000), headers=tony)
    assert other.status_code == 409 and other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_wrong_pin_locks_pin_not_login(bank):
    client, tony, _, src, dst = bank
    action = (await client.post("/transfers", json=transfer(src, dst), headers=tony)).json()["data"]
    url = f"/approvals/{action['action_id']}/approve"
    for left in [4, 3, 2, 1]:
        response = await client.post(url, json={"pin": "000000"}, headers=tony)
        assert response.json()["error"]["code"] == "INVALID_PIN"
        assert f"{left}번" in response.json()["error"]["message"]
    response = await client.post(url, json={"pin": "000000"}, headers=tony)
    assert response.status_code == 423 and response.json()["error"]["code"] == "PIN_LOCKED"
    assert (await client.post(url, json={"pin": PIN}, headers=tony)).status_code == 423  # 맞아도 잠김
    assert await balance(src["account_id"]) == 1_000_000

    login = await client.post("/users/login", json={"login_id": "ironman", "password": "password1234"})
    assert login.status_code == 200  # 로그인은 잠기지 않음 (ADR 0005)
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).where(AuditLog.action == "PIN_FAILED")) == 5


async def test_pin_rules(bank):
    client, _, _, src, dst = bank
    nopin = await user(client, "hulk", "브루스", pin=None)
    mine = await open_account(client, nopin, balance=10_000)
    action = (await client.post("/transfers", json=transfer(mine, dst, amount=1_000), headers=nopin)).json()["data"]
    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=nopin)
    assert response.json()["error"]["code"] == "PIN_NOT_SET"

    wrong = await client.put("/users/me/pin", json={"password": "nope", "pin": PIN}, headers=nopin)
    assert wrong.json()["error"]["code"] == "INVALID_PASSWORD"  # 토큰만으로는 PIN을 못 바꿈
    assert (await client.put("/users/me/pin", json={"password": "password1234", "pin": "12345"}, headers=nopin)).status_code == 422
    assert (await client.get("/users/me", headers=nopin)).json()["data"]["has_pin"] is False


async def test_failed_when_balance_changes_before_approval(bank):
    client, tony, _, src, dst = bank
    action = (await client.post("/transfers", json=transfer(src, dst, amount=900_000), headers=tony)).json()["data"]
    async with SessionLocal() as db:  # 요청과 승인 사이에 다른 출금이 있었다
        await db.execute(update(Account).where(Account.account_id == src["account_id"]).values(balance=100_000))
        await db.commit()

    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=tony)
    assert response.status_code == 400 and response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    detail = (await client.get(f"/approvals/{action['action_id']}", headers=tony)).json()["data"]
    assert detail["status"] == "FAILED" and detail["failure_reason"].startswith("INSUFFICIENT_BALANCE")
    assert (await balance(src["account_id"]), await balance(dst["account_id"])) == (100_000, 0)


@pytest.mark.parametrize("amount, code", [
    (1_000_001, "PER_TRANSFER_LIMIT_EXCEEDED"),  # 1회 한도 100만
    (2_000_000, "INSUFFICIENT_BALANCE"),
])
async def test_request_checks(bank, amount, code):
    client, tony, _, src, dst = bank
    if code == "PER_TRANSFER_LIMIT_EXCEEDED":
        async with SessionLocal() as db:
            await db.execute(update(Account).where(Account.account_id == src["account_id"]).values(balance=5_000_000))
            await db.commit()
    response = await client.post("/transfers", json=transfer(src, dst, amount=amount), headers=tony)
    assert response.status_code == 400 and response.json()["error"]["code"] == code


async def test_daily_limit_counts_today_transfers(bank):
    client, tony, _, src, dst = bank
    async with SessionLocal() as db:
        await db.execute(update(Account).where(Account.account_id == src["account_id"]).values(balance=10_000_000))
        db.add(AccountTransaction(account_id=src["account_id"], tx_type="TRANSFER_OUT", amount=-4_500_000, balance_after=10_000_000))
        db.add(AccountTransaction(account_id=src["account_id"], tx_type="INTERNAL_OUT", amount=-3_000_000, balance_after=10_000_000))
        await db.commit()
    response = await client.post("/transfers", json=transfer(src, dst, amount=600_000), headers=tony)
    assert response.json()["error"]["code"] == "DAILY_LIMIT_EXCEEDED"  # 450만 + 60만 > 500만 (내 계좌 이동은 안 셈)
    assert "500,000원" in response.json()["error"]["message"]
    assert (await client.post("/transfers", json=transfer(src, dst, amount=500_000), headers=tony)).status_code == 202


async def test_own_savings_is_internal_without_limit(bank):
    client, tony, _, src, _ = bank
    savings = await open_account(client, tony, "스타크 자유적금", term_months=12, monthly_payment=100_000)
    action = (await client.post("/transfers", json=transfer(src, savings, amount=100_000), headers=tony)).json()["data"]
    await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": PIN}, headers=tony)
    async with SessionLocal() as db:
        types = list(await db.scalars(select(AccountTransaction.tx_type).order_by(AccountTransaction.tx_id)))
    assert types == ["INTERNAL_OUT", "INTERNAL_IN"]


async def test_cannot_send_to_others_savings_or_from_others_account(bank):
    client, tony, peter, src, _ = bank
    peter_savings = await open_account(client, peter, "스타크 자유적금", term_months=12, monthly_payment=100_000)
    response = await client.post("/transfers", json=transfer(src, peter_savings), headers=tony)
    assert response.json()["error"]["code"] == "ACCOUNT_CANNOT_RECEIVE"
    response = await client.post("/transfers", json=transfer(src, peter_savings), headers=peter)
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"  # 남의 계좌에서는 못 보냄


async def test_expired_reject_and_other_users_action(bank):
    client, tony, peter, src, dst = bank
    a1 = (await client.post("/transfers", json=transfer(src, dst, key="key-expired"), headers=tony)).json()["data"]
    async with SessionLocal() as db:
        await db.execute(update(PendingAction).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()
    response = await client.post(f"/approvals/{a1['action_id']}/approve", json={"pin": PIN}, headers=tony)
    assert response.json()["error"]["code"] == "ACTION_EXPIRED"

    a2 = (await client.post("/transfers", json=transfer(src, dst, key="key-rejected"), headers=tony)).json()["data"]
    assert (await client.post(f"/approvals/{a2['action_id']}/approve", json={"pin": PIN}, headers=peter)).status_code == 404
    assert (await client.post(f"/approvals/{a2['action_id']}/reject", headers=tony)).json()["data"]["status"] == "REJECTED"
    response = await client.post(f"/approvals/{a2['action_id']}/approve", json={"pin": PIN}, headers=tony)
    assert response.json()["error"]["code"] == "ACTION_NOT_PENDING"
    assert await balance(src["account_id"]) == 1_000_000


async def test_attempts_are_reserved_before_checking(bank):
    """느린 PIN 확인이 동시에 많이 돌아도 예약은 5번까지만 성공한다 (동시 추측 차단)"""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        uid = await db.scalar(select(User.user_id).where(User.login_id == "ironman"))
        reserved = [await user_repository.reserve_attempt(db, uid, "pin", 5, now) for _ in range(10)]
        assert reserved == [1, 2, 3, 4, 5, None, None, None, None, None]
        await user_repository.fail_attempt(db, uid, "pin", 5, now + timedelta(minutes=15))  # 하나가 틀려서 잠김
        assert await user_repository.succeed_attempt(db, uid, "pin", now) is False  # 늦게 끝난 정답은 인정 안 함
        await db.commit()


async def test_no_pin_attempt_for_expired_action(bank):
    client, tony, _, src, dst = bank
    action = (await client.post("/transfers", json=transfer(src, dst), headers=tony)).json()["data"]
    async with SessionLocal() as db:
        await db.execute(update(PendingAction).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()
    response = await client.post(f"/approvals/{action['action_id']}/approve", json={"pin": "000000"}, headers=tony)
    assert response.json()["error"]["code"] == "ACTION_EXPIRED"  # 틀린 PIN이어도 PIN 실패로 세지 않음
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).where(AuditLog.action == "PIN_FAILED")) == 0


async def test_daily_limit_rechecked_at_execution(bank):
    client, tony, _, src, dst = bank
    async with SessionLocal() as db:
        await db.execute(update(Account).where(Account.account_id == src["account_id"]).values(balance=10_000_000))
        await db.commit()
    # 요청 때는 각각 한도 안이지만, 승인할수록 오늘 보낸 금액이 쌓인다 (90만 × 6 = 540만 > 500만)
    actions = [(await client.post("/transfers", json=transfer(src, dst, amount=900_000, key=f"key-daily-{i}"), headers=tony)).json()["data"]
               for i in range(6)]
    results = [await client.post(f"/approvals/{a['action_id']}/approve", json={"pin": PIN}, headers=tony) for a in actions]
    assert [r.status_code for r in results] == [200] * 5 + [400]
    assert results[-1].json()["error"]["code"] == "DAILY_LIMIT_EXCEEDED"
    assert await balance(dst["account_id"]) == 4_500_000


async def test_memo_is_part_of_idempotency(bank):
    client, tony, _, src, dst = bank
    await client.post("/transfers", json=transfer(src, dst, memo="밥값"), headers=tony)
    response = await client.post("/transfers", json=transfer(src, dst, memo="월세"), headers=tony)
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_name_cannot_look_like_amount(client):
    body = {"login_id": "tricky", "password": "password1234", "phone": "010-1234-5678", "birth_date": "1990-05-29"}
    for name in ["피터 500만원", "1,000,000", "피터(관리자)"]:
        assert (await client.post("/users/signup", json={**body, "name": name})).status_code == 422, name
    assert (await client.post("/users/signup", json={**body, "name": "Peter Parker"})).status_code == 201


async def test_claim_succeeds_only_once(bank):
    """승인 상태 변경은 조건부 UPDATE 한 문장: 같은 작업을 두 번 바꾸려 하면 두 번째는 0행 (docs/guides/04)"""
    client, tony, _, src, dst = bank
    action = (await client.post("/transfers", json=transfer(src, dst), headers=tony)).json()["data"]
    async with SessionLocal() as db:
        uid = await db.scalar(select(User.user_id).where(User.login_id == "ironman"))
        aid = uuid.UUID(action["action_id"])
        now = datetime.now(UTC)
        assert await approval_repository.claim(db, aid, uid, now, "APPROVED") is not None
        assert await approval_repository.claim(db, aid, uid, now, "APPROVED") is None
        await db.rollback()
