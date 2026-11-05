from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import ApiException, BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.account_number import BANK_CODE, TYPE_CODES, make_account_num
from avengers_bank.domains.accounts.models import Account, AccountTerms
from avengers_bank.domains.accounts.money import TransferRejected, execute_transfer
from avengers_bank.domains.accounts.repository import account_repository
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.accounts.schemas import (
    AccountCreate,
    AccountDetailResponse,
    AccountListResponse,
    AccountSummaryResponse,
    AccountTermsResponse,
    DepositCreate,
    TransactionFilter,
    TransactionResponse,
    TransactionSearchResponse,
    TransactionUpdate,
)
from avengers_bank.domains.products.eligibility import add_months, applied_rate, check_eligibility
from avengers_bank.domains.products.models import AccountProduct
from avengers_bank.domains.products.service import product_service
from avengers_bank.domains.users.models import User
from avengers_bank.domains.users.schemas import UserResponse

# 입출금 계좌의 기본 이체 한도. 올리는 것은 보안을 약하게 해서 승인 기능과 함께 만든다
DEFAULT_PER_TRANSFER_LIMIT = 1_000_000
DEFAULT_DAILY_TRANSFER_LIMIT = 5_000_000
MAX_SERIAL = 999_999  # 계좌번호 NNNNNN
APPROVAL_TTL = timedelta(minutes=10)


def deposit_payload(data: DepositCreate) -> dict:
    return {"product_id": data.product_id, "from_account_id": data.from_account_id, "amount": data.amount,
            "term_months": data.term_months, "nickname": data.nickname}


def summary(account: Account, product_name: str) -> AccountSummaryResponse:
    return AccountSummaryResponse(
        account_id=account.account_id, account_type=account.account_type,
        account_num=account.account_num, product_name=product_name, nickname=account.nickname,
        balance=account.balance, status=account.status, opened_at=account.opened_at,
    )


def not_found() -> NotFoundException:
    # 남의 계좌도 404: 403을 주면 그 계좌가 있다는 것을 알려 주게 된다
    return NotFoundException(message="계좌를 찾을 수 없습니다.", code="ACCOUNT_NOT_FOUND")


async def create_account(
    db: AsyncSession, *, user_id: int, birth_date, marketing_agreed: bool, product: AccountProduct,
    nickname: str | None, term_months: int | None = None, amount: int | None = None,
    monthly_payment: int | None = None, payment_day: int | None = None,
) -> tuple[Account, AccountTerms | None]:
    """가입 조건 검사 → 계좌번호 → 계좌 + (예·적금이면) 조건 저장. 잔액은 0. 호출한 쪽의 트랜잭션 안에서.

    입출금·적금은 바로(open_account), 예금은 승인 뒤 실행기(run_open_deposit)가 이 함수를 쓴다.
    """
    today = today_kst()
    # 적금은 월 납입금, 예금은 맡기는 금액이 상품의 금액 범위 대상
    check_eligibility(
        product, birth_date=birth_date, today=today, term_months=term_months,
        amount=monthly_payment if product.type == "SAVINGS" else amount,
    )
    prefix = f"{BANK_CODE}-{TYPE_CODES[product.type]}{product.product_code:02d}-"
    serial = await account_repository.last_serial(db, prefix) + 1
    if serial > MAX_SERIAL:
        raise ConflictException(message="이 상품은 더 이상 계좌를 만들 수 없습니다.", code="ACCOUNT_NUM_EXHAUSTED")
    account = Account(
        user_id=user_id, product_id=product.product_id, account_type=product.type,
        account_num=make_account_num(product.type, product.product_code, serial),
        nickname=nickname, balance=0, status="ACTIVE",
    )
    if product.type == "CHECKING":
        account.per_transfer_limit = DEFAULT_PER_TRANSFER_LIMIT
        account.daily_transfer_limit = DEFAULT_DAILY_TRANSFER_LIMIT

    met = {"MARKETING_AGREED"} if marketing_agreed else set()
    if not await account_repository.has_deposit_or_savings(db, user_id):
        met.add("FIRST_PRODUCT")
    # shortcut: 같은 상품을 동시에 개설하면 일련번호가 겹쳐 409. 자주 생기면 DB 시퀀스로 바꾼다
    try:
        await account_repository.save(db, account)
    except IntegrityError as e:
        if "account_num" not in str(e.orig):  # 번호 중복만 409, 다른 제약 위반은 버그라서 그대로 500
            raise
        raise ConflictException(message="잠시 후 다시 시도해 주세요.", code="ACCOUNT_NUM_CONFLICT") from None

    terms = None
    if product.type in ("DEPOSIT", "SAVINGS"):
        # 급여이체(SALARY_TRANSFER)는 개설 때 알 수 없어서 적용하지 않는다
        rate = applied_rate(product, met)
        savings = product.type == "SAVINGS"
        terms = await account_repository.save(db, AccountTerms(
            account_id=account.account_id, applied_rate=rate.rate, rate_detail=rate.detail,
            maturity_date=add_months(today, term_months),
            monthly_payment=monthly_payment if savings else None,
            payment_day=(payment_day or min(today.day, 28)) if savings else None,
        ))
    return account, terms


