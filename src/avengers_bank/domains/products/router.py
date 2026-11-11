from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.products.benefit_schemas import BenefitBundle, BenefitSettings, BundleUpdate
from avengers_bank.domains.products.benefits import get_benefits, save_benefits
from avengers_bank.domains.products.schemas import (
    AccountProductDetailResponse,
    AccountProductResponse,
    AccountProductType,
)
from avengers_bank.domains.products.service import product_service
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/products", tags=["products"], responses=error_responses(422))
DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]


@router.get("/benefits", response_model=SuccessResponse[BenefitSettings], responses=error_responses(401))
async def get_benefit_settings(db: DB, me: Me):
    """은행의 혜택 카탈로그와 내 100크레딧 구성안."""
    return SuccessResponse[BenefitSettings](data=await get_benefits(db, me.user_id))


@router.put("/benefits", response_model=SuccessResponse[BenefitBundle], responses=error_responses(400, 401))
async def save_benefit_settings(data: BundleUpdate, db: DB, me: Me):
    """내 혜택 미리보기 구성을 저장한다. 할인율과 비용은 은행의 카탈로그로 검증한다."""
    return SuccessResponse[BenefitBundle](data=await save_benefits(db, me.user_id, data.offer_ids))


@router.get("/accounts", response_model=SuccessResponse[list[AccountProductResponse]])
async def list_account_products(
    db: Annotated[AsyncSession, Depends(get_db)], type: AccountProductType | None = None
):
    products = await product_service.list_account_products(db, type)
    return SuccessResponse[list[AccountProductResponse]](data=products)


@router.get(
    "/accounts/{product_id}",
    response_model=SuccessResponse[AccountProductDetailResponse],
    responses=error_responses(404),
)
async def get_account_product(product_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    product = await product_service.get_account_product(db, product_id)
    return SuccessResponse[AccountProductDetailResponse](data=product)


# 카드 상품 목록 GET /products/cards 는 domains/cards/router.py (카드 도메인이 card_products를 가진다)
