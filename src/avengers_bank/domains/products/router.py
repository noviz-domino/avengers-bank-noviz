from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.products.schemas import (
    AccountProductDetailResponse,
    AccountProductResponse,
    AccountProductType,
)
from avengers_bank.domains.products.service import product_service

router = APIRouter(prefix="/products", tags=["products"], responses=error_responses(422))


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


# TODO: GET /products/cards?type=               카드 상품 목록 (카드 기능 PR)
