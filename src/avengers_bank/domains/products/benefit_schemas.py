from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BenefitGroup = Literal["cafe", "meal", "transit", "convenience"]
OfferId = Annotated[str, Field(min_length=1, max_length=40)]


class BenefitOption(BaseModel):
    offer_id: str
    label: str
    group: BenefitGroup
    credits: int
    rate_percent: int
    monthly_cap_won: int
    merchant_prefix: str | None = None


class BenefitBundle(BaseModel):
    offers: list[BenefitOption]
    credits: int
    budget: int


class BundleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_ids: list[OfferId] = Field(max_length=6)


class BenefitSettings(BaseModel):
    catalogue: list[BenefitOption]
    saved: BenefitBundle
    needs_review: bool = False


class SpendPattern(BaseModel):
    group: BenefitGroup
    visits: int
    months: int
    monthly_spend_won: int
    frequent_merchants: list[str]


class BundleRecommendation(BaseModel):
    source: Literal["history", "demo"]
    periods: int
    patterns: list[SpendPattern]
    bundle: BenefitBundle
    monthly_saving_won: int


class PlanLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_won: int = Field(ge=1_000, le=500_000)
    available_minutes: int = Field(ge=1, le=240)
    meal_minutes: int = Field(default=25, ge=5, le=120)
    cafe_minutes: int = Field(default=8, ge=3, le=120)
    meal_keyword: str | None = Field(default=None, min_length=1, max_length=50)
    cafe_keyword: str | None = Field(default=None, min_length=1, max_length=50)


class RouteStop(BaseModel):
    name: str
    address: str
    kind: Literal["meal", "cafe"]
    map_url: str | None
    price_won: int
    card_name: str | None = None
    discount_won: int = 0
    benefit: str | None = None
    coupon_url: str | None = None
    coupon_until: date | None = None
    coupon_minimum_won: int | None = None
    coupon_requires_channel: bool = False


class BenefitRoute(BaseModel):
    label: Literal["fastest", "cheapest", "fastest_and_cheapest"]
    stops: list[RouteStop]
    estimated_minutes: int
    total_won: int
    total_before_benefits_won: int
    total_without_coupons_won: int


class NearbyPlan(BaseModel):
    source: Literal["kakao", "demo"]
    price_basis: Literal["user_estimates", "demo_prices"]
    preview_bundle: bool
    budget_won: int
    available_minutes: int
    routes: list[BenefitRoute]
