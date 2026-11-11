"""카드 결제 확인 규칙과 스마트폰 위치 동의."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import KST
from avengers_bank.core.exceptions import BadRequestException, ConflictException
from avengers_bank.core.geo import distance_m
from avengers_bank.domains.cards.repository import card_repository
from avengers_bank.domains.cards.schemas import CardProtection, CardProtectionUpdate, Location, MerchantPayment, PhoneLocation
from avengers_bank.domains.users.models import User
from avengers_bank.domains.users.service import user_service

LOCATION_TTL = timedelta(minutes=15)
ONLINE_SIGNAL_TTL = timedelta(minutes=5)
MAX_ACCURACY_M = 2_000
MAX_DISTANCE_M = 10_000
MIN_MOVEMENT_M = 1_000
ROUNDING_MARGIN_M = 800
HIGH_VALUE_AMOUNT = 500_000


async def get_settings(db: AsyncSession, user_id: int) -> CardProtection:
    user = await db.get(User, user_id)
    return CardProtection.model_validate((user.card_protection or {}).get("settings", {}))


async def update_settings(
    db: AsyncSession, user_id: int, data: CardProtectionUpdate, ip: str | None
) -> CardProtection:
    await user_service.verify_pin(db, user_id, data.pin, ip=ip, target="card_protection")
    settings = CardProtection.model_validate(data.model_dump(exclude={"pin"}))
    async with db.begin():
        user = await db.get(User, user_id, with_for_update=True, populate_existing=True)
        state = dict(user.card_protection or {})
        if not settings.location_check:
            state.pop("location", None)
        if settings.active_from is None:
            state.pop("activity_at", None)
        if not settings.location_check or settings.active_from is None:
            state.pop("movement_at", None)
        user.card_protection = {**state, "settings": settings.model_dump()}
    return settings


async def record_activity(db: AsyncSession, user_id: int) -> None:
    # shortcut: 로그인한 은행 화면의 활동을 참고하며, 실결제망 연동 시 기기 신뢰성 검증이 필요하다.
    async with db.begin():
        user = await db.get(User, user_id, with_for_update=True)
        state = user.card_protection or {}
        if not state.get("settings", {}).get("active_from"):
            return
        now = datetime.now(UTC)
        if not is_recent(state.get("activity_at"), now, timedelta(minutes=1)):
            user.card_protection = {**state, "activity_at": now.isoformat()}


async def record_location(db: AsyncSession, user_id: int, location: PhoneLocation) -> None:
    # shortcut: 브라우저 좌표는 확인 신호로만 사용하며, 실결제망 연동 시 기기 신뢰성 검증이 필요하다.
    now = datetime.now(UTC)
    if not now - LOCATION_TTL <= location.observed_at <= now + timedelta(seconds=30):
        raise BadRequestException(message="스마트폰에서 현재 위치를 다시 확인해 주세요.", code="STALE_PHONE_LOCATION")
    async with db.begin():
        user = await db.get(User, user_id, with_for_update=True)
        state = user.card_protection or {}
        settings = state.get("settings", {})
        if not settings.get("location_check"):
            raise ConflictException(message="위치 기반 카드 보호를 먼저 켜 주세요.", code="LOCATION_CHECK_DISABLED")
        previous = state.get("location")
        if previous and datetime.fromisoformat(previous["observed_at"]) >= location.observed_at:
            return
        state = dict(state)
        if (
            settings.get("active_from") and previous and is_recent(previous["observed_at"], now, LOCATION_TTL)
            and previous["accuracy_m"] <= MAX_ACCURACY_M and location.accuracy_m <= MAX_ACCURACY_M
            and distance_from(previous, location) - previous["accuracy_m"] - location.accuracy_m
            - ROUNDING_MARGIN_M > MIN_MOVEMENT_M
        ):
            state["movement_at"] = min(location.observed_at, now).isoformat()
        # 최근 위치 한 건만 보관한다. 0.01도 반올림 오차는 거리 판단에서 별도로 감안한다.
        user.card_protection = {**state, "location": location.model_dump(mode="json") | {
            "latitude": round(location.latitude, 2), "longitude": round(location.longitude, 2),
        }}


def is_recent(observed_at: str | None, now: datetime, ttl: timedelta) -> bool:
    return observed_at is not None and now - ttl <= datetime.fromisoformat(observed_at)


def distance_from(phone: dict, other: Location) -> float:
    return distance_m(phone["latitude"], phone["longitude"], other.latitude, other.longitude)


async def review_reason(
    db: AsyncSession, card_id: int, state: dict, payment: MerchantPayment, now: datetime
) -> str | None:
    settings = CardProtection.model_validate(state.get("settings", {}))
    if payment.channel == "ONLINE":
        start, end = settings.active_from, settings.active_until
        if start is None:
            return None
        if payment.amount >= HIGH_VALUE_AMOUNT and not await card_repository.used_merchant_since(
            db, card_id, payment.merchant_name, now - timedelta(days=30)
        ):
            return "최근 사용 내역에 없는 가맹점의 고액 온라인 결제"
        local = now.astimezone(KST).strftime("%H:%M")
        active = start <= local < end if start < end else local >= start or local < end
        phone_active = any(is_recent(state.get(key), now, ONLINE_SIGNAL_TTL) for key in ("activity_at", "movement_at"))
        return None if active or phone_active else "온라인 결제 활동시간 외 · 최근 스마트폰 활동 없음"
    if not settings.location_check:
        return None
    phone = state.get("location")
    if phone is None or not is_recent(phone["observed_at"], now, LOCATION_TTL):
        return "최근 스마트폰 위치 없음"
    if phone["accuracy_m"] > MAX_ACCURACY_M:
        return "스마트폰 위치 정확도 부족"

    distance_m = distance_from(phone, payment.terminal_location)
    if distance_m - phone["accuracy_m"] - ROUNDING_MARGIN_M > MAX_DISTANCE_M:
        return "스마트폰과 결제 단말기 위치 불일치"
    return None
