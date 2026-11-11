"""예산 계산 (budget.md 규칙 1·3·4, ADR 0024). DB를 모르는 순수 함수라 숫자만 넣어 단위 테스트한다.

자유 사용 가능액 = 이번 주기 수입 - 쓴 돈 - 아직 안 낸 고정 지출 - 남겨 둘 생활비 - 목표 저축
모든 금액은 정수(원)다.

생활비는 업종마다 "금액 + 주기"로 받는다 (2026-11-12, ADR 0024 보완):
- 매일(day): 식사·교통처럼 매일 쓰는 돈 → 남은 일수(오늘 포함) × 금액
- 주 N회(week)·월 N회(month): 외식·쇼핑·의료처럼 가끔 쓰는 돈 → 이번 주기 계획액 - 이번 주기에 그 업종에서 이미 쓴 돈 (0 아래로는 안 감)
  주 N회의 주기 계획액 = 금액 × N × 주기 일수 ÷ 7 (올림), 월 N회 = 금액 × N (주기가 한 달이라)
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from avengers_bank.domains.products.eligibility import add_months


def cycle_bounds(payday: int, today: date) -> tuple[date, date]:
    """오늘이 들어 있는 주기 (월급날 ~ 다음 월급날 전날). payday는 1~28이라 모든 달에 있다"""
    start = today.replace(day=payday) if today.day >= payday else add_months(today.replace(day=payday), -1)
    return start, add_months(start, 1) - timedelta(days=1)


def fixed_due_date(payday: int, start: date, day: int) -> date:
    """고정 지출이 이번 주기에 나가는 날. 월급날 이후 날짜면 시작한 달, 아니면 다음 달. 그 달에 없는 날이면 말일"""
    month = start if day >= payday else add_months(start, 1)
    return month.replace(day=min(day, calendar.monthrange(month.year, month.month)[1]))


def fixed_paid(payday: int, today: date, day: int) -> bool:
    """나가는 날이 지났으면 낸 것으로 본다 (budget.md). 당일은 아직 안 낸 것: 늦게 나가도 두 번 쓰지 않게 보수적으로.
    shortcut: 실제 출금과 맞춰 보지 않는다. 출금 매칭은 소비 분석 PR에서"""
    return fixed_due_date(payday, cycle_bounds(payday, today)[0], day) < today


def goal_monthly(target_amount: int, months: int) -> int:
    return -(-target_amount // months)  # 올림: 마지막 달에 모자라지 않게


PERIODS = ("day", "week", "month")


def essential(value) -> dict:
    """저장된 생활비 한 항목을 {"amount", "per", "times"}로. 예전 값(하루 금액 정수)은 매일로 읽는다"""
    if isinstance(value, int):
        return {"amount": value, "per": "day", "times": 1}
    return {"amount": int(value["amount"]), "per": value.get("per", "day"), "times": int(value.get("times", 1))}


def planned_for_cycle(item: dict, days_total: int) -> int:
    """이번 주기(days_total일)에 쓸 계획액"""
    e = essential(item)
    if e["per"] == "day":
        return e["amount"] * days_total
    if e["per"] == "week":
        return -(-e["amount"] * e["times"] * days_total // 7)  # 올림: 모자라지 않게
    return e["amount"] * e["times"]


def essential_reserve(essentials: dict, spent_by_category: dict[str, int], days_left: int, days_total: int) -> int:
    """남겨 둘 생활비. 매일 항목은 남은 일수만큼, 주·월 항목은 계획액에서 이미 쓴 만큼 뺀다"""
    total = 0
    for name, item in essentials.items():
        e = essential(item)
        if e["per"] == "day":
            total += e["amount"] * days_left
        else:
            total += max(0, planned_for_cycle(e, days_total) - spent_by_category.get(name, 0))
    return total


def monthly_equivalent(item: dict) -> int:
    """설정끼리 비교용(완화 판정): 30일 주기 기준 계획액"""
    return planned_for_cycle(item, 30)


@dataclass(frozen=True)
class Budget:
    start: date
    end: date
    days_total: int
    days_left: int  # 오늘 포함
    monthly_income: int
    spent: int
    unpaid_fixed: int
    essential_reserve: int
    goal_saving: int
    free_before_saving: int  # 생활비만 보면
    free_to_spend: int  # 저축까지 지키면 (결제 검사 기준)

    @property
    def daily_allowance(self) -> int:
        return max(0, self.free_to_spend) // self.days_left


def compute(
    *, payday: int, today: date, monthly_income: int, spent: int, fixed: list[tuple[int, int]],
    essentials: dict, goal_saving: int, spent_by_category: dict[str, int] | None = None,
) -> Budget:
    """fixed: [(금액, 나가는 날)], essentials: {업종: {"amount", "per", "times"}} (예전 정수 값은 매일),
    spent_by_category: 이번 주기 업종별 지출 (주·월 항목에서 이미 쓴 돈을 빼는 데 씀)"""
    start, end = cycle_bounds(payday, today)
    days_left = (end - today).days + 1
    days_total = (end - start).days + 1
    unpaid = sum(amount for amount, day in fixed if not fixed_paid(payday, today, day))
    # shortcut: 신청 때 값 그대로. 지난 주기 중앙값(규칙 4)은 소비 분석 PR에서
    reserve = essential_reserve(essentials, spent_by_category or {}, days_left, days_total)
    before_saving = monthly_income - spent - unpaid - reserve
    return Budget(
        start=start, end=end, days_total=days_total, days_left=days_left,
        monthly_income=monthly_income, spent=spent, unpaid_fixed=unpaid, essential_reserve=reserve,
        goal_saving=goal_saving, free_before_saving=before_saving, free_to_spend=before_saving - goal_saving,
    )


def needs_confirmation(free_to_spend: int, amount: int, category: str | None, always_allow: list[str]) -> bool:
    """카드 결제 검사: 자유 사용 가능액 안이거나 항상 통과 업종이면 False. 업종은 서버가 정한 값만 넣는다 (ADR 0007)"""
    return amount > free_to_spend and category not in always_allow


def still_confirmed(free_now: int, amount: int, free_at_confirm: int) -> bool:
    """실행 때 다시 검사 (ADR 0007): 지금 안에 들어오거나, 확인 때 본 숫자보다 나빠지지 않았으면 통과"""
    return amount <= free_now or free_now >= free_at_confirm


def impact_text(budget: Budget, amount: int, goal_name: str | None) -> str:
    """승인 화면에 보여 줄 예산 영향 (서버가 만든 문장, 승인·실행 규칙 5)"""
    after = budget.free_to_spend - amount
    line = f"예산 초과: 자유 사용 가능액 {budget.free_to_spend:,}원 → {after:,}원"
    if budget.free_before_saving - amount < 0:
        return line + " (월급날 전에 고정 지출·필수 생활비가 모자라요)"
    if goal_name:
        return line + f" ({goal_name} 저축이 이번 주기에 {-after:,}원 모자라요)"
    return line
