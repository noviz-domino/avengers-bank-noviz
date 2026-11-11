from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from avengers_bank.domains.accounts.categories import CATEGORIES

Won = Annotated[int, Field(gt=0, le=10_000_000_000)]


def known_categories(names):
    unknown = [n for n in names if n not in CATEGORIES]
    if unknown:
        raise ValueError(f"없는 카테고리: {', '.join(unknown)} (가능: {', '.join(CATEGORIES)})")
    return names


class FixedExpenseIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    amount: Won
    day: int = Field(ge=1, le=31)  # 그 달에 없는 날이면 말일


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    target_amount: Won
    months: int = Field(ge=1, le=60)


class EssentialIn(BaseModel):
    """생활비 한 업종: 금액과 쓰는 주기. 매일 쓰면 per=day, 가끔이면 주·월 몇 번인지 (예: 외식 주 2회 × 3만 원)"""

    model_config = ConfigDict(extra="forbid")

    amount: int = Field(ge=0, le=10_000_000)  # 한 번(매일이면 하루)에 쓰는 돈
    per: Literal["day", "week", "month"] = "day"
    times: int = Field(default=1, ge=1, le=31)  # 주·월에 몇 번

    @model_validator(mode="after")
    def _times(self):
        if self.per == "day" and self.times != 1:
            raise ValueError("매일 쓰는 생활비는 횟수가 1이어야 합니다")
        if self.per == "week" and self.times > 7:
            raise ValueError("주 단위 횟수는 1~7번")
        return self

    @model_validator(mode="before")
    @classmethod
    def _plain_number(cls, value):
        return {"amount": value} if isinstance(value, int) else value  # 예전 형식(하루 금액 숫자)도 받는다


class BudgetEssentials(BaseModel):
    essentials: dict[str, EssentialIn] | None = None  # 업종별 생활비 {"식사": {"amount": 15000}, "외식": {"amount": 30000, "per": "week", "times": 2}}

    @model_validator(mode="after")
    def _unique_fixed_names(self):
        items = getattr(self, "fixed_expenses", None) or []
        if len({f.name for f in items}) != len(items):
            raise ValueError("고정 지출 이름은 중복될 수 없습니다")
        return self

    @field_validator("essentials")
    @classmethod
    def _essentials(cls, v):
        if v is not None:
            known_categories(v)
        return v


class BudgetEnroll(BudgetEssentials):
    """POST /budget — 신청. 바로 반영한다 (가드를 강하게 하는 쪽, ADR 0007)"""

    model_config = ConfigDict(extra="forbid")

    monthly_income: Won
    payday: int = Field(ge=1, le=28)
    essentials: dict[str, EssentialIn] = Field(default_factory=dict)
    fixed_expenses: list[FixedExpenseIn] = Field(default_factory=list, max_length=30)
    goal: GoalIn | None = None
    always_allow_categories: list[str] = Field(default_factory=lambda: ["의료"], max_length=len(CATEGORIES))

    @field_validator("always_allow_categories")
    @classmethod
    def _always(cls, v):
        return known_categories(v)


class BudgetUpdate(BudgetEssentials):
    """PATCH /budget — 강화는 즉시, 완화는 PIN 승인 대기 (ADR 0007 표)"""

    model_config = ConfigDict(extra="forbid")

    monthly_income: int | None = Field(default=None, gt=0, le=10_000_000_000)
    fixed_expenses: list[FixedExpenseIn] | None = Field(default=None, max_length=30)  # 목록 전체를 바꿈
    goal: GoalIn | None = None  # null은 삭제, 생략하면 그대로
    always_allow_categories: list[str] | None = Field(default=None, max_length=len(CATEGORIES))

    @field_validator("always_allow_categories")
    @classmethod
    def _always(cls, v):
        return known_categories(v) if v is not None else v


class CycleOut(BaseModel):
    start: date
    end: date
    days_total: int
    days_left: int


class CategoryAmount(BaseModel):
    category: str
    amount: int


class FixedExpenseOut(BaseModel):
    name: str
    amount: int
    day: int
    paid: bool  # 이번 주기에 나가는 날이 지났으면 낸 것으로 봄


class GoalOut(BaseModel):
    name: str
    target_amount: int
    months: int
    monthly_amount: int


class BudgetNotEnrolled(BaseModel):
    """GET /budget, 신청하지 않은 사람: `{"enrolled": false}`만"""

    enrolled: Literal[False] = False


class BudgetSummary(BaseModel):
    """POST·GET·PATCH /budget. 금액은 모두 원(정수), 이번 주기 기준"""

    enrolled: Literal[True] = True
    cycle: CycleOut
    monthly_income: int
    spent: int  # 이번 주기에 쓴 돈 (체크·이체·신용카드, 같은 주기 환불은 뺌)
    unpaid_fixed: int
    essential_reserve: int  # 남겨 둘 생활비: 매일 항목은 남은 일수 × 금액, 주·월 항목은 계획액 - 이미 쓴 돈
    goal_saving: int
    free_before_saving: int  # 생활비만 보면
    free_to_spend: int  # 저축까지 지키면: 결제 검사 기준
    daily_allowance: int  # max(0, free_to_spend) // days_left
    by_category: list[CategoryAmount]  # 이번 주기 업종별 지출, 많은 순
    fixed_expenses: list[FixedExpenseOut]
    goal: GoalOut | None
    essentials: dict[str, EssentialIn]
    always_allow_categories: list[str]


class BudgetCheck(BaseModel):
    """GET /budget/check — "이거 사도 돼?" 계산만, 아무것도 바꾸지 않는다"""

    allowed: bool
    free_to_spend: int
    after: int
    shortage: int
    always_allowed: bool
    message: str
