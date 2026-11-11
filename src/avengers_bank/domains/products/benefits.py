"""은행이 정한 카탈로그에서 소비 기록에 맞는 100크레딧 구성안을 계산한다."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import KST, today_kst
from avengers_bank.core.exceptions import BadRequestException
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.cards.models import Card, CardTransaction
from avengers_bank.domains.products.benefit_schemas import (
    BenefitBundle, BenefitGroup, BenefitOption, BenefitSettings, BundleRecommendation, SpendPattern,
)
from avengers_bank.domains.users.models import User

CREDIT_BUDGET = 100
HISTORY_MONTHS = 3


def option(offer_id: str, label: str, group: BenefitGroup, credits: int, rate: int, cap: int,
           merchant: str | None = None) -> BenefitOption:
    return BenefitOption(
        offer_id=offer_id, label=label, group=group, credits=credits, rate_percent=rate,
        monthly_cap_won=cap, merchant_prefix=merchant,
    )


# 서비스가 승인한 데모 상품 옵션. 이름과 퍼센트는 입력이나 모델 출력에서 받지 않는다.
CATALOGUE = {
    item.offer_id: item for item in (
        option("paiks-5", "빽다방 5%", "cafe", 20, 5, 1_500, "빽다방"),
        option("paiks-10", "빽다방 10%", "cafe", 40, 10, 3_000, "빽다방"),
        option("cafe-5", "카페 5%", "cafe", 35, 5, 3_000),
        option("meal-5", "식당 5%", "meal", 45, 5, 5_000),
        option("transit-5", "대중교통 5%", "transit", 35, 5, 4_000),
        option("convenience-5", "편의점 5%", "convenience", 25, 5, 2_000),
    )
}


@dataclass(frozen=True)
class Purchase:
    merchant: str
    group: BenefitGroup
    amount: int
    month: date


def make_bundle(offers: list[BenefitOption]) -> BenefitBundle:
    return BenefitBundle(offers=offers, credits=sum(item.credits for item in offers), budget=CREDIT_BUDGET)


def valid_bundle(bundle: BenefitBundle) -> bool:
    return bundle.credits <= bundle.budget and len({item.group for item in bundle.offers}) == len(bundle.offers)


def validate_bundle(offer_ids: list[str]) -> BenefitBundle:
    if any(key not in CATALOGUE for key in offer_ids):
        raise BadRequestException("은행이 제공하는 혜택을 선택해 주세요.", code="UNKNOWN_BENEFIT")
    bundle = make_bundle([CATALOGUE[key] for key in offer_ids])
    if not valid_bundle(bundle):
        raise BadRequestException("100크레딧 이내에서 같은 업종의 혜택은 하나만 고를 수 있습니다.",
                                  code="BENEFIT_CONSTRAINT")
    return bundle


async def get_benefits(db: AsyncSession, user_id: int) -> BenefitSettings:
    user = await db.get(User, user_id)
    catalogue = list(CATALOGUE.values())
    try:
        return BenefitSettings(catalogue=catalogue, saved=validate_bundle(user.benefit_bundle or []))
    except BadRequestException:
        return BenefitSettings(catalogue=catalogue, saved=make_bundle([]), needs_review=True)


async def save_benefits(db: AsyncSession, user_id: int, offer_ids: list[str]) -> BenefitBundle:
    bundle = validate_bundle(offer_ids)
    async with db.begin():
        user = await db.get(User, user_id, with_for_update=True)
        user.benefit_bundle = offer_ids
    return bundle


def merchant_group(name: str, category: str) -> BenefitGroup | None:
    # shortcut: 시뮬레이터 장부는 가맹점 이름만 남긴다. 실제 제휴는 가맹점 ID와 업종 코드로 판별한다.
    if any(word in name for word in ("편의점", "세븐일레븐")) or name.startswith(("GS25", "CU ")):
        return "convenience"
    if category == "교통":
        return "transit"
    if category in ("식사", "외식·술자리"):
        return "meal"
    if category == "카페·간식" or any(word in name for word in ("빽다방", "카페", "커피", "스타벅스")):
        return "cafe"
    return None


def previous_month(month: date) -> date:
    return (month - timedelta(days=1)).replace(day=1)


async def get_purchases(db: AsyncSession, user_id: int, since: date, before: date | None = None) -> list[Purchase]:
    query = select(CardTransaction).join(Card, Card.card_id == CardTransaction.card_id).where(
        Card.user_id == user_id, CardTransaction.status == "APPROVED",
        CardTransaction.approved_at >= kst_midnight_utc(since),
    )
    if before is not None:
        query = query.where(CardTransaction.approved_at < kst_midnight_utc(before))
    purchases = []
    for tx in await db.scalars(query):
        group = merchant_group(tx.merchant_name, tx.category)
        if group is not None:
            approved = tx.approved_at
            month = (approved if approved.tzinfo else approved.replace(tzinfo=UTC)).astimezone(KST).date().replace(day=1)
            purchases.append(Purchase(tx.merchant_name, group, tx.amount, month))
    return purchases


def saving(offer: BenefitOption, purchase: Purchase) -> int:
    if purchase.group != offer.group:
        return 0
    if offer.merchant_prefix and not purchase.merchant.startswith(offer.merchant_prefix):
        return 0
    return purchase.amount * offer.rate_percent // 100


def month_saving(offer: BenefitOption, purchases: list[Purchase]) -> int:
    return min(offer.monthly_cap_won, sum(saving(offer, item) for item in purchases))


async def recommend_bundle(
    db: AsyncSession, user_id: int, *, demo: bool, prioritize: BenefitGroup | None,
    exclude: list[BenefitGroup],
) -> BundleRecommendation:
    month = today_kst().replace(day=1)
    periods = []
    for _ in range(HISTORY_MONTHS):
        month = previous_month(month)
        periods.append(month)
    if demo:
        purchases = [
            Purchase(name, group, amount, period)
            for period in periods
            for name, group, amount, visits in (
                ("빽다방 시연점", "cafe", 3_500, 10), ("버스", "transit", 1_500, 30),
                ("시연 편의점", "convenience", 4_000, 10), ("시연 식당", "meal", 10_000, 3),
            )
            for _ in range(visits)
        ]
    else:
        purchases = await get_purchases(db, user_id, periods[-1], today_kst().replace(day=1))
    by_month = defaultdict(list)
    by_group = defaultdict(list)
    for purchase in purchases:
        by_month[purchase.month].append(purchase)
        by_group[purchase.group].append(purchase)
    patterns = [
        SpendPattern(group=group, visits=len(items), months=len({item.month for item in items}),
                     monthly_spend_won=sum(item.amount for item in items) // HISTORY_MONTHS,
                     frequent_merchants=[name for name, _ in Counter(item.merchant for item in items).most_common(3)])
        for group, items in sorted(by_group.items())
    ]
    values = {
        offer.offer_id: sum(month_saving(offer, items) for items in by_month.values())
        for offer in CATALOGUE.values() if offer.group not in exclude
    }
    candidates = [offer for offer in CATALOGUE.values() if offer.offer_id in values
                  and (values[offer.offer_id] or offer.group == prioritize)]
    best = make_bundle([])
    best_score = (False, 0, 0)
    for size in range(1, len(candidates) + 1):
        for choices in combinations(candidates, size):
            bundle = make_bundle(list(choices))
            if valid_bundle(bundle):
                score = (any(offer.group == prioritize for offer in choices),
                         sum(values[offer.offer_id] for offer in choices), -bundle.credits)
                if score > best_score:
                    best, best_score = bundle, score
    return BundleRecommendation(
        source="demo" if demo else "history", periods=HISTORY_MONTHS, patterns=patterns,
        bundle=best, monthly_saving_won=best_score[1] // HISTORY_MONTHS,
    )