async def run_open_deposit(db: AsyncSession, action: PendingAction) -> None:
    """승인된 예금 개설 실행기 (approvals/service.py EXECUTORS). 승인과 같은 트랜잭션 안에서:
    상품·가입 조건을 다시 확인 → 예금 계좌 생성 → 맡길 돈을 입출금 계좌에서 옮김."""
    p = action.payload
    user = await db.get(User, action.user_id)
    # 출금 계좌를 먼저 잠그고 검사한다: 계좌번호를 만들기 전에 분명한 이유(잔액 부족 등)로 실패하게.
    # 빈 예금 계좌가 남지 않는 것 자체는 아래 savepoint가 보장한다
    src = await db.scalar(
        select(Account).where(Account.account_id == p["from_account_id"])
        .with_for_update().execution_options(populate_existing=True)
    )
    if src is None or src.user_id != action.user_id or src.status != "ACTIVE" or src.account_type != "CHECKING":
        raise TransferRejected("ACCOUNT_NOT_FOUND", "출금할 내 입출금 계좌를 찾을 수 없습니다.")
    if p["amount"] > src.balance:
        raise TransferRejected("INSUFFICIENT_BALANCE", "잔액이 부족합니다.")
    # 계좌 생성 + 이동을 savepoint로 묶는다: 어느 쪽이 실패해도 이 부분만 되돌리고
    # 바깥 트랜잭션(승인 대기를 FAILED로 바꾸는 것)은 살아 있다. 빈 예금 계좌가 남지 않는 것을 순서가 아니라 구조로 보장
    try:
        async with db.begin_nested():
            product = await product_service.get_account_product(db, p["product_id"])  # 그사이 판매가 끝났을 수 있음
            account, _ = await create_account(
                db, user_id=user.user_id, birth_date=user.birth_date, marketing_agreed=user.marketing_agreed,
                product=product, nickname=p.get("nickname"), term_months=p["term_months"], amount=p["amount"],
            )
            await execute_transfer(
                db, owner_user_id=action.user_id, from_account_id=p["from_account_id"],
                to_account_id=account.account_id, amount=p["amount"], action_id=action.action_id,
                memo="예금 가입", opening_deposit=True,
            )
    except ApiException as e:  # 실행 직전 재검사 실패(판매 종료, 가입 조건, 번호 충돌) → FAILED, 돈은 안 움직임
        raise TransferRejected(e.code, e.message) from None
    # 요청 내용(payload)은 바꾸지 않는다: 멱등키 비교에 쓰인다. 결과는 따로 남긴다
    action.result = {"account_id": account.account_id}


