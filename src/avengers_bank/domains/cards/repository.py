from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.cards.models import Card, CardProduct, CardTransaction


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

    async def find_by_id(self, db: AsyncSession, card_id: int, lock: bool = False) -> tuple[Card, str] | None:
        """lock=True: 상태를 바꾸기 전 카드 행만 잠근다 (동시 정지·분실·해제가 서로 덮어쓰지 않게)"""
        query = (select(Card, CardProduct.name).join(CardProduct, Card.product_id == CardProduct.product_id)
                 .where(Card.card_id == card_id))
        if lock:
            query = query.with_for_update(of=Card).execution_options(populate_existing=True)
        row = (await db.execute(query)).first()
        return tuple(row) if row else None

    async def find_tx_by_key(self, db: AsyncSession, card_id: int, key: str) -> CardTransaction | None:
        return await db.scalar(select(CardTransaction).where(
            CardTransaction.card_id == card_id, CardTransaction.idempotency_key == key))

    async def find_txs(self, db: AsyncSession, card_id: int) -> list[CardTransaction]:
        return list(await db.scalars(select(CardTransaction).where(CardTransaction.card_id == card_id)
                                     .order_by(CardTransaction.card_tx_id.desc())))

    async def spent_since(self, db: AsyncSession, card_id: int, since: datetime) -> int:
        """취소하지 않은 사용액 합계 (1일 한도). 누적액은 저장하지 않고 계산한다 (ERD 규칙 11)"""
        return await db.scalar(select(func.coalesce(func.sum(CardTransaction.amount), 0)).where(
            CardTransaction.card_id == card_id, CardTransaction.status == "APPROVED",
            CardTransaction.approved_at >= since))

    async def unpaid_credit(self, db: AsyncSession, card_id: int) -> int:
        """신용카드의 안 갚은 사용액 (신용 한도, ADR 0010)"""
        return await db.scalar(select(func.coalesce(func.sum(CardTransaction.amount), 0)).where(
            CardTransaction.card_id == card_id, CardTransaction.status == "APPROVED",
            CardTransaction.billing_status != "PAID"))


card_repository = CardRepository()
