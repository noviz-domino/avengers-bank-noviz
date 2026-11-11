"""예산 관리: 신청·조회·검사 시뮬레이션·강화 변경·해지 요청, 결제 검사가 쓰는 주기 잠금 (budget.md, ADR 0007·0024).

결제 검사(가드) 자체는 돈 실행 지점(accounts/money.py, cards/service.py)이 이 파일의 lock_cycle로 숫자를 받아서 한다.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import ConflictException, NotFoundException
from avengers_bank.domains.accounts.models import Account, AccountTransaction
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.budget import calc
from avengers_bank.domains.budget.models import BudgetCycle, BudgetProfile, FixedExpense
from avengers_bank.domains.budget.schemas import (
    BudgetCheck,
    BudgetEnroll,
    BudgetNotEnrolled,
    BudgetSummary,
    BudgetUpdate,
    CategoryAmount,
    CycleOut,
    FixedExpenseOut,
    GoalOut,
)
from avengers_bank.domains.cards.models import Card, CardTransaction

# 장부에서 "쓴 돈"으로 세는 종류 (budget.md 규칙 3). 환불은 같은 주기면 빼고, 다음 주기면 수입처럼 더하는 것과 같아서 함께 센다.
# 내 계좌끼리(INTERNAL_*), 카드 대금(CARD_BILL), 목표 저축(GOAL_SAVING_*)은 세지 않는다
SPENDING_TX_TYPES = ("CARD_PAYMENT", "TRANSFER_OUT", "WITHDRAW", "LOAN_REPAY", "REFUND")
APPROVAL_TTL = timedelta(minutes=10)


def not_enrolled() -> NotFoundException:
    return NotFoundException(message="예산 관리를 신청하지 않았습니다.", code="BUDGET_NOT_ENROLLED")


async def find_profile(db: AsyncSession, user_id: int) -> BudgetProfile | None:
    profile = await db.get(BudgetProfile, user_id, populate_existing=True)
    return profile if profile is not None and profile.active else None


async def fixed_expenses(db: AsyncSession, user_id: int) -> list[FixedExpense]:
    return list(await db.scalars(
        select(FixedExpense).where(FixedExpense.user_id == user_id).order_by(FixedExpense.day, FixedExpense.fixed_expense_id)
    ))


async def spent_by_category(db: AsyncSession, user_id: int, start: date, end: date) -> dict[str, int]:
    """이번 주기에 쓴 돈 (업종별). 체크카드·이체는 장부, 신용카드는 쓴 순간의 사용내역 (규칙 2)"""
    since, until = kst_midnight_utc(start), kst_midnight_utc(end + timedelta(days=1))
    ledger = await db.execute(
        select(AccountTransaction.category, func.sum(-AccountTransaction.amount))  # 나간 돈 −를 +로, 환불 +는 −로
        .join(Account, Account.account_id == AccountTransaction.account_id)
        .where(Account.user_id == user_id, AccountTransaction.tx_type.in_(SPENDING_TX_TYPES),
               AccountTransaction.created_at >= since, AccountTransaction.created_at < until)
        .group_by(AccountTransaction.category)
    )
    credit = await db.execute(
        select(CardTransaction.category, func.sum(CardTransaction.amount))
        .join(Card, Card.card_id == CardTransaction.card_id)
        # 대금을 낸 뒤 취소한 건은 환불 줄(REFUND)이 빼 주므로 사용분은 그대로 센다 (두 번 빼지 않게)
        .where(Card.user_id == user_id, Card.card_type == "CREDIT",
               or_(CardTransaction.status == "APPROVED", CardTransaction.refund_tx_id.is_not(None)),
               CardTransaction.approved_at >= since, CardTransaction.approved_at < until)
        .group_by(CardTransaction.category)
    )
    totals: dict[str, int] = {}
    for category, amount in [*ledger.all(), *credit.all()]:
        totals[category or "기타"] = totals.get(category or "기타", 0) + int(amount)
    return totals


async def calculate(db: AsyncSession, profile: BudgetProfile, today: date | None = None) -> tuple[calc.Budget, dict[str, int]]:
    today = today or today_kst()
    start, end = calc.cycle_bounds(profile.payday, today)
    by_category = await spent_by_category(db, profile.user_id, start, end)
    budget = calc.compute(
        payday=profile.payday, today=today, monthly_income=profile.monthly_income, spent=sum(by_category.values()),
        fixed=[(f.amount, f.day) for f in await fixed_expenses(db, profile.user_id)],
        essentials_daily=sum(profile.essentials.values()), goal_saving=profile.goal_monthly_amount or 0,
    )
    return budget, by_category


async def preview(db: AsyncSession, user_id: int) -> tuple[BudgetProfile, calc.Budget] | None:
    """잠그지 않고 계산만 (이체 요청 때 미리 보여 주기, 검사 시뮬레이션). 신청 안 했으면 None"""
    profile = await find_profile(db, user_id)
    return (profile, (await calculate(db, profile))[0]) if profile else None


async def lock_cycle(db: AsyncSession, user_id: int) -> tuple[BudgetProfile, calc.Budget] | None:
    """지출 실행 직전: 이번 주기 행을 만들거나(get-or-create) 잠그고 계산한다. 신청 안 했으면 None (검사 안 함).
    같은 사용자의 지출(이체·체크·신용)은 이 행에서 한 줄로 서서, 동시에 와도 같은 돈을 두 번 쓰지 않는다"""
    profile = await find_profile(db, user_id)
    if profile is None:
        return None
    start, end = calc.cycle_bounds(profile.payday, today_kst())
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    await db.execute(insert(BudgetCycle).values(user_id=user_id, start_date=start, end_date=end)
                     .on_conflict_do_nothing(index_elements=["user_id", "start_date"]))
    await db.execute(select(BudgetCycle.cycle_id).where(
        BudgetCycle.user_id == user_id, BudgetCycle.start_date == start).with_for_update())
    profile = await find_profile(db, user_id)  # 잠근 뒤 다시 읽는다 (그사이 해지됐을 수 있음)
    return (profile, (await calculate(db, profile))[0]) if profile else None


async def run_budget_disable(db: AsyncSession, action: PendingAction) -> None:
    """승인된 예산 관리 해지 (approvals EXECUTORS). 기록은 남기고 active만 끈다"""
    from avengers_bank.domains.accounts.money import TransferRejected  # money가 이 파일을 import해서 여기서

    locked = await lock_cycle(db, action.user_id)
    profile = locked[0] if locked else None
    if profile is None:
        raise TransferRejected("BUDGET_NOT_ENROLLED", "예산 관리를 신청하지 않았습니다.")
    profile.active = False


def weakening_changes(profile: BudgetProfile, fixed: list[FixedExpense], data: BudgetUpdate) -> list[str]:
    """가드를 약하게 하는 변경 (ADR 0007 표). 자유 사용 가능액을 늘리는 쪽이면 PIN이 필요하다"""
    weak = []
    if data.monthly_income is not None and data.monthly_income > profile.monthly_income:
        weak.append("월 수입 높이기")
    if data.essentials is not None and any(data.essentials.get(k, 0) < v for k, v in profile.essentials.items()):
        weak.append("필수 생활비 낮추기·빼기")
    if data.fixed_expenses is not None:
        new = {f.name: (f.amount, f.day) for f in data.fixed_expenses}
        # 이름으로 맞춰 본다: 빠지거나, 금액이 줄거나, 날짜가 바뀌면(이미 지난 날로 옮기면 안 낸 돈이 줄어서) 약하게
        if any(f.name not in new or new[f.name][0] < f.amount or new[f.name][1] != f.day for f in fixed):
            weak.append("고정 지출 빼기·낮추기·날짜 바꾸기")
    if "goal" in data.model_fields_set and profile.goal_name is not None:
        if data.goal is None or calc.goal_monthly(data.goal.target_amount, data.goal.months) < profile.goal_monthly_amount:
            weak.append("목표 저축 빼기·낮추기")
    if data.always_allow_categories is not None and set(data.always_allow_categories) - set(profile.always_allow):
        weak.append("항상 통과 업종 추가")
    return weak


def apply_goal(profile: BudgetProfile, goal) -> None:
    profile.goal_name = goal.name if goal else None
    profile.goal_target_amount = goal.target_amount if goal else None
    profile.goal_months = goal.months if goal else None
    profile.goal_monthly_amount = calc.goal_monthly(goal.target_amount, goal.months) if goal else None


async def configuration(db: AsyncSession, profile: BudgetProfile) -> dict:
    return {
        "monthly_income": profile.monthly_income, "payday": profile.payday,
        "essentials": profile.essentials, "always_allow_categories": profile.always_allow,
        "goal": {"name": profile.goal_name, "target_amount": profile.goal_target_amount,
                 "months": profile.goal_months} if profile.goal_name else None,
        "fixed_expenses": [{"name": f.name, "amount": f.amount, "day": f.day}
                           for f in await fixed_expenses(db, profile.user_id)],
    }


async def apply_update(db: AsyncSession, profile: BudgetProfile, data: BudgetUpdate) -> None:
    if data.monthly_income is not None:
        profile.monthly_income = data.monthly_income
    if data.essentials is not None:
        profile.essentials = dict(data.essentials)
    if data.always_allow_categories is not None:
        profile.always_allow = list(dict.fromkeys(data.always_allow_categories))
    if data.fixed_expenses is not None:
        await budget_service._replace_fixed(db, profile.user_id, data.fixed_expenses)
    if "goal" in data.model_fields_set:
        apply_goal(profile, data.goal)


def change_details(data: BudgetUpdate) -> str:
    """승인 화면에 실제 반영할 전체 값을 사람이 읽을 수 있게 표시한다."""
    lines = []
    if data.monthly_income is not None:
        lines.append(f"월 수입: {data.monthly_income:,}원")
    if data.essentials is not None:
        items = ", ".join(f"{name} 하루 {amount:,}원" for name, amount in data.essentials.items())
        lines.append(f"필수 생활비: {items or '없음'}")
    if data.fixed_expenses is not None:
        items = ", ".join(f"{f.name} {f.amount:,}원 (매월 {f.day}일)" for f in data.fixed_expenses)
        lines.append(f"고정 지출: {items or '없음'}")
    if "goal" in data.model_fields_set:
        goal = data.goal
        text = (f"{goal.name} {goal.target_amount:,}원 / {goal.months}개월 "
                f"(주기마다 {calc.goal_monthly(goal.target_amount, goal.months):,}원 저축)") if goal else "삭제"
        lines.append(f"목표: {text}")
    if data.always_allow_categories is not None:
        lines.append(f"항상 통과 업종: {', '.join(data.always_allow_categories) or '없음'}")
    return "\n".join(lines)


async def run_budget_update(db: AsyncSession, action: PendingAction) -> None:
    from avengers_bank.domains.accounts.money import TransferRejected

    locked = await lock_cycle(db, action.user_id)
    if locked is None:
        raise TransferRejected("BUDGET_NOT_ENROLLED", "예산 관리를 신청하지 않았습니다.")
    profile = locked[0]
    if await configuration(db, profile) != action.payload["before"]:
        raise TransferRejected("BUDGET_CHANGED", "예산 설정이 바뀌었습니다. 변경 내용을 확인하고 다시 요청해 주세요.")
    await apply_update(db, profile, BudgetUpdate.model_validate(action.payload["changes"]))


class BudgetService:
    async def enroll(self, db: AsyncSession, user_id: int, data: BudgetEnroll) -> BudgetSummary:
        """신청은 가드를 강하게 하는 쪽이라 바로 반영 (ADR 0007). 해지했던 사람은 같은 행을 새 값으로 덮어쓴다"""
        async with db.begin():
            profile = await db.get(BudgetProfile, user_id)
            if profile is not None and profile.active:
                raise ConflictException(message="이미 예산 관리를 쓰고 있습니다.", code="BUDGET_ALREADY_ENROLLED")
            if profile is None:
                profile = BudgetProfile(user_id=user_id)
                db.add(profile)
            profile.monthly_income, profile.payday, profile.active = data.monthly_income, data.payday, True
            profile.essentials = dict(data.essentials)
            profile.always_allow = list(dict.fromkeys(data.always_allow_categories))
            apply_goal(profile, data.goal)
            await self._replace_fixed(db, user_id, data.fixed_expenses)
            try:
                await db.flush()
            except IntegrityError:  # 같은 사람이 동시에 두 번 신청
                raise ConflictException(message="이미 예산 관리를 쓰고 있습니다.", code="BUDGET_ALREADY_ENROLLED") from None
            return await self._summary(db, profile)

    async def summary(self, db: AsyncSession, user_id: int) -> BudgetSummary | BudgetNotEnrolled:
        profile = await find_profile(db, user_id)
        return await self._summary(db, profile) if profile else BudgetNotEnrolled()

    async def check(self, db: AsyncSession, user_id: int, amount: int, category: str | None) -> BudgetCheck:
        """결제 검사와 같은 규칙으로 계산만 한다. 아무것도 쓰지 않는다 ("이거 사도 돼?")"""
        found = await preview(db, user_id)
        if found is None:
            raise not_enrolled()
        profile, budget = found
        free, after = budget.free_to_spend, budget.free_to_spend - amount
        always = category in profile.always_allow
        allowed = not calc.needs_confirmation(free, amount, category, profile.always_allow)
        if amount <= free:
            message = f"써도 돼요. 쓰고 나면 자유 사용 가능액은 {after:,}원이에요."
        elif always:
            message = f"항상 통과 업종({category})이라 카드 결제는 돼요. 자유 사용 가능액은 {after:,}원이 돼요."
        else:
            message = calc.impact_text(budget, amount, profile.goal_name) + ". 결제하려면 승인 화면에서 사유와 PIN이 필요해요."
        return BudgetCheck(allowed=allowed, free_to_spend=free, after=after, shortage=max(0, amount - free),
                           always_allowed=always, message=message)

    async def update(self, db: AsyncSession, user_id: int, data: BudgetUpdate,
                     requested_by: str = "WEB") -> BudgetSummary | PendingAction:
        async with db.begin():
            locked = await lock_cycle(db, user_id)
            if locked is None:
                raise not_enrolled()
            profile = locked[0]
            if weak := weakening_changes(profile, await fixed_expenses(db, user_id), data):
                changes = data.model_dump(mode="json", exclude_unset=True)
                action = PendingAction(
                    user_id=user_id, action_type="BUDGET_UPDATE", requested_by=requested_by,
                    payload={"changes": changes,
                             "before": await configuration(db, profile)},
                    idempotency_key=f"budget-update-{uuid.uuid4()}", expires_at=datetime.now(UTC) + APPROVAL_TTL,
                    summary=f"예산 변경: {', '.join(weak)} (PIN 승인 후 반영)\n{change_details(data)}",
                )
                await approval_repository.save(db, action)
                return action
            await apply_update(db, profile, data)
            await db.flush()
            return await self._summary(db, profile)

    async def request_disable(self, db: AsyncSession, user_id: int, requested_by: str = "WEB") -> tuple[PendingAction, bool]:
        """해지는 가드를 끄는 변경이라 승인 대기만 만든다 (PIN 승인 뒤 run_budget_disable, ADR 0007).
        기다리는 해지 요청이 있으면 그것을 돌려준다"""
        async with db.begin():
            if await find_profile(db, user_id) is None:
                raise not_enrolled()
            now = datetime.now(UTC)
            for action in await approval_repository.find_pending(db, user_id, now):
                if action.action_type == "BUDGET_DISABLE":
                    return action, False
            action = PendingAction(
                user_id=user_id, action_type="BUDGET_DISABLE", requested_by=requested_by, payload={},
                idempotency_key=f"budget-disable-{uuid.uuid4()}", expires_at=now + APPROVAL_TTL,
                summary="예산 관리 해지 (결제 검사가 꺼집니다)",
            )
            await approval_repository.save(db, action)
            return action, True

    async def _replace_fixed(self, db: AsyncSession, user_id: int, items) -> None:
        await db.execute(delete(FixedExpense).where(FixedExpense.user_id == user_id))
        db.add_all(FixedExpense(user_id=user_id, name=f.name, amount=f.amount, day=f.day) for f in items)

    async def _summary(self, db: AsyncSession, profile: BudgetProfile) -> BudgetSummary:
        today = today_kst()
        budget, by_category = await calculate(db, profile, today)
        b = budget
        return BudgetSummary(
            cycle=CycleOut(start=b.start, end=b.end, days_total=b.days_total, days_left=b.days_left),
            monthly_income=b.monthly_income, spent=b.spent, unpaid_fixed=b.unpaid_fixed,
            essential_reserve=b.essential_reserve, goal_saving=b.goal_saving,
            free_before_saving=b.free_before_saving, free_to_spend=b.free_to_spend, daily_allowance=b.daily_allowance,
            by_category=[CategoryAmount(category=c, amount=a)
                         for c, a in sorted(by_category.items(), key=lambda kv: -kv[1]) if a > 0],
            fixed_expenses=[FixedExpenseOut(name=f.name, amount=f.amount, day=f.day,
                                            paid=calc.fixed_paid(profile.payday, today, f.day))
                            for f in await fixed_expenses(db, profile.user_id)],
            goal=GoalOut(name=profile.goal_name, target_amount=profile.goal_target_amount, months=profile.goal_months,
                         monthly_amount=profile.goal_monthly_amount) if profile.goal_name else None,
            essentials=profile.essentials, always_allow_categories=profile.always_allow,
        )


budget_service = BudgetService()
