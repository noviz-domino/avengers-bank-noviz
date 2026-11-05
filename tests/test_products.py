from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

from avengers_bank.core.clock import today_kst
from avengers_bank.core.database import SessionLocal
from avengers_bank.core.exceptions import NotFoundException
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.products.service import product_service
from avengers_bank.seed import PRODUCTS, seed_products

pytestmark = pytest.mark.anyio


@pytest.fixture
async def seeded(client):
    async with SessionLocal() as db:
        await seed_products(db)
    return client


async def test_seed_is_idempotent(client):
    async with SessionLocal() as db:
        assert await seed_products(db) == len(PRODUCTS)
    async with SessionLocal() as db:
        assert await seed_products(db) == 0


async def test_list_filters_by_type(seeded):
    response = await seeded.get("/products/accounts", params={"type": "SAVINGS"})
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["data"]]
    assert names == ["스타크 자유적금", "주니어 어벤져스 적금"]

    response = await seeded.get("/products/accounts", params={"type": "CARD"})
    assert response.status_code == 422


async def test_detail_has_preferential_rates(seeded):
    products = (await seeded.get("/products/accounts", params={"type": "SAVINGS"})).json()["data"]
    response = await seeded.get(f"/products/accounts/{products[0]['product_id']}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert [r["code"] for r in data["preferential_rates"]] == ["SALARY_TRANSFER", "MARKETING_AGREED", "FIRST_PRODUCT"]
    assert data["max_preferential_rate"] == "1.00"  # 우대 합계


async def test_detail_not_found(seeded):
    response = await seeded.get("/products/accounts/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_special_offer_only_during_sale(seeded):
    async with SessionLocal() as db:
        def names(products):
            return [p.name for p in products]

        during = await product_service.list_account_products(db, "DEPOSIT", date(2027, 12, 31))
        after = await product_service.list_account_products(db, "DEPOSIT", date(2028, 1, 1))
        assert "쉴드 특판 예금" in names(during)
        assert "쉴드 특판 예금" not in names(after)

        special = next(p for p in during if p.name == "쉴드 특판 예금")
        with pytest.raises(NotFoundException):  # 기간이 끝나면 상세·가입도 안 됨
            await product_service.get_account_product(db, special.product_id, date(2028, 1, 1))


async def test_hidden_when_inactive_or_not_started(seeded):
    async with SessionLocal() as db:
        await db.execute(update(AccountProduct).where(AccountProduct.name == "히어로 정기예금").values(is_active=False))
        await db.commit()

        names = [p.name for p in await product_service.list_account_products(db, "DEPOSIT", date(2026, 11, 5))]
        assert "히어로 정기예금" not in names  # 판매 중지
        before = await product_service.list_account_products(db, "DEPOSIT", date(2026, 10, 31))
        assert "쉴드 특판 예금" not in [p.name for p in before]  # 특판 시작 전


async def test_api_detail_404_after_sale_ends(seeded):
    async with SessionLocal() as db:
        special = await db.scalar(select(AccountProduct).where(AccountProduct.name == "쉴드 특판 예금"))
        special.sale_end = today_kst() - timedelta(days=1)
        await db.commit()
        product_id = special.product_id

    response = await seeded.get(f"/products/accounts/{product_id}")
    assert response.status_code == 404
    names = [p["name"] for p in (await seeded.get("/products/accounts")).json()["data"]]
    assert "쉴드 특판 예금" not in names
