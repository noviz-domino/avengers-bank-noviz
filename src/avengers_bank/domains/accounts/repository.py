from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.domains.accounts.models import Account, AccountTerms, AccountTransaction
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

    # TODO: find_by_account_num, sum_today_transfer_out (이체 PR, ERD 규칙 12)


account_repository = AccountRepository()
