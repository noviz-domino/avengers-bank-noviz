from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import NotFoundException
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.products.repository import product_repository


class ProductService:
    async def list_account_products(
        self, db: AsyncSession, type_: str | None, today: date | None = None
    ) -> list[AccountProduct]:
        return await product_repository.find_account_products(db, type_, today or today_kst())

    async def get_account_product(
        self, db: AsyncSession, product_id: int, today: date | None = None
    ) -> AccountProduct:
        """판매 중인 상품만. 판매가 끝났거나 특판 기간이 아니면 404 (계좌 개설에서도 이걸 쓴다)"""
        product = await product_repository.find_account_product_on_sale(
            db, product_id, today or today_kst()
        )
        if product is None:
            raise NotFoundException(message="판매 중인 상품이 아닙니다.", code="PRODUCT_NOT_FOUND")
        return product

    # TODO: 가입 조건 검사(나이·기간·금액)는 계좌 개설 PR에서 여기에 둔다


product_service = ProductService()
