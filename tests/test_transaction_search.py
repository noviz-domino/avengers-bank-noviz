from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update

from avengers_bank.core.clock import KST
from avengers_bank.core.database import SessionLocal
from avengers_bank.domains.accounts.categories import classify
from avengers_bank.domains.accounts.models import AccountTransaction
from avengers_bank.seed import DEMO_LOGIN_ID, DEMO_PASSWORD, seed_demo_user, seed_products

pytestmark = pytest.mark.anyio


@pytest.fixture
async def demo(client):
    async with SessionLocal() as db:
        await seed_products(db)
    async with SessionLocal() as db:
        await seed_demo_user(db)
    token = (await client.post("/users/login", json={"login_id": DEMO_LOGIN_ID, "password": DEMO_PASSWORD})).json()["data"]
    return client, {"Authorization": f"Bearer {token['access_token']}"}


async def search(client, me, **params):
    response = await client.get("/transactions", params=params, headers=me)
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def test_classify_rules():
    assert classify("CARD_PAYMENT", "점심") == "식사"
    assert classify("CARD_PAYMENT", "회식 2차") == "외식·술자리"  # 식사보다 먼저 (budget.md: 회식은 필수 생활비가 아님)
    assert classify("TRANSFER_OUT", "월세") == "주거·통신"
    assert classify("TRANSFER_OUT", None, "피터") == "이체"
    assert classify("INTERNAL_OUT", "점심") == "저축·내 계좌"  # 거래 종류가 먼저
    assert classify("DEPOSIT", "급여") == "수입"
    assert classify("CARD_PAYMENT", "저녁 외식") == "외식·술자리"
    assert classify("CARD_PAYMENT", "수술비") == "의료"  # "술"이 들어 있어도 술자리가 아님
    assert classify("CARD_PAYMENT", "미술학원") == "기타"


async def test_search_all_accounts_with_totals(demo):
    client, me = demo
    data = await search(client, me)
    # 데모: 급여 300만, 편의점 3.8만, 월세 60만, 점심 1.2만 + 비상금 15만 + 예금 500만 + 적금 30만 × 2
    assert data["total_in"] == 3_000_000 + 150_000 + 5_000_000 + 600_000
    assert data["total_out"] == 38_000 + 600_000 + 12_000
    assert [t["category"] for t in data["transactions"] if t["memo"] in ("점심", "월세")] == ["식사", "주거·통신"]


async def test_filters(demo):
    client, me = demo
    assert [t["memo"] for t in (await search(client, me, direction="OUT"))["transactions"]] == ["점심", "월세", "편의점"]
    assert [t["memo"] for t in (await search(client, me, min_amount=100_000, max_amount=700_000, direction="OUT"))["transactions"]] == ["월세"]
    assert [t["memo"] for t in (await search(client, me, keyword="편의"))["transactions"]] == ["편의점"]
    assert (await search(client, me, category="식사"))["total_out"] == 12_000
    assert (await search(client, me, keyword="100%"))["transactions"] == []  # %가 와일드카드로 쓰이지 않음


async def test_date_range_uses_korean_date(demo):
    """한국 시간 0~9시는 UTC로 전날이다. 이 구간의 거래가 한국 날짜로 잡히는지 (UTC 날짜를 쓰면 실패)"""
    client, me = demo
    day = date(2026, 11, 5)
    async with SessionLocal() as db:  # 월세: 11/5 한국 08:00 = UTC 11/4 23:00
        early = datetime(2026, 11, 5, 8, 0, tzinfo=KST).astimezone(UTC)
        await db.execute(update(AccountTransaction).where(AccountTransaction.memo == "월세").values(created_at=early))
        await db.commit()
    on_day = [t["memo"] for t in (await search(client, me, from_date=str(day), to_date=str(day)))["transactions"]]
    day_before = [t["memo"] for t in (await search(client, me, from_date=str(day - timedelta(days=1)), to_date=str(day - timedelta(days=1))))["transactions"]]
    assert "월세" in on_day and "월세" not in day_before


