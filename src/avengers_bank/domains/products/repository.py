from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.products.models import AccountProduct


def on_sale(today: date):
    """판매 중: is_active이고, 특판 기간이 있으면 오늘이 그 안에 있음"""
    return (
        AccountProduct.is_active.is_(True),
        or_(AccountProduct.sale_start.is_(None), AccountProduct.sale_start <= today),
        or_(AccountProduct.sale_end.is_(None), AccountProduct.sale_end >= today),
    )


class ProductRepository:
    async def find_account_products(
        self, db: AsyncSession, type_: str | None, today: date
    ) -> list[AccountProduct]:
        query = select(AccountProduct).where(*on_sale(today))
        if type_ is not None:
            query = query.where(AccountProduct.type == type_)
        return list(await db.scalars(query.order_by(AccountProduct.type, AccountProduct.product_code)))

    async def find_account_product_on_sale(
        self, db: AsyncSession, product_id: int, today: date
    ) -> AccountProduct | None:
        return await db.scalar(
            select(AccountProduct).where(AccountProduct.product_id == product_id, *on_sale(today))
        )

    # TODO: 카드 상품 조회는 카드 기능 PR에서


product_repository = ProductRepository()
