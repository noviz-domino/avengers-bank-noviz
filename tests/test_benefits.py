import json
from datetime import timedelta

import httpx
import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import update

from avengers_bank.core.clock import today_kst
from avengers_bank.core.database import SessionLocal
from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.agent import benefits as benefit_agent
from avengers_bank.domains.agent.llm import get_llm
from avengers_bank.domains.cards.models import CardTransaction
from avengers_bank.domains.products import nearby
from avengers_bank.domains.rag import router as rag_router
from avengers_bank.main import app
from tests.test_agent import FakeChat, call
from tests.test_card_payments import bank, pay
from tests.test_transfers import user

pytestmark = pytest.mark.anyio


@pytest.fixture
def model(monkeypatch):
    fake = FakeChat()
    monkeypatch.setitem(app.dependency_overrides, get_llm, lambda: fake)
    rag_router.calls.clear()
    return fake


async def test_bundle_budget_and_exclusive_groups_are_enforced_per_user(client):
    me = await user(client, "ben-1", "혜택 고객")
    other = await user(client, "ben-2", "다른 고객")
    path = "/products/benefits"
    assert (await client.get(path)).status_code == 401
    for invalid in (["paiks-10", "meal-5", "convenience-5"], ["paiks-5", "cafe-5"], ["made-up-100"]):
        assert (await client.put(path, headers=me, json={"offer_ids": invalid})).status_code == 400
    saved = await client.put(path, headers=me, json={"offer_ids": ["paiks-10", "transit-5", "convenience-5"]})
    assert saved.status_code == 200 and saved.json()["data"]["credits"] == 100
    assert (await client.get(path, headers=other)).json()["data"]["saved"]["offers"] == []
    assert (await client.get(path, headers=me)).json()["data"]["saved"] == saved.json()["data"]


