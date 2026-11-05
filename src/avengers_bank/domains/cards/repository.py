from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.cards.models import Card, CardProduct


class CardRepository:
    async def save(self, db: AsyncSession, card: Card) -> Card:
        db.add(card)
        await db.flush()
        return card

    async def last_serial(self, db: AsyncSession, prefix: str) -> int:
        """같은 종류·상품(9410TPP)에서 가장 큰 일련번호. 없으면 0"""
        last = await db.scalar(select(func.max(Card.card_num)).where(Card.card_num.like(f"{prefix}%")))
        return int(last[7:15]) if last else 0

    async def find_products(self, db: AsyncSession, type_: str | None) -> list[CardProduct]:
        query = select(CardProduct).where(CardProduct.is_active.is_(True))
        if type_:
            query = query.where(CardProduct.type == type_)
        return list(await db.scalars(query.order_by(CardProduct.type, CardProduct.product_code)))

    async def find_mine(self, db: AsyncSession, user_id: int) -> list[tuple[Card, str]]:
        rows = await db.execute(
            select(Card, CardProduct.name).join(CardProduct, Card.product_id == CardProduct.product_id)
            .where(Card.user_id == user_id).order_by(Card.card_id)
        )
        return [(c, name) for c, name in rows]

    async def find_by_id(self, db: AsyncSession, card_id: int) -> tuple[Card, str] | None:
        row = (await db.execute(
            select(Card, CardProduct.name).join(CardProduct, Card.product_id == CardProduct.product_id)
            .where(Card.card_id == card_id)
        )).first()
        return tuple(row) if row else None


card_repository = CardRepository()
