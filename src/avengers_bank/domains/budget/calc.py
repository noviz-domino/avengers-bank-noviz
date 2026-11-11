"""예산 계산 (budget.md 규칙 1·3·4, ADR 0024). DB를 모르는 순수 함수라 숫자만 넣어 단위 테스트한다.

자유 사용 가능액 = 이번 주기 수입 - 쓴 돈 - 아직 안 낸 고정 지출 - 남은 날의 필수 생활비 - 목표 저축
모든 금액은 정수(원)다.
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
    essentials_daily: int, goal_saving: int,
) -> Budget:
    """fixed: [(금액, 나가는 날)], essentials_daily: 카테고리별 하루 필수 생활비의 합"""
    start, end = cycle_bounds(payday, today)
    days_left = (end - today).days + 1
    unpaid = sum(amount for amount, day in fixed if not fixed_paid(payday, today, day))
    reserve = essentials_daily * days_left  # shortcut: 신청 때 값 그대로. 지난 주기 중앙값(규칙 4)은 소비 분석 PR에서
    before_saving = monthly_income - spent - unpaid - reserve
    return Budget(
        start=start, end=end, days_total=(end - start).days + 1, days_left=days_left,
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
