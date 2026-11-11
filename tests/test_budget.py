"""예산 관리 (budget.md, ADR 0007·0024): 순수 계산, 주기 경계, 쓴 돈 세기, 결제 검사(가드), 승인 사유, 해지 승인"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.models import AccountTransaction
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.budget import calc
from avengers_bank.domains.budget.models import BudgetCycle, BudgetDecision
from avengers_bank.domains.users.models import User
from avengers_bank.seed import seed_card_products, seed_products
from tests.test_card_payments import merchant_pay
from tests.test_cards import issue
from tests.test_transfers import PIN, balance, open_account, user

pytestmark = pytest.mark.anyio

# 예시 사람 (budget.md "예시"): 월급 300만, 월급날 25일(주기 30일), 고정 지출 150만, 생활비 하루 1.9만, 목표 저축 25만
# 고정 지출 날짜: 월세 60(10일), 공과금 15(15일), 통신 10(27일), 보험·구독 15(28일), 대출 상환 50(30일)
FIXED = [(600_000, 10), (150_000, 15), (100_000, 27), (150_000, 28), (500_000, 30)]


def example(today: date, spent: int) -> calc.Budget:
    return calc.compute(payday=25, today=today, monthly_income=3_000_000, spent=spent, fixed=FIXED,
                        essentials={"식사": 19_000}, goal_saving=calc.goal_monthly(1_500_000, 6))


# ---------- 순수 계산 ----------

def test_spec_example_on_payday():
    b = example(date(2026, 11, 25), spent=0)
    assert (b.days_total, b.days_left) == (30, 30)
    assert (b.unpaid_fixed, b.essential_reserve, b.goal_saving) == (1_500_000, 570_000, 250_000)
    assert (b.free_before_saving, b.free_to_spend) == (930_000, 680_000)  # 68만
    assert b.daily_allowance == 680_000 // 30


def test_spec_example_after_7_days_of_overspending():
    b = example(date(2026, 12, 2), spent=2_000_000)  # 통신·보험·대출(27·28·30일)은 지나서 낸 것으로
    assert b.days_left == 23
    assert (b.unpaid_fixed, b.essential_reserve) == (750_000, 437_000)
    assert (b.free_before_saving, b.free_to_spend) == (-187_000, -437_000)  # -18.7만 / -43.7만
    assert b.daily_allowance == 0


@pytest.mark.parametrize("payday,today,expected", [
    (25, date(2026, 11, 24), (date(2026, 10, 25), date(2026, 11, 24))),  # 월급 전날은 지난 주기의 마지막 날
    (25, date(2026, 11, 25), (date(2026, 11, 25), date(2026, 12, 24))),
    (25, date(2027, 1, 10), (date(2026, 12, 25), date(2027, 1, 24))),  # 해 넘김
    (28, date(2027, 2, 27), (date(2027, 1, 28), date(2027, 2, 27))),
    (28, date(2027, 2, 28), (date(2027, 2, 28), date(2027, 3, 27))),  # 2월
    (1, date(2026, 3, 1), (date(2026, 3, 1), date(2026, 3, 31))),
    (1, date(2026, 2, 28), (date(2026, 2, 1), date(2026, 2, 28))),
])
def test_cycle_bounds(payday, today, expected):
    assert calc.cycle_bounds(payday, today) == expected


def test_fixed_expense_due_dates():
    assert calc.fixed_due_date(28, date(2027, 2, 28), 31) == date(2027, 2, 28)  # 2월에 31일이 없으면 말일
    assert calc.fixed_due_date(25, date(2026, 11, 25), 10) == date(2026, 12, 10)  # 월급날 앞 날짜는 다음 달
    assert not calc.fixed_paid(25, date(2026, 12, 10), 10)  # 당일은 아직 안 낸 것
    assert calc.fixed_paid(25, date(2026, 12, 11), 10)


def test_guard_rules():
    assert not calc.needs_confirmation(100, 100, "쇼핑", ["의료"])
    assert calc.needs_confirmation(100, 101, "쇼핑", ["의료"])
    assert not calc.needs_confirmation(-50, 101, "의료", ["의료"])  # 항상 통과 업종
    assert calc.still_confirmed(free_now=-100, amount=500, free_at_confirm=-100)  # 같으면 통과
    assert not calc.still_confirmed(free_now=-101, amount=500, free_at_confirm=-100)  # 나빠지면 실패
    assert calc.still_confirmed(free_now=600, amount=500, free_at_confirm=-100)  # 지금 안에 들어오면 통과
    assert calc.goal_monthly(1_000_000, 3) == 333_334  # 올림


def test_change_details_displays_all_proposed_values_and_removals():
    from avengers_bank.domains.budget.schemas import BudgetUpdate
    from avengers_bank.domains.budget.service import change_details

    text = change_details(BudgetUpdate(
        monthly_income=700_000, essentials={"식사": 5_000},
        fixed_expenses=[{"name": "월세", "amount": 100_000, "day": 31}],
        goal={"name": "여행", "target_amount": 1_000_000, "months": 3},
        always_allow_categories=["의료", "쇼핑"],
    ))
    assert text.splitlines() == [
        "월 수입: 700,000원", "생활비: 식사 매일 5,000원", "고정 지출: 월세 100,000원 (매월 31일)",
        "목표: 여행 1,000,000원 / 3개월 (주기마다 333,334원 저축)", "항상 통과 업종: 의료, 쇼핑",
    ]
    assert change_details(BudgetUpdate(goal=None, essentials={}, fixed_expenses=[], always_allow_categories=[])) == (
        "생활비: 없음\n고정 지출: 없음\n목표: 삭제\n항상 통과 업종: 없음"
    )
    assert change_details(BudgetUpdate()) == ""


def test_essentials_by_frequency():
    # 매일 항목은 남은 일수 × 금액, 주·월 항목은 이번 주기 계획액 - 그 업종에서 이미 쓴 돈 (0 아래로 안 감)
    days_left, days_total = 14, 31
    essentials = {"식사": {"amount": 15_000, "per": "day", "times": 1},
                  "외식·술자리": {"amount": 30_000, "per": "week", "times": 2},
                  "의료": {"amount": 20_000, "per": "month", "times": 1},
                  "쇼핑": {"amount": 50_000, "per": "month", "times": 1}}
    assert calc.planned_for_cycle(essentials["외식·술자리"], days_total) == 265_715  # 30,000 × 2 × 31 ÷ 7 올림
    spent = {"외식·술자리": 100_000, "쇼핑": 80_000, "식사": 999_999}
    assert calc.essential_reserve(essentials, spent, days_left, days_total) == (
        15_000 * 14          # 식사: 이미 쓴 돈과 상관없이 남은 날만큼
        + 265_715 - 100_000  # 외식: 계획 - 쓴 돈
        + 20_000             # 의료: 아직 안 씀
        + 0                  # 쇼핑: 계획(5만)보다 더 써서 더 남기지 않음
    )
    assert calc.essential(5_000) == {"amount": 5_000, "per": "day", "times": 1}  # 예전 저장값(하루 금액)도 읽음
    assert calc.monthly_equivalent({"amount": 1_000, "per": "day"}) == 30_000
    assert calc.monthly_equivalent({"amount": 30_000, "per": "month", "times": 1}) == 30_000


# ---------- API ----------

INCOME = 500_000  # 생활비·고정 지출·목표 없이: 자유 사용 가능액 = 50만 - 쓴 돈 (날짜와 상관없이 정해짐)


@pytest.fixture
async def bank(client):
    async with SessionLocal() as db:
        await seed_products(db)
    async with SessionLocal() as db:
        await seed_card_products(db)
    tony = await user(client, "ironman", "토니")
    peter = await user(client, "spidey", "피터")
    checking = await open_account(client, tony, balance=3_000_000)
    other = await open_account(client, peter)
    debit = (await issue(client, tony, checking)).json()["data"]
    credit = (await issue(client, tony, checking, type_="CREDIT")).json()["data"]
    return client, tony, peter, checking, other, debit, credit


async def enroll(client, me, **body):
    return await client.post("/budget", json={"monthly_income": INCOME, "payday": 1, **body}, headers=me)


def pay(client, me, card, amount, key, merchant="스타벅스 강남점"):
    return client.post(f"/cards/{card['card_id']}/payments",
                       json={"merchant_name": merchant, "amount": amount, "idempotency_key": key}, headers=me)


async def transfer(client, me, src, dst, amount, key):
    body = {"from_account_id": src["account_id"], "to_account_num": dst["account_num"], "amount": amount,
            "idempotency_key": key}
    return (await client.post("/transfers", json=body, headers=me)).json()["data"]


def approve(client, me, action_id, **body):
    return client.post(f"/approvals/{action_id}/approve", json={"pin": PIN, **body}, headers=me)


async def free(client, me) -> int:
    return (await client.get("/budget", headers=me)).json()["data"]["free_to_spend"]


async def count(model) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(func.count()).select_from(model))


async def decisions() -> list[BudgetDecision]:
    async with SessionLocal() as db:
        return list(await db.scalars(select(BudgetDecision).order_by(BudgetDecision.decision_id)))


async def test_enroll_and_summary(bank):
    client, tony, peter, *_ = bank
    assert (await client.get("/budget", headers=tony)).json()["data"] == {"enrolled": False}
    res = await enroll(client, tony, essentials={"식사": 15_000, "교통": 4_000},
                       goal={"name": "휴대폰", "target_amount": 1_500_000, "months": 6},
                       fixed_expenses=[{"name": "월세", "amount": 100_000, "day": 31}])
    assert res.status_code == 201
    s = res.json()["data"]
    assert s["enrolled"] and s["always_allow_categories"] == ["의료"]
    assert s["goal"] == {"name": "휴대폰", "target_amount": 1_500_000, "months": 6, "monthly_amount": 250_000}
    days_left = s["cycle"]["days_left"]
    unpaid = 0 if s["fixed_expenses"][0]["paid"] else 100_000
    assert s["essential_reserve"] == 19_000 * days_left
    assert s["free_before_saving"] == INCOME - unpaid - 19_000 * days_left
    assert s["free_to_spend"] == s["free_before_saving"] - 250_000
    assert s["daily_allowance"] == max(0, s["free_to_spend"]) // days_left

    again = await enroll(client, tony)
    assert again.status_code == 409 and again.json()["error"]["code"] == "BUDGET_ALREADY_ENROLLED"
    assert (await client.get("/budget", headers=peter)).json()["data"] == {"enrolled": False}  # 남의 예산은 안 보임
    bad = await enroll(client, peter, essentials={"술값": 1000})
    assert bad.status_code == 422  # 서버의 카테고리 목록에 없는 이름
    for wrong in [{"식사": {"amount": 1000, "per": "day", "times": 2}}, {"외식·술자리": {"amount": 1000, "per": "week", "times": 8}},
                  {"의료": {"amount": 1000, "per": "year"}}, {"의료": {"amount": -1, "per": "month"}}]:
        assert (await enroll(client, peter, essentials=wrong)).status_code == 422, wrong


async def test_enroll_with_weekly_and_monthly_essentials(bank):
    # 가끔 쓰는 생활비는 주·월 횟수로 받는다. 응답은 항상 {"amount", "per", "times"} 형식
    client, tony, *_ = bank
    s = (await enroll(client, tony, essentials={"식사": 10_000, "의료": {"amount": 20_000, "per": "month", "times": 1},
                                                "외식·술자리": {"amount": 30_000, "per": "week", "times": 2}})).json()["data"]
    assert s["essentials"]["식사"] == {"amount": 10_000, "per": "day", "times": 1}
    assert s["essentials"]["외식·술자리"] == {"amount": 30_000, "per": "week", "times": 2}
    days_total, days_left = s["cycle"]["days_total"], s["cycle"]["days_left"]
    assert s["essential_reserve"] == 10_000 * days_left + -(-30_000 * 2 * days_total // 7) + 20_000

    # 매일 1만 → 월 1회 1만은 덜 남기는 쪽이라 PIN 승인 대기
    res = await client.patch("/budget", json={"essentials": {"식사": {"amount": 10_000, "per": "month", "times": 1}}}, headers=tony)
    assert res.status_code == 202 and "식사 월 1회 × 10,000원" in res.json()["data"]["summary"]


async def test_spending_counts_by_kind(bank):
    client, tony, _, checking, other, debit, credit = bank
    await enroll(client, tony)
    mine = await open_account(client, tony)

    await approve(client, tony, (await transfer(client, tony, checking, other, 100_000, "t-0000001"))["action_id"])
    await approve(client, tony, (await transfer(client, tony, checking, mine, 50_000, "t-0000002"))["action_id"])
    assert (await pay(client, tony, credit, 30_000, "p-0000001")).status_code == 201
    tx = (await pay(client, tony, debit, 20_000, "p-0000002", merchant="김밥천국 점심")).json()["data"]
    async with SessionLocal() as db:  # 신용카드 대금 출금: 쓴 순간 셌으니 다시 세지 않는다
        db.add(AccountTransaction(account_id=checking["account_id"], tx_type="CARD_BILL", amount=-30_000,
                                  balance_after=1, category="카드 대금"))
        await db.commit()

    s = (await client.get("/budget", headers=tony)).json()["data"]
    assert s["spent"] == 100_000 + 30_000 + 20_000  # 내 계좌끼리 5만, 카드 대금은 안 셈
    assert {c["category"]: c["amount"] for c in s["by_category"]} == {"이체": 100_000, "카페·간식": 30_000, "식사": 20_000}
    assert s["by_category"][0]["category"] == "이체"  # 많은 순

    await client.post(f"/cards/{debit['card_id']}/transactions/{tx['card_tx_id']}/cancel", headers=tony)
    assert (await client.get("/budget", headers=tony)).json()["data"]["spent"] == 130_000  # 같은 주기 환불은 뺀다


async def test_card_over_budget_needs_human_confirmation(bank):
    client, tony, _, checking, _, debit, _ = bank
    await enroll(client, tony)
    assert (await pay(client, tony, debit, 100_000, "p-0000001")).status_code == 201  # 안이면 그대로
    assert await free(client, tony) == 400_000

    res = await pay(client, tony, debit, 450_000, "p-0000002")
    assert res.status_code == 409
    err = res.json()["error"]
    assert err["code"] == "BUDGET_CONFIRMATION_REQUIRED"
    data = err["data"]
    assert (data["free_to_spend"], data["after"], data["shortage"]) == (400_000, -50_000, 50_000)
    assert await balance(checking["account_id"]) == 2_900_000  # 결제 안 됨
    again = await pay(client, tony, debit, 450_000, "p-0000002")  # 같은 요청 번호: 같은 확인 요청
    assert again.status_code == 409 and again.json()["error"]["data"]["action_id"] == data["action_id"]

    action = (await client.get(f"/approvals/{data['action_id']}", headers=tony)).json()["data"]
    assert action["action_type"] == "BUDGET_CARD_PAYMENT" and action["needs_budget_reason"]
    assert "400,000원 → -50,000원" in action["budget_impact"] and action["budget_impact"] in action["summary"]

    no_reason = await approve(client, tony, data["action_id"])
    assert no_reason.status_code == 400 and no_reason.json()["error"]["code"] == "BUDGET_REASON_REQUIRED"
    async with SessionLocal() as db:  # PIN을 확인하기 전에 막아서 PIN 실패로 세지 않음
        assert await db.scalar(select(User.pin_fail_count).where(User.login_id == "ironman")) == 0

    done = await approve(client, tony, data["action_id"], reason="노트북 수리비")
    assert done.status_code == 200 and done.json()["data"]["status"] == "EXECUTED"
    assert await balance(checking["account_id"]) == 2_450_000
    card_tx_id = done.json()["data"]["result"]["card_tx_id"]
    paid_again = await pay(client, tony, debit, 450_000, "p-0000002")  # 가맹점이 다시 보내도 한 번만
    assert paid_again.status_code == 200 and paid_again.json()["data"]["card_tx_id"] == card_tx_id
    [d] = await decisions()
    assert (d.amount, d.free_to_spend_at_confirm, d.reason, d.emergency) == (450_000, 400_000, "노트북 수리비", False)
    assert str(d.action_id) == data["action_id"]


async def test_credit_card_is_guarded_too(bank):
    client, tony, _, _, _, _, credit = bank
    await enroll(client, tony)
    res = await pay(client, tony, credit, 500_001, "p-0000001")
    assert res.status_code == 409 and res.json()["error"]["code"] == "BUDGET_CONFIRMATION_REQUIRED"
    assert (await client.get(f"/cards/{credit['card_id']}/transactions", headers=tony)).json()["data"] == []


async def test_always_allow_category_passes_but_counts(bank):
    client, tony, _, _, _, debit, _ = bank
    await enroll(client, tony)
    res = await pay(client, tony, debit, 600_000, "p-0000001", merchant="서울약국")
    assert res.status_code == 201 and res.json()["data"]["category"] == "의료"
    assert await free(client, tony) == -100_000  # 통과해도 자유 사용 가능액에서는 빠진다
    [d] = await decisions()
    assert d.action_id is None and d.reason == "항상 통과 업종(의료)"


async def test_confirmed_payment_fails_if_budget_got_worse_unless_emergency(bank):
    client, tony, _, checking, _, debit, _ = bank
    await enroll(client, tony)
    first = (await pay(client, tony, debit, 600_000, "p-0000001")).json()["error"]["data"]  # 확인 때 50만
    assert (await pay(client, tony, debit, 100_000, "p-0000002")).status_code == 201  # 그사이 10만 씀
    res = await approve(client, tony, first["action_id"], reason="필요해서")
    assert res.status_code == 400 and res.json()["error"]["code"] == "BUDGET_CHANGED"
    action = (await client.get(f"/approvals/{first['action_id']}", headers=tony)).json()["data"]
    assert action["status"] == "FAILED" and action["failure_reason"].startswith("BUDGET_CHANGED")
    assert await balance(checking["account_id"]) == 2_900_000
    assert await decisions() == []

    second = (await pay(client, tony, debit, 600_000, "p-0000003")).json()["error"]["data"]  # 확인 때 40만
    assert (await pay(client, tony, debit, 50_000, "p-0000004")).status_code == 201
    res = await approve(client, tony, second["action_id"], reason="경조사", emergency=True)
    assert res.status_code == 200 and res.json()["data"]["status"] == "EXECUTED"  # 긴급은 다시 막지 않음
    [d] = await decisions()
    assert d.emergency and d.reason == "경조사"


async def test_transfer_over_budget_asks_reason_on_same_approval(bank):
    client, tony, _, checking, other, _, _ = bank
    await enroll(client, tony)
    small = await transfer(client, tony, checking, other, 1_000, "t-0000001")
    assert not small["needs_budget_reason"] and small["budget_impact"] is None
    assert (await approve(client, tony, small["action_id"])).status_code == 200  # 사유 없이 PIN만

    big = await transfer(client, tony, checking, other, 600_000, "t-0000002")
    assert big["status"] == "PENDING" and big["needs_budget_reason"]  # 409로 막지 않고 승인 화면에서 함께
    assert "예산 초과: 자유 사용 가능액 499,000원 → -101,000원" in big["summary"]
    res = await approve(client, tony, big["action_id"])
    assert res.status_code == 400 and res.json()["error"]["code"] == "BUDGET_REASON_REQUIRED"
    res = await approve(client, tony, big["action_id"], reason="이사 보증금 일부")
    assert res.status_code == 200 and res.json()["data"]["status"] == "EXECUTED"
    assert await balance(other["account_id"]) == 601_000
    [d] = await decisions()
    assert (d.amount, d.free_to_spend_at_confirm, d.reason) == (600_000, 499_000, "이사 보증금 일부")


async def test_transfer_fails_when_budget_changed_before_approval(bank):
    client, tony, _, checking, other, debit, _ = bank
    await enroll(client, tony)
    big = await transfer(client, tony, checking, other, 600_000, "t-0000001")
    assert (await pay(client, tony, debit, 100_000, "p-0000001")).status_code == 201
    res = await approve(client, tony, big["action_id"], reason="필요해서")
    assert res.status_code == 400 and res.json()["error"]["code"] == "BUDGET_CHANGED"
    assert await balance(other["account_id"]) == 0
    within = await transfer(client, tony, checking, other, 300_000, "t-0000002")  # 요청 때는 안이었는데
    assert (await pay(client, tony, debit, 200_000, "p-0000002")).status_code == 201  # 실행 때 넘으면
    res = await approve(client, tony, within["action_id"])
    assert res.status_code == 400 and res.json()["error"]["code"] == "BUDGET_CHANGED"


async def test_own_accounts_and_not_enrolled_users_are_not_checked(bank):
    client, tony, peter, checking, other, _, _ = bank
    await enroll(client, tony)
    mine = await open_account(client, tony)
    move = await transfer(client, tony, checking, mine, 1_000_000, "t-0000001")  # 내 계좌끼리는 지출이 아님
    assert not move["needs_budget_reason"]
    assert (await approve(client, tony, move["action_id"])).status_code == 200

    peter_card = (await issue(client, peter, other)).json()["data"]  # 신청 안 한 사람은 검사 안 함
    async with SessionLocal() as db:
        from avengers_bank.domains.accounts.models import Account
        (await db.get(Account, other["account_id"])).balance = 900_000
        await db.commit()
    assert (await pay(client, peter, peter_card, 900_000, "p-0000001")).status_code == 201


async def test_check_is_simulation_only(bank):
    client, tony, peter, *_ = bank
    await enroll(client, tony)
    c = (await client.get("/budget/check", params={"amount": 600_000}, headers=tony)).json()["data"]
    assert (c["allowed"], c["free_to_spend"], c["after"], c["shortage"], c["always_allowed"]) == (False, 500_000, -100_000, 100_000, False)
    c = (await client.get("/budget/check", params={"amount": 600_000, "category": "의료"}, headers=tony)).json()["data"]
    assert c["allowed"] and c["always_allowed"]
    c = (await client.get("/budget/check", params={"amount": 1_000}, headers=tony)).json()["data"]
    assert c["allowed"] and c["shortage"] == 0
    assert (await count(PendingAction), await count(BudgetCycle), await count(BudgetDecision)) == (0, 0, 0)
    res = await client.get("/budget/check", params={"amount": 1_000}, headers=peter)
    assert res.status_code == 404 and res.json()["error"]["code"] == "BUDGET_NOT_ENROLLED"


async def test_patch_weakening_waits_for_pin_and_strengthening_applies(bank):
    client, tony, *_ = bank
    await enroll(client, tony, essentials={"식사": 10_000}, goal={"name": "휴대폰", "target_amount": 600_000, "months": 6},
                 fixed_expenses=[{"name": "월세", "amount": 100_000, "day": 25}])

    async def patch(**body):
        return await client.patch("/budget", json=body, headers=tony)

    for weak in [dict(monthly_income=INCOME + 1), dict(essentials={"식사": 9_000}), dict(essentials={"교통": 10_000}),
                 dict(fixed_expenses=[]), dict(fixed_expenses=[{"name": "월세", "amount": 100_000, "day": 1}]),
                 dict(goal=None), dict(goal={"name": "휴대폰", "target_amount": 600_000, "months": 12})]:
        res = await patch(**weak)
        assert res.status_code == 202 and res.json()["data"]["action_type"] == "BUDGET_UPDATE", weak
        assert (await client.get("/budget", headers=tony)).json()["data"]["monthly_income"] == INCOME

    res = await patch(monthly_income=400_000, essentials={"식사": 12_000, "교통": 4_000},
                      fixed_expenses=[{"name": "월세", "amount": 120_000, "day": 25}, {"name": "통신", "amount": 50_000, "day": 13}],
                      goal={"name": "노트북", "target_amount": 1_200_000, "months": 6})
    assert res.status_code == 200
    s = res.json()["data"]
    assert (s["monthly_income"], s["goal"]["monthly_amount"], len(s["fixed_expenses"])) == (400_000, 200_000, 2)


async def test_disable_needs_pin_approval(bank):
    client, tony, _, _, _, debit, _ = bank
    await enroll(client, tony)
    res = await client.delete("/budget", headers=tony)
    assert res.status_code == 202
    action = res.json()["data"]
    assert action["action_type"] == "BUDGET_DISABLE" and action["status"] == "PENDING"
    again = await client.delete("/budget", headers=tony)
    assert again.status_code == 200 and again.json()["data"]["action_id"] == action["action_id"]
    assert (await client.get("/budget", headers=tony)).json()["data"]["enrolled"]  # 승인 전에는 그대로
    assert (await pay(client, tony, debit, 600_000, "p-0000001")).status_code == 409

    assert (await approve(client, tony, action["action_id"])).json()["data"]["status"] == "EXECUTED"
    assert (await client.get("/budget", headers=tony)).json()["data"] == {"enrolled": False}
    assert (await pay(client, tony, debit, 600_000, "p-0000002")).status_code == 201  # 검사 꺼짐
    assert (await enroll(client, tony)).status_code == 201  # 다시 신청할 수 있음


async def test_pin_update_is_scoped_single_use_and_stale_changes_fail(bank):
    client, tony, peter, *_ = bank
    await enroll(client, tony)
    change = (await client.patch("/budget", json={"monthly_income": 700_000,
                     "always_allow_categories": ["의료", "쇼핑"]}, headers=tony)).json()["data"]
    assert "월 수입: 700,000원" in change["summary"] and "항상 통과 업종: 의료, 쇼핑" in change["summary"]
    assert (await approve(client, peter, change["action_id"])).status_code == 404
    assert await free(client, tony) == INCOME
    done = await approve(client, tony, change["action_id"])
    assert done.status_code == 200 and done.json()["data"]["status"] == "EXECUTED"
    summary = (await client.get("/budget", headers=tony)).json()["data"]
    assert summary["monthly_income"] == 700_000 and summary["always_allow_categories"] == ["의료", "쇼핑"]
    assert (await approve(client, tony, change["action_id"])).status_code == 409
    stale = (await client.patch("/budget", json={"monthly_income": 900_000}, headers=tony)).json()["data"]
    assert (await client.patch("/budget", json={"monthly_income": 600_000}, headers=tony)).status_code == 200
    res = await approve(client, tony, stale["action_id"])
    assert res.status_code == 400 and res.json()["error"]["code"] == "BUDGET_CHANGED"
    assert await free(client, tony) == 600_000
    assert (await client.get(f"/approvals/{stale['action_id']}", headers=tony)).json()["data"]["status"] == "FAILED"


async def test_approved_goal_removal_and_category_removal(bank):
    client, tony, *_ = bank
    await enroll(client, tony, goal={"name": "여행", "target_amount": 120_000, "months": 6})
    res = await client.patch("/budget", json={"goal": None}, headers=tony)
    assert res.status_code == 202
    assert await free(client, tony) == INCOME - 20_000
    assert (await approve(client, tony, res.json()["data"]["action_id"])).status_code == 200
    assert await free(client, tony) == INCOME
    res = await client.patch("/budget", json={"always_allow_categories": []}, headers=tony)
    assert res.status_code == 200 and res.json()["data"]["always_allow_categories"] == []


async def test_duplicate_fixed_names_cannot_hide_removed_reserves(bank):
    client, tony, *_ = bank
    fixed = [{"name": "월세", "amount": 100_000, "day": 25}] * 2
    assert (await enroll(client, tony, fixed_expenses=fixed)).status_code == 422
    await enroll(client, tony)
    assert (await client.patch("/budget", json={"fixed_expenses": fixed}, headers=tony)).status_code == 422


SEOUL = {"latitude": 37.57, "longitude": 126.98}
BUSAN = {"latitude": 35.18, "longitude": 129.08}


async def protect_in_seoul(client, me):
    assert (await client.put("/cards/protection", json={"location_check": True, "pin": PIN}, headers=me)).status_code == 200
    phone = {**SEOUL, "accuracy_m": 50, "observed_at": datetime.now(UTC).isoformat()}
    assert (await client.put("/cards/protection/location", json=phone, headers=me)).status_code == 200


async def test_protection_hold_over_budget_asks_reason_on_same_approval(bank):
    """결제 보호(ADR 0023)가 보류한 결제가 예산도 넘으면 같은 승인에서 사유를 받는다: PIN 한 번 (ADR 0024)"""
    client, tony, _, checking, _, debit, _ = bank
    await enroll(client, tony)
    await protect_in_seoul(client, tony)

    held = await merchant_pay(client, debit, "far-0000001", terminal=BUSAN, amount=600_000)
    assert held.status_code == 202
    action = held.json()["data"]
    assert action["action_type"] == "CARD_PAYMENT" and action["needs_budget_reason"]
    assert "위치 불일치" in action["summary"] and action["budget_impact"] in action["summary"]

    no_reason = await approve(client, tony, action["action_id"])
    assert no_reason.status_code == 400 and no_reason.json()["error"]["code"] == "BUDGET_REASON_REQUIRED"
    done = await approve(client, tony, action["action_id"], reason="출장 숙박비")
    assert done.status_code == 200 and done.json()["data"]["status"] == "EXECUTED"
    assert await balance(checking["account_id"]) == 2_400_000
    [d] = await decisions()
    assert (d.amount, d.free_to_spend_at_confirm, d.reason) == (600_000, 500_000, "출장 숙박비")


async def test_protection_hold_fails_if_budget_runs_out_before_approval(bank):
    """보류 때는 예산 안이었는데 승인 전에 예산이 줄면 새 확인을 만들지 않고 실패한다. 돈은 안 움직인다"""
    client, tony, _, checking, _, debit, _ = bank
    await enroll(client, tony)
    await protect_in_seoul(client, tony)

    held = (await merchant_pay(client, debit, "far-0000002", terminal=BUSAN, amount=100_000)).json()["data"]
    assert held["action_type"] == "CARD_PAYMENT" and not held["needs_budget_reason"]
    near = await merchant_pay(client, debit, "near-000001", terminal=SEOUL, amount=450_000)  # 예산 안: 바로 결제
    assert near.status_code == 201
    assert await free(client, tony) == 50_000

    failed = await approve(client, tony, held["action_id"])
    assert failed.status_code == 400 and failed.json()["error"]["code"] == "BUDGET_CHANGED"
    assert await balance(checking["account_id"]) == 2_550_000  # 45만만 빠짐
    action = (await client.get(f"/approvals/{held['action_id']}", headers=tony)).json()["data"]
    assert action["status"] == "FAILED"
