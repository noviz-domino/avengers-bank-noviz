from datetime import UTC, datetime, time, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import KST
from avengers_bank.domains.accounts.models import Account, AccountTerms, AccountTransaction
from avengers_bank.domains.accounts.schemas import TransactionFilter
from avengers_bank.domains.products.models import AccountProduct


class AccountRepository:
    async def save(self, db: AsyncSession, obj):
        db.add(obj)
        await db.flush()
        return obj

    async def last_serial(self, db: AsyncSession, prefix: str) -> int:
        """같은 종류·상품(110-TPP-)에서 가장 큰 일련번호. 없으면 0"""
        last = await db.scalar(
            select(func.max(Account.account_num)).where(Account.account_num.like(f"{prefix}%"))
        )
        return int(last[-6:]) if last else 0

    async def find_all_by_user_id(self, db: AsyncSession, user_id: int) -> list[tuple[Account, str]]:
        """해지하지 않은 내 계좌와 상품명, 잔액 많은 순"""
        rows = await db.execute(
            select(Account, AccountProduct.name)
            .join(AccountProduct, Account.product_id == AccountProduct.product_id)
            .where(Account.user_id == user_id, Account.status != "CLOSED")
            .order_by(Account.balance.desc(), Account.account_id)
        )
        return [(a, name) for a, name in rows]

    async def find_by_id(self, db: AsyncSession, account_id: int) -> tuple[Account, str, AccountTerms | None] | None:
        row = (await db.execute(
            select(Account, AccountProduct.name, AccountTerms)
            .join(AccountProduct, Account.product_id == AccountProduct.product_id)
            .outerjoin(AccountTerms, AccountTerms.account_id == Account.account_id)
            .where(Account.account_id == account_id)
        )).first()
        return tuple(row) if row else None

    async def has_deposit_or_savings(self, db: AsyncSession, user_id: int) -> bool:
        return await db.scalar(select(exists().where(
            Account.user_id == user_id, Account.account_type.in_(("DEPOSIT", "SAVINGS"))
        )))

    async def find_transactions(
        self, db: AsyncSession, account_id: int, limit: int, before_tx_id: int | None
    ) -> list[AccountTransaction]:
        """최근 거래부터. 다음 쪽은 받은 마지막 tx_id를 before로 넘긴다 (tx_id는 기록 순서와 같음)

        shortcut: account_id로 걸러서 tx_id로 정렬한다. (account_id, created_at) 인덱스로 거른 뒤 정렬하는데,
        계좌 하나의 거래가 수만 건이 되면 (account_id, tx_id) 인덱스를 추가한다.
        """
        query = select(AccountTransaction).where(AccountTransaction.account_id == account_id)
        if before_tx_id is not None:
            query = query.where(AccountTransaction.tx_id < before_tx_id)
        return list(await db.scalars(query.order_by(AccountTransaction.tx_id.desc()).limit(limit)))

    def _filtered(self, user_id: int, f: TransactionFilter):
        """내 계좌의 거래만 (남의 계좌 id를 넣어도 결과 없음). 조건은 모두 AND"""
        conds = [Account.user_id == user_id]
        if f.account_id is not None:
            conds.append(AccountTransaction.account_id == f.account_id)
        if f.from_date:  # 한국 날짜 00:00을 UTC로 바꿔서 비교 (SQLite는 시간대를 버림)
            conds.append(AccountTransaction.created_at >= kst_midnight_utc(f.from_date))
        if f.to_date:
            conds.append(AccountTransaction.created_at < kst_midnight_utc(f.to_date + timedelta(days=1)))
        if f.min_amount is not None:
            conds.append(func.abs(AccountTransaction.amount) >= f.min_amount)
        if f.max_amount is not None:
            conds.append(func.abs(AccountTransaction.amount) <= f.max_amount)
        if f.keyword:  # autoescape: 검색어의 %, _를 글자 그대로
            conds.append(or_(
                AccountTransaction.memo.icontains(f.keyword, autoescape=True),
                AccountTransaction.counterparty_name.icontains(f.keyword, autoescape=True),
            ))
        if f.direction == "IN":
            conds.append(AccountTransaction.amount > 0)
        elif f.direction == "OUT":
            conds.append(AccountTransaction.amount < 0)
        if f.category:
            conds.append(AccountTransaction.category == f.category)
        return conds

    async def search_transactions(
        self, db: AsyncSession, user_id: int, f: TransactionFilter
    ) -> tuple[list[AccountTransaction], bool, int, int]:
        """(이번 쪽 거래, 다음 쪽이 있는지, 들어온 합계, 나간 합계). 합계는 쪽과 상관없이 조건 전체"""
        conds = self._filtered(user_id, f)
        base = select(AccountTransaction).join(Account, Account.account_id == AccountTransaction.account_id)
        page = base.where(*conds)
        if f.before is not None:
            page = page.where(AccountTransaction.tx_id < f.before)
        rows = list(await db.scalars(page.order_by(AccountTransaction.tx_id.desc()).limit(f.limit + 1)))
        has_more = len(rows) > f.limit  # 하나 더 읽어 봐서 다음 쪽이 있는지 안다
        rows = rows[:f.limit]
        total_in, total_out = (await db.execute(
            select(
                func.coalesce(func.sum(AccountTransaction.amount).filter(AccountTransaction.amount > 0), 0),
                func.coalesce(func.sum(AccountTransaction.amount).filter(AccountTransaction.amount < 0), 0),
            ).join(Account, Account.account_id == AccountTransaction.account_id).where(*conds)
        )).one()
        return rows, has_more, total_in, -total_out

    async def find_my_transaction(self, db: AsyncSession, user_id: int, tx_id: int) -> AccountTransaction | None:
        return await db.scalar(
            select(AccountTransaction).join(Account, Account.account_id == AccountTransaction.account_id)
            .where(AccountTransaction.tx_id == tx_id, Account.user_id == user_id)
        )


def kst_midnight_utc(day) -> datetime:
    return datetime.combine(day, time(0), KST).astimezone(UTC)


account_repository = AccountRepository()
