from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.account_number import BANK_CODE, TYPE_CODES, make_account_num
from avengers_bank.domains.accounts.models import Account, AccountTerms
from avengers_bank.domains.accounts.repository import account_repository
from avengers_bank.domains.accounts.schemas import (
    AccountCreate,
    AccountDetailResponse,
    AccountListResponse,
    AccountSummaryResponse,
    AccountTermsResponse,
)
from avengers_bank.domains.products.eligibility import add_months, applied_rate, check_eligibility
from avengers_bank.domains.products.service import product_service
from avengers_bank.domains.users.schemas import UserResponse

# 입출금 계좌의 기본 이체 한도. 올리는 것은 보안을 약하게 해서 승인 기능과 함께 만든다
DEFAULT_PER_TRANSFER_LIMIT = 1_000_000
DEFAULT_DAILY_TRANSFER_LIMIT = 5_000_000


def summary(account: Account, product_name: str) -> AccountSummaryResponse:
    return AccountSummaryResponse(
        account_id=account.account_id, account_type=account.account_type,
        account_num=account.account_num, product_name=product_name, nickname=account.nickname,
        balance=account.balance, status=account.status, opened_at=account.opened_at,
    )


def not_found() -> NotFoundException:
    # 남의 계좌도 404: 403을 주면 그 계좌가 있다는 것을 알려 주게 된다
    return NotFoundException(message="계좌를 찾을 수 없습니다.", code="ACCOUNT_NOT_FOUND")


class AccountService:
    async def open_account(self, db: AsyncSession, user: UserResponse, data: AccountCreate) -> AccountDetailResponse:
        async with db.begin():
            product = await product_service.get_account_product(db, data.product_id)
            if product.type == "DEPOSIT":
                raise BadRequestException(
                    message="예금은 맡길 돈을 입출금 계좌에서 옮겨야 해서 이체 기능과 함께 열 수 있습니다.",
                    code="DEPOSIT_NEEDS_TRANSFER",
                )
            if product.type not in ("CHECKING", "SAVINGS"):
                raise BadRequestException(message="계좌로 개설할 수 없는 상품입니다.", code="PRODUCT_NOT_OPENABLE")

            today = today_kst()
            check_eligibility(
                product, birth_date=user.birth_date, today=today,
                term_months=data.term_months, amount=data.monthly_payment,
            )

            prefix = f"{BANK_CODE}-{TYPE_CODES[product.type]}{product.product_code:02d}-"
            serial = await account_repository.last_serial(db, prefix) + 1
            account = Account(
                user_id=user.user_id, product_id=product.product_id, account_type=product.type,
                account_num=make_account_num(product.type, product.product_code, serial),
                nickname=data.nickname, balance=0, status="ACTIVE",
            )
            if product.type == "CHECKING":
                account.per_transfer_limit = DEFAULT_PER_TRANSFER_LIMIT
                account.daily_transfer_limit = DEFAULT_DAILY_TRANSFER_LIMIT

            met = {"MARKETING_AGREED"} if user.marketing_agreed else set()
            if not await account_repository.has_deposit_or_savings(db, user.user_id):
                met.add("FIRST_PRODUCT")
            # shortcut: 같은 상품을 동시에 개설하면 일련번호가 겹쳐 409. 자주 생기면 DB 시퀀스로 바꾼다
            try:
                await account_repository.save(db, account)
            except IntegrityError:
                raise ConflictException(
                    message="잠시 후 다시 시도해 주세요.", code="ACCOUNT_NUM_CONFLICT"
                ) from None

            terms = None
            if product.type == "SAVINGS":
                # 급여이체(SALARY_TRANSFER)는 개설 때 알 수 없어서 적용하지 않는다
                rate = applied_rate(product, met)
                terms = await account_repository.save(db, AccountTerms(
                    account_id=account.account_id, applied_rate=rate.rate, rate_detail=rate.detail,
                    maturity_date=add_months(today, data.term_months),
                    monthly_payment=data.monthly_payment, payment_day=data.payment_day or min(today.day, 28),
                ))
            await db.refresh(account)
            return self._detail(account, product.name, terms)

    async def list_my_accounts(self, db: AsyncSession, user_id: int) -> AccountListResponse:
        rows = await account_repository.find_all_by_user_id(db, user_id)
        return AccountListResponse(
            total_balance=sum(a.balance for a, _ in rows),
            accounts=[summary(a, name) for a, name in rows],
        )

    async def get_my_account(self, db: AsyncSession, user_id: int, account_id: int) -> AccountDetailResponse:
        found = await account_repository.find_by_id(db, account_id)
        if found is None or found[0].user_id != user_id:
            raise not_found()
        return self._detail(*found)

    async def list_transactions(
        self, db: AsyncSession, user_id: int, account_id: int, limit: int, before: int | None
    ):
        await self.get_my_account(db, user_id, account_id)  # 소유권 검사
        return await account_repository.find_transactions(db, account_id, limit, before)

    async def rename(self, db: AsyncSession, user_id: int, account_id: int, nickname: str | None) -> AccountDetailResponse:
        async with db.begin():
            found = await account_repository.find_by_id(db, account_id)
            if found is None or found[0].user_id != user_id:
                raise not_found()
            found[0].nickname = nickname
        return self._detail(*found)

    def _detail(self, account: Account, product_name: str, terms: AccountTerms | None) -> AccountDetailResponse:
        return AccountDetailResponse(
            **summary(account, product_name).model_dump(),
            per_transfer_limit=account.per_transfer_limit,
            daily_transfer_limit=account.daily_transfer_limit,
            terms=AccountTermsResponse.model_validate(terms) if terms else None,
        )

    # TODO: 예금 개설(맡길 돈 이체 포함)과 이체 한도 변경은 이체·승인 PR에서
    # TODO: close_account — 잔액 0일 때만 (ADR 0006)


account_service = AccountService()