class AccountService:
    async def open_account(self, db: AsyncSession, user: UserResponse, data: AccountCreate) -> AccountDetailResponse:
        """입출금·적금은 바로 연다. 예금은 돈이 움직여서 request_deposit(승인 대기)으로"""
        async with db.begin():
            product = await product_service.get_account_product(db, data.product_id)
            if product.type == "DEPOSIT":
                raise BadRequestException(
                    message="예금은 맡길 돈을 옮겨야 해서 POST /accounts/deposits로 신청합니다.",
                    code="DEPOSIT_NEEDS_TRANSFER",
                )
            if product.type not in ("CHECKING", "SAVINGS"):
                raise BadRequestException(message="계좌로 개설할 수 없는 상품입니다.", code="PRODUCT_NOT_OPENABLE")
            account, terms = await create_account(
                db, user_id=user.user_id, birth_date=user.birth_date, marketing_agreed=user.marketing_agreed,
                product=product, nickname=data.nickname, term_months=data.term_months,
                monthly_payment=data.monthly_payment, payment_day=data.payment_day,
            )
            await db.refresh(account)
            return self._detail(account, product.name, terms)

    async def request_deposit(
        self, db: AsyncSession, user: UserResponse, data: DepositCreate
    ) -> tuple[PendingAction, bool]:
        """예금 개설 신청: 조건과 출금 계좌를 미리 검사하고 승인 대기만 만든다 (ADR 0004·0008)"""
        async with db.begin():
            existing = await approval_repository.find_by_key(db, user.user_id, data.idempotency_key)
            if existing is not None:
                if existing.action_type != "OPEN_DEPOSIT" or existing.payload != deposit_payload(data):  # 요청 내용만 비교
                    raise ConflictException(
                        message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
                    )
                return existing, False

            product = await product_service.get_account_product(db, data.product_id)
            if product.type != "DEPOSIT":
                raise BadRequestException(message="예금 상품이 아닙니다.", code="PRODUCT_NOT_OPENABLE")
            check_eligibility(product, birth_date=user.birth_date, today=today_kst(),
                              term_months=data.term_months, amount=data.amount)
            src = await db.get(Account, data.from_account_id)
            if src is None or src.user_id != user.user_id or src.status != "ACTIVE" or src.account_type != "CHECKING":
                raise BadRequestException(message="출금할 내 입출금 계좌를 찾을 수 없습니다.", code="ACCOUNT_NOT_FOUND")
            if data.amount > src.balance:
                raise BadRequestException(message="잔액이 부족합니다.", code="INSUFFICIENT_BALANCE")

            action = PendingAction(
                user_id=user.user_id, action_type="OPEN_DEPOSIT", requested_by="WEB",
                idempotency_key=data.idempotency_key, expires_at=datetime.now(UTC) + APPROVAL_TTL,
                payload=deposit_payload(data),
                summary=(f"{src.nickname or '내 계좌'}({src.account_num})에서 {data.amount:,}원을 "
                         f"{product.name} {data.term_months}개월에 맡기기"),
            )
            try:
                await approval_repository.save(db, action)
            except IntegrityError as e:
                if "idempotency_key" not in str(e.orig):
                    raise
                raise ConflictException(message="같은 요청을 처리하고 있습니다.", code="DUPLICATE_REQUEST") from None
            return action, True

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

    async def search_transactions(self, db: AsyncSession, user_id: int, f: TransactionFilter) -> TransactionSearchResponse:
        if f.account_id is not None:
            await self.get_my_account(db, user_id, f.account_id)  # 남의 계좌면 404 (빈 결과로 숨기지 않고 명확히)
        rows, has_more, total_in, total_out = await account_repository.search_transactions(db, user_id, f)
        return TransactionSearchResponse(
            transactions=[TransactionResponse.model_validate(r) for r in rows],
            total_in=total_in, total_out=total_out,
            next_before=rows[-1].tx_id if has_more else None,
        )

    async def update_transaction(
        self, db: AsyncSession, user_id: int, tx_id: int, data: TransactionUpdate
    ) -> TransactionResponse:
        async with db.begin():
            tx = await account_repository.find_my_transaction(db, user_id, tx_id)
            if tx is None:
                raise NotFoundException(message="거래를 찾을 수 없습니다.", code="TRANSACTION_NOT_FOUND")
            for field in data.model_fields_set:  # 보낸 칸만 바꾼다 (null이면 지움)
                setattr(tx, field, getattr(data, field))
        return TransactionResponse.model_validate(tx)

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

    # TODO: 이체 한도 변경(올리는 것은 승인 필요)
    # TODO: close_account — 잔액 0일 때만 (ADR 0006)


account_service = AccountService()
