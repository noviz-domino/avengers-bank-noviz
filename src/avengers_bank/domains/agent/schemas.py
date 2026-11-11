from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from avengers_bank.domains.cards.schemas import Location
from avengers_bank.domains.products.benefit_schemas import BundleRecommendation, NearbyPlan


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    session_id: UUID | None = None  # 없으면 새 대화. 같은 값을 보내면 앞 대화를 기억한다


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    routed: list[str]  # 이번 턴에 일한 담당 (account·card·product·budget), 평가·디버깅용


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class BenefitsChatRequest(ChatRequest):
    mode: Literal["bundle", "nearby"]
    demo: bool = False
    location: Location | None = None
    meal_price_won: int | None = Field(default=None, ge=1_000, le=500_000)
    cafe_price_won: int | None = Field(default=None, ge=1_000, le=500_000)
    budget_won: int | None = Field(default=None, ge=1_000, le=500_000)
    available_minutes: int | None = Field(default=None, ge=1, le=240)
    allow_channel_coupon: bool = False
    preview_bundle: bool = False

    @model_validator(mode="after")
    def require_live_inputs(self):
        if self.mode == "nearby" and (self.budget_won is None or self.available_minutes is None):
            raise ValueError("주변 코스를 찾으려면 결제 예산과 가용 시간이 필요합니다.")
        if self.mode == "nearby" and not self.demo and (
            self.location is None or self.meal_price_won is None or self.cafe_price_won is None
        ):
            raise ValueError("실제 주변 매장 검색에는 현재 위치와 식사·카페 예상 가격이 필요합니다.")
        if self.location is not None and (self.demo or self.mode == "bundle"):
            raise ValueError("위치는 실제 주변 매장을 검색할 때만 보내 주세요.")
        return self


class BenefitsChatResponse(ChatResponse):
    recommendation: BundleRecommendation | None = None
    plan: NearbyPlan | None = None