async def test_paging_and_totals_cover_all_pages(demo):
    client, me = demo
    page1 = await search(client, me, limit=3)
    page2 = await search(client, me, limit=3, before=page1["next_before"])
    assert len(page1["transactions"]) == 3 and page1["total_in"] == page2["total_in"]  # 합계는 쪽과 상관없이 전체
    ids = [t["tx_id"] for t in page1["transactions"] + page2["transactions"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == len(ids)


async def test_other_users_data_is_hidden(demo):
    client, me = demo
    await client.post("/users/signup", json={"login_id": "thor", "password": "password1234", "name": "토르",
                                              "phone": "010-1234-5678", "birth_date": "1990-01-01"})
    token = (await client.post("/users/login", json={"login_id": "thor", "password": "password1234"})).json()["data"]
    other = {"Authorization": f"Bearer {token['access_token']}"}
    assert (await search(client, other)) == {"transactions": [], "total_in": 0, "total_out": 0, "next_before": None}

    demo_tx = (await search(client, me, limit=1))["transactions"][0]
    assert (await client.get("/transactions", params={"account_id": demo_tx["account_id"]}, headers=other)).status_code == 404
    response = await client.patch(f"/transactions/{demo_tx['tx_id']}", json={"category": "여가"}, headers=other)
    assert response.status_code == 404 and response.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"


async def test_user_can_fix_category_and_memo(demo):
    client, me = demo
    tx = next(t for t in (await search(client, me))["transactions"] if t["memo"] == "편의점")
    response = await client.patch(f"/transactions/{tx['tx_id']}", json={"category": "식사"}, headers=me)
    assert response.json()["data"]["category"] == "식사" and response.json()["data"]["memo"] == "편의점"  # 보낸 칸만
    assert (await client.patch(f"/transactions/{tx['tx_id']}", json={"category": "로또"}, headers=me)).status_code == 422
    async with SessionLocal() as db:
        assert await db.scalar(select(AccountTransaction.amount).where(AccountTransaction.tx_id == tx["tx_id"])) == -38_000


async def test_unknown_fields_rejected(demo):
    client, me = demo
    assert (await client.get("/transactions", params={"catgory": "식사"}, headers=me)).status_code == 422  # 오타
    tx = (await search(client, me, limit=1))["transactions"][0]
    assert (await client.patch(f"/transactions/{tx['tx_id']}", json={"amount": 1}, headers=me)).status_code == 422
    assert (await client.patch(f"/transactions/{tx['tx_id']}", json={"category": None}, headers=me)).status_code == 422
    assert (await client.patch(f"/transactions/{tx['tx_id']}", json={"memo": None}, headers=me)).json()["data"]["memo"] is None


async def test_no_next_page_when_exactly_limit_left(demo):
    client, me = demo
    total = len((await search(client, me, limit=100))["transactions"])
    assert (await search(client, me, limit=total))["next_before"] is None
    assert (await search(client, me, limit=total - 1))["next_before"] is not None


async def test_backfill_fills_only_missing(demo):
    from avengers_bank.seed import backfill_categories
    async with SessionLocal() as db:
        await db.execute(update(AccountTransaction).where(AccountTransaction.memo == "점심").values(category=None))
        await db.execute(update(AccountTransaction).where(AccountTransaction.memo == "월세").values(category="여가"))
        await db.commit()
    async with SessionLocal() as db:
        assert await backfill_categories(db) == 1
    async with SessionLocal() as db:
        cats = dict((await db.execute(select(AccountTransaction.memo, AccountTransaction.category))).all())
    assert cats["점심"] == "식사" and cats["월세"] == "여가"  # 사용자가 고친 값은 그대로


async def test_invalid_ranges(demo):
    client, me = demo
    assert (await client.get("/transactions", params={"from_date": "2026-11-05", "to_date": "2026-11-01"}, headers=me)).status_code == 422
    assert (await client.get("/transactions", params={"min_amount": 10, "max_amount": 1}, headers=me)).status_code == 422
