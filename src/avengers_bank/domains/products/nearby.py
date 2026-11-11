"""카카오 장소 목록과 확인된 혜택으로 왕복 식사·카페 계획을 계산한다."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import product
from math import ceil
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.config import get_settings
from avengers_bank.core.exceptions import ApiException
from avengers_bank.core.geo import distance_m
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.cards.models import Card, CardProduct
from avengers_bank.domains.cards.repository import card_repository
from avengers_bank.domains.cards.schemas import Location
from avengers_bank.domains.products.benefit_schemas import BenefitRoute, NearbyPlan, PlanLimits, RouteStop
from avengers_bank.domains.products.benefits import Purchase, get_benefits, get_purchases, month_saving, saving

KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
COUPON_FILE = Path(__file__).with_name("benefit_coupons.json")


def hide_location_requests(record: logging.LogRecord) -> bool:
    return KAKAO_CATEGORY_URL not in record.getMessage()


# httpx logs the whole URL, including the user's coordinates.
logging.getLogger("httpx").addFilter(hide_location_requests)


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    address: str
    kind: Literal["meal", "cafe"]
    location: Location
    price_won: int

    @property
    def map_url(self) -> str | None:
        return f"https://place.map.kakao.com/{self.place_id}" if self.place_id.isascii() and self.place_id.isdecimal() else None


class KakaoPlace(BaseModel):
    id: str = Field(pattern=r"^[0-9]+$")
    place_name: str = Field(min_length=1, max_length=120)
    address_name: str = Field(max_length=250)
    road_address_name: str = Field(max_length=250)
    x: float = Field(ge=-180, le=180)
    y: float = Field(ge=-90, le=90)


class Coupon(BaseModel):
    place_id: str
    title: str
    starts_on: date
    ends_on: date
    minimum_won: int = Field(ge=0)
    discount_won: int = Field(gt=0)
    requires_channel: bool
    source_url: HttpUrl | None = None


COUPONS = TypeAdapter(list[Coupon])
DEMO_ORIGIN = Location(latitude=37.5000, longitude=127.0300)


def demo_places() -> list[Place]:
    return [
        Place(place_id, name, "시연 지도", kind, Location(latitude=lat, longitude=lon), price)
        for place_id, name, kind, lat, lon, price in (
            ("demo-meal-1", "시연 골목식당", "meal", 37.5007, 127.0301, 13_000),
            ("demo-meal-2", "시연 온기식당", "meal", 37.5019, 127.0320, 12_500),
            ("demo-cafe-1", "빽다방 시연점", "cafe", 37.5010, 127.0302, 5_000),
            ("demo-cafe-2", "시연 모퉁이카페", "cafe", 37.5018, 127.0320, 5_000),
        )
    ]


async def kakao_places(
    client: httpx.AsyncClient, key: str, location: Location, *, meal_price: int, cafe_price: int
) -> list[Place]:
    async def search(kind: Literal["meal", "cafe"], category: str, price: int) -> list[Place]:
        response = await client.get(
            KAKAO_CATEGORY_URL,
            headers={"Authorization": f"KakaoAK {key}"},
            params={"category_group_code": category, "x": location.longitude, "y": location.latitude,
                    "radius": 1_500, "sort": "distance", "size": 10},
        )
        response.raise_for_status()
        places = TypeAdapter(list[KakaoPlace]).validate_python(response.json()["documents"])
        return [
            Place(p.id, p.place_name, p.road_address_name or p.address_name, kind,
                  Location(latitude=p.y, longitude=p.x), price)
            for p in places
        ]

    try:
        restaurants, cafes = await asyncio.gather(search("meal", "FD6", meal_price), search("cafe", "CE7", cafe_price))
        return restaurants + cafes
    except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
        raise ApiException(503, "PLACE_SEARCH_UNAVAILABLE", "주변 매장을 지금 검색할 수 없습니다.") from None


async def find_places(location: Location, *, meal_price: int, cafe_price: int) -> list[Place]:
    key = get_settings().kakao_local_api_key
    if key is None:
        raise ApiException(503, "PLACE_SEARCH_DISABLED", "카카오맵 검색 키가 필요합니다. 예시 데이터로 시연할 수 있어요.")
    async with httpx.AsyncClient(timeout=5.0) as client:
        return await kakao_places(client, key.get_secret_value(), location, meal_price=meal_price, cafe_price=cafe_price)


def available_coupons(today: date, *, demo: bool, allow_channel: bool) -> list[Coupon]:
    if demo:
        coupons = [Coupon(
            place_id="demo-cafe-2", title="시연 채널 추가 1,500원 할인", starts_on=today,
            ends_on=today + timedelta(days=7), minimum_won=4_000, discount_won=1_500, requires_channel=True,
        )]
    else:
        try:
            coupons = COUPONS.validate_json(COUPON_FILE.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            raise ApiException(503, "COUPONS_UNAVAILABLE", "확인된 쿠폰 정보를 불러오지 못했습니다.") from None
        coupons = [coupon for coupon in coupons if coupon.source_url and coupon.source_url.scheme == "https"]
    return [coupon for coupon in coupons if coupon.starts_on <= today <= coupon.ends_on
            and (allow_channel or not coupon.requires_channel)]


async def eligible_debit_cards(db: AsyncSession, user_id: int, today: date) -> list[tuple[str, int]]:
    rows = (await db.execute(
        select(Card, CardProduct.name, Account.balance).join(CardProduct).join(Account, Card.linked_account_id == Account.account_id)
        .where(Card.user_id == user_id, Card.status == "ACTIVE", CardProduct.type == "DEBIT",
               CardProduct.product_code == 1, Account.status == "ACTIVE").order_by(Card.card_id)
    )).all()
    cards = []
    for card, product_name, balance in rows:
        remaining = card.daily_limit - await card_repository.spent_since(db, card.card_id, kst_midnight_utc(today))
        cards.append((f"{card.nickname or product_name} · 끝자리 {card.card_num[-4:]}", min(remaining, balance)))
    return cards


def walking_m(first: Location, second: Location) -> float:
    return distance_m(first.latitude, first.longitude, second.latitude, second.longitude)


async def quote_routes(
    db: AsyncSession, user_id: int, places: list[Place], origin: Location, limits: PlanLimits, *,
    demo: bool, allow_channel: bool, preview_bundle: bool,
) -> NearbyPlan:
    today = today_kst()
    month = today.replace(day=1)
    cards = [("시연 체크카드 · 끝자리 4821", 100_000)] if demo else await eligible_debit_cards(db, user_id, today)
    coupons = available_coupons(today, demo=demo, allow_channel=allow_channel)
    remaining = []
    if preview_bundle:
        offers = (await get_benefits(db, user_id)).saved.offers
        purchases = [] if demo else await get_purchases(db, user_id, month)
        remaining = [(offer, offer.monthly_cap_won - month_saving(offer, purchases)) for offer in offers]

    def price_stop(place: Place) -> tuple[RouteStop, int]:
        price = place.price_won
        stop = RouteStop(name=place.name, address=place.address, kind=place.kind, map_url=place.map_url, price_won=price)
        # 기존 체크카드 카페 혜택. 맞춤 조합은 비교용으로만 별도 표시한다.
        if place.kind == "cafe":
            stop.card_name = next((name for name, available in cards if available >= price), None)
            if stop.card_name:
                stop.discount_won, stop.benefit = price * 5 // 100, "체크카드 카페 5%"
        purchase = Purchase(place.name, place.kind, price, month)
        for offer, left in remaining:
            preview = min(left, saving(offer, purchase))
            if preview > stop.discount_won:
                stop.discount_won, stop.benefit, stop.card_name = preview, f"{offer.label} · 조합 미리보기", None
        without_coupon = price - stop.discount_won
        for coupon in coupons:
            discount = min(coupon.discount_won, price)
            if coupon.place_id == place.place_id and price >= coupon.minimum_won and discount > stop.discount_won:
                stop.discount_won, stop.benefit, stop.card_name = discount, coupon.title, None
                stop.coupon_url = str(coupon.source_url) if coupon.source_url else None
                stop.coupon_until, stop.coupon_minimum_won = coupon.ends_on, coupon.minimum_won
                stop.coupon_requires_channel = coupon.requires_channel
        return stop, without_coupon

    meals = [p for p in places if p.kind == "meal" and (not limits.meal_keyword or limits.meal_keyword.casefold() in p.name.casefold())]
    cafes = [p for p in places if p.kind == "cafe" and (not limits.cafe_keyword or limits.cafe_keyword.casefold() in p.name.casefold())]
    quotes = {place.place_id: price_stop(place) for place in meals + cafes}
    routes = []
    for meal, cafe in product(meals, cafes):
        if meal.place_id == cafe.place_id:
            continue
        distance = walking_m(origin, meal.location) + walking_m(meal.location, cafe.location) + walking_m(cafe.location, origin)
        # shortcut: 직선 거리의 1.25배와 분당 70m로 추정한다. 실제 도보 경로·대기시간은 별도 데이터가 필요하다.
        minutes = ceil(distance * 1.25 / 70) + limits.meal_minutes + limits.cafe_minutes
        meal_stop, meal_no_coupon = quotes[meal.place_id]
        cafe_stop, cafe_no_coupon = quotes[cafe.place_id]
        before = meal_stop.price_won + cafe_stop.price_won
        total = before - meal_stop.discount_won - cafe_stop.discount_won
        if minutes <= limits.available_minutes and total <= limits.budget_won:
            routes.append(BenefitRoute(
                label="fastest", stops=[meal_stop, cafe_stop], estimated_minutes=minutes, total_won=total,
                total_before_benefits_won=before, total_without_coupons_won=meal_no_coupon + cafe_no_coupon,
            ))
    choices = []
    if routes:
        fastest = min(routes, key=lambda route: (route.estimated_minutes, route.total_won))
        cheapest = min(routes, key=lambda route: (route.total_won, route.estimated_minutes))
        choices = ([fastest.model_copy(update={"label": "fastest_and_cheapest"})] if fastest is cheapest
                   else [fastest, cheapest.model_copy(update={"label": "cheapest"})])
    return NearbyPlan(
        source="demo" if demo else "kakao", price_basis="demo_prices" if demo else "user_estimates",
        preview_bundle=preview_bundle, budget_won=limits.budget_won, available_minutes=limits.available_minutes,
        routes=choices,
    )
