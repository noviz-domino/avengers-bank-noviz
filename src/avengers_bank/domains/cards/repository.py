from datetime import datetime

from sqlalchemy import func, or_, select, update
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

    async def used_merchant_since(self, db: AsyncSession, card_id: int, merchant_name: str, since: datetime) -> bool:
        # shortcut: 시뮬레이터는 가맹점 이름으로 비교하며, 결제망 연동 시 가맹점 식별자를 사용한다.
        match = select(CardTransaction.card_tx_id).where(
            CardTransaction.card_id == card_id, CardTransaction.merchant_name == merchant_name,
            CardTransaction.status == "APPROVED", CardTransaction.approved_at >= since,
        )
        return bool(await db.scalar(select(match.exists())))

    async def find_txs(
        self, db: AsyncSession, card_id: int, since: datetime | None = None, before: datetime | None = None
    ) -> list[CardTransaction]:
        query = select(CardTransaction).where(CardTransaction.card_id == card_id)
        if since is not None:
            query = query.where(CardTransaction.approved_at >= since)
        if before is not None:
            query = query.where(CardTransaction.approved_at < before)
        return list(await db.scalars(query.order_by(CardTransaction.card_tx_id.desc())))

    async def search_txs(
        self, db: AsyncSession, user_id: int, *, card_id: int | None, keyword: str | None, category: str | None,
        since: datetime | None, before: datetime | None, limit: int = 100,
    ) -> tuple[list[CardTransaction], int, int]:
        """내 카드들의 사용내역 검색: (최근 limit건, 승인 합계, 전체 건수). 합계·건수는 조건 전체 기준"""
        where = [Card.user_id == user_id]
        if card_id is not None:
            where.append(CardTransaction.card_id == card_id)
        if keyword:
            where.append(CardTransaction.merchant_name.contains(keyword, autoescape=True))
        if category:
            where.append(CardTransaction.category == category)
        if since is not None:
            where.append(CardTransaction.approved_at >= since)
        if before is not None:
            where.append(CardTransaction.approved_at < before)
        base = select(CardTransaction).join(Card, Card.card_id == CardTransaction.card_id).where(*where)
        rows = list(await db.scalars(base.order_by(CardTransaction.card_tx_id.desc()).limit(limit)))
        total, count = (await db.execute(select(
            func.coalesce(func.sum(CardTransaction.amount).filter(CardTransaction.status == "APPROVED"), 0),
            func.count(),
        ).select_from(CardTransaction).join(Card, Card.card_id == CardTransaction.card_id).where(*where))).one()
        return rows, total, count

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

    async def has_overdue(self, db: AsyncSession, card_id: int) -> bool:
        """청구됐는데 못 낸(BILLED) 사용분이 있나. 출금되면 같은 트랜잭션에서 PAID가 돼서 BILLED는 연체뿐이다"""
        return await db.scalar(select(func.count()).where(
            CardTransaction.card_id == card_id, CardTransaction.status == "APPROVED",
            CardTransaction.billing_status == "BILLED")) > 0

    async def cards_to_bill(self, db: AsyncSession, day: int) -> list[int]:
        """오늘이 결제일인 신용카드 + 연체가 있는 카드 (정지·분실 카드도 빚은 남아서 포함)"""
        overdue = select(CardTransaction.card_id).where(
            CardTransaction.status == "APPROVED", CardTransaction.billing_status == "BILLED")
        return list(await db.scalars(select(Card.card_id).where(
            Card.card_type == "CREDIT", or_(Card.payment_day == day, Card.card_id.in_(overdue))
        ).order_by(Card.card_id)))

    async def bill(self, db: AsyncSession, card_id: int, before: datetime) -> None:
        """결제일 0시 전에 쓴 UNBILLED를 BILLED로"""
        await db.execute(update(CardTransaction).where(
            CardTransaction.card_id == card_id, CardTransaction.status == "APPROVED",
            CardTransaction.billing_status == "UNBILLED", CardTransaction.approved_at < before,
        ).values(billing_status="BILLED"))

    async def find_billed(self, db: AsyncSession, card_id: int) -> list[CardTransaction]:
        return list(await db.scalars(select(CardTransaction).where(
            CardTransaction.card_id == card_id, CardTransaction.status == "APPROVED",
            CardTransaction.billing_status == "BILLED",
        ).execution_options(populate_existing=True)))

    async def find_pending_refunds(self, db: AsyncSession) -> list[tuple[CardTransaction, Card]]:
        """환불 대기: 돈이 나간 결제(체크, 낸 신용)를 취소했는데 환불 줄이 없음 (ADR 0012).
        조건은 CardTransaction.refund_pending과 같아야 한다 (test_pending_list_matches_property)"""
        return [tuple(r) for r in await db.execute(select(CardTransaction, Card).join(
            Card, Card.card_id == CardTransaction.card_id).where(
            CardTransaction.status == "CANCELED", CardTransaction.refund_tx_id.is_(None),
            or_(CardTransaction.account_tx_id.is_not(None), CardTransaction.billing_status == "PAID"),
        ).order_by(CardTransaction.card_tx_id))]


card_repository = CardRepository()