async def test_bundle_recommendation_uses_approved_owned_spending_and_respects_user_feedback(bank, model):
    client, me, _, debit, _ = bank
    payment = (await pay(client, me, debit, amount=40_000, merchant="빽다방 테스트점")).json()["data"]
    canceled = (await pay(client, me, debit, amount=80_000, key="cancel-ben-1", merchant="교통 테스트")).json()["data"]
    cancel = await client.post(f"/cards/{debit['card_id']}/transactions/{canceled['card_tx_id']}/cancel", headers=me)
    assert cancel.status_code == 200
    async with SessionLocal.begin() as db:
        previous_month = today_kst().replace(day=1) - timedelta(days=1)
        await db.execute(update(CardTransaction).where(CardTransaction.card_id == payment["card_id"])
                         .values(approved_at=kst_midnight_utc(previous_month)))
    model.replies = [
        call("recommend_my_bundle"), AIMessage("카페 이용 내역이 있어요."),
        call("recommend_my_bundle", exclude=["cafe"]), AIMessage("카페를 빼면 예상 할인이 없어요."),
    ]
    path = "/chat/benefits"
    first = await client.post(path, headers=me, json={"mode": "bundle", "message": "내 소비로 추천해줘"})
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    rec = data["recommendation"]
    assert rec["source"] == "history" and rec["monthly_saving_won"] == 1_000
    assert rec["patterns"] == [{
        "group": "cafe", "visits": 1, "months": 1, "monthly_spend_won": 13_333, "frequent_merchants": ["빽다방 테스트점"],
    }]
    assert [offer["offer_id"] for offer in rec["bundle"]["offers"]] == ["paiks-10"]
    updated = await client.post(path, headers=me, json={
        "mode": "bundle", "message": "카페는 빼줘", "session_id": data["session_id"],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["recommendation"]["bundle"]["offers"] == []
    assert (await client.get("/products/benefits", headers=me)).json()["data"]["saved"]["offers"] == []


async def test_demo_routes_respect_user_limits_channel_preference_and_saved_bundle(client, model):
    me = await user(client, "ben-plan", "코스 고객")
    assert (await client.put("/products/benefits", headers=me, json={"offer_ids": ["paiks-10"]})).status_code == 200
    tool_args = {"limits": {"budget_won": 100_000, "available_minutes": 100}}
    model.replies = [
        call("plan_nearby", **tool_args), AIMessage("가까운 코스와 저렴한 코스를 찾았어요."),
        call("plan_nearby", **tool_args), AIMessage("채널 조건을 반영했어요."),
        call("plan_nearby", **tool_args), AIMessage("맞는 코스가 없어요."),
    ]
    req = {"mode": "nearby", "demo": True, "message": "밥과 커피 코스", "budget_won": 20_000, "available_minutes": 45}
    path = "/chat/benefits"
    first = await client.post(path, headers=me, json=req | {"preview_bundle": True})
    assert first.status_code == 200, first.text
    plan = first.json()["data"]["plan"]
    assert (plan["budget_won"], plan["available_minutes"]) == (20_000, 45)
    assert plan["source"] == "demo"
    stops = [stop for route in plan["routes"] for stop in route["stops"]]
    assert any(stop["benefit"] == "빽다방 10% · 조합 미리보기" and stop["discount_won"] == 500 for stop in stops)
    assert all(not stop["coupon_requires_channel"] for stop in stops)

    second = await client.post(path, headers=me, json=req | {"allow_channel_coupon": True})
    assert second.status_code == 200, second.text
    cheapest = next(route for route in second.json()["data"]["plan"]["routes"] if route["label"] == "cheapest")
    assert (cheapest["total_won"], cheapest["total_without_coupons_won"]) == (16_000, 17_250)
    assert cheapest["stops"][1]["discount_won"] == 1_500 and cheapest["stops"][1]["coupon_requires_channel"]
    third = await client.post(path, headers=me, json=req | {"budget_won": 10_000, "available_minutes": 20})
    assert third.status_code == 200, third.text
    assert third.json()["data"]["plan"]["routes"] == []


async def test_kakao_contract_reads_both_categories_and_uses_user_estimated_prices():
    queries = []

    def upstream(request):
        assert str(request.url.copy_with(query=None)) == nearby.KAKAO_CATEGORY_URL
        assert request.headers["Authorization"] == "KakaoAK fake-key"
        assert request.url.params["x"] == "127.03" and request.url.params["y"] == "37.5"
        category = request.url.params["category_group_code"]
        queries.append(category)
        return httpx.Response(200, json={"documents": [{
            "id": "10" if category == "FD6" else "20", "place_name": "테스트 매장", "x": "127.031", "y": "37.501",
            "road_address_name": "테스트 도로명", "address_name": "테스트 주소",
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        places = await nearby.kakao_places(http, "fake-key", nearby.DEMO_ORIGIN, meal_price=12_000, cafe_price=5_000)
    assert set(queries) == {"FD6", "CE7"}
    assert [(place.kind, place.price_won, place.map_url) for place in places] == [
        ("meal", 12_000, "https://place.map.kakao.com/10"), ("cafe", 5_000, "https://place.map.kakao.com/20"),
    ]

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(503))) as http:
        with pytest.raises(ApiException, match="검색할 수 없습니다"):
            await nearby.kakao_places(http, "fake-key", nearby.DEMO_ORIGIN, meal_price=12_000, cafe_price=5_000)


async def test_live_plan_uses_owned_active_cards_and_remaining_preview_cap(bank, model, monkeypatch):
    client, me, _, debit, _ = bank
    assert (await pay(client, me, debit, amount=30_000, merchant="빽다방 테스트점")).status_code == 201
    assert (await client.put("/products/benefits", headers=me, json={"offer_ids": ["paiks-10"]})).status_code == 200

    def upstream(request):
        cafe = request.url.params["category_group_code"] == "CE7"
        return httpx.Response(200, json={"documents": [{
            "id": "20" if cafe else "10", "place_name": "빽다방 테스트점" if cafe else "식당 테스트점",
            "x": "127.0301", "y": "37.5001", "road_address_name": "테스트 도로명", "address_name": "테스트 주소",
        }]})

    async def mock_map(origin, *, meal_price, cafe_price):
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
            return await nearby.kakao_places(http, "fake-key", origin, meal_price=meal_price, cafe_price=cafe_price)

    monkeypatch.setattr(benefit_agent, "find_places", mock_map)
    tool_args = {"limits": {"budget_won": 20_000, "available_minutes": 45}}
    model.replies = [call("plan_nearby", **tool_args), AIMessage("코스를 찾았어요.")] * 2
    req = {"mode": "nearby", "message": "밥과 커피 코스", "budget_won": 20_000, "available_minutes": 45,
           "location": nearby.DEMO_ORIGIN.model_dump(), "meal_price_won": 12_000, "cafe_price_won": 5_000,
           "preview_bundle": True}
    first = await client.post("/chat/benefits", headers=me, json=req)
    assert first.status_code == 200, first.text
    plan = first.json()["data"]["plan"]
    assert (plan["source"], plan["price_basis"]) == ("kakao", "user_estimates")
    cafe = plan["routes"][0]["stops"][1]
    assert cafe["discount_won"] == 250 and cafe["benefit"] == "체크카드 카페 5%"
    assert cafe["card_name"].endswith(debit["masked_card_num"][-4:])
    assert (await client.post(f"/cards/{debit['card_id']}/suspend", json={}, headers=me)).status_code == 200

    second = await client.post("/chat/benefits", headers=me, json=req)
    assert second.status_code == 200, second.text
    cafe = second.json()["data"]["plan"]["routes"][0]["stops"][1]
    assert cafe["discount_won"] == 0 and cafe["card_name"] is None


def test_coupon_catalogue_uses_validity_and_verified_source(tmp_path, monkeypatch):
    today = today_kst()
    base = {
        "place_id": "20", "title": "테스트 할인", "minimum_won": 4_000, "discount_won": 500, "requires_channel": False,
        "starts_on": today.isoformat(), "ends_on": today.isoformat(), "source_url": "https://example.com/coupon",
    }
    path = tmp_path / "coupons.json"
    path.write_text(json.dumps([base, base | {"source_url": None}, base | {
        "starts_on": (today - timedelta(days=2)).isoformat(), "ends_on": (today - timedelta(days=1)).isoformat(),
    }]), encoding="utf-8")
    monkeypatch.setattr(nearby, "COUPON_FILE", path)
    assert len(nearby.available_coupons(today, demo=False, allow_channel=False)) == 1
