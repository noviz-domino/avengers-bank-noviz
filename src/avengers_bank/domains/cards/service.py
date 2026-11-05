"""카드 발급·조회·정지·해제 (ADR 0009). 결제는 카드 결제 PR에서 실행 함수(ADR 0007)를 거친다"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.exceptions import BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.cards.card_number import make_card_num, mask, prefix
from avengers_bank.domains.cards.models import Card, CardProduct
from avengers_bank.domains.cards.repository import card_repository
from avengers_bank.domains.cards.schemas import CardIssue, CardResponse

# 기본 한도. 올리는 것은 보안을 약하게 해서 승인 기능과 함께 만든다 (ADR 0009)
DEBIT_DAILY_LIMIT = 1_000_000
CREDIT_DAILY_LIMIT = 1_000_000
CREDIT_MONTHLY_LIMIT = 3_000_000
DEFAULT_PAYMENT_DAY = 14
MAX_SERIAL = 99_999_999
APPROVAL_TTL = timedelta(minutes=10)


def response(card: Card, product_name: str) -> CardResponse:
    return CardResponse(
        card_id=card.card_id, card_type=card.card_type, product_name=product_name,
        masked_card_num=mask(card.card_num), nickname=card.nickname, linked_account_id=card.linked_account_id,
        daily_limit=card.daily_limit, monthly_limit=card.monthly_limit, payment_day=card.payment_day,
        status=card.status, issued_at=card.issued_at,
    )


def not_found() -> NotFoundException:
    return NotFoundException(message="카드를 찾을 수 없습니다.", code="CARD_NOT_FOUND")  # 남의 카드도 404 (ADR 0008)


async def run_unsuspend_card(db: AsyncSession, action: PendingAction) -> None:
    """승인된 정지 해제 (approvals EXECUTORS). 그사이 분실 신고됐으면 풀지 않는다"""
    found = await card_repository.find_by_id(db, action.payload["card_id"], lock=True)
    card = found[0] if found else None
    if card is None or card.user_id != action.user_id:
        raise TransferRejected("CARD_NOT_FOUND", "카드를 찾을 수 없습니다.")
    if card.status != "SUSPENDED":
        raise TransferRejected("CARD_NOT_SUSPENDED", "정지된 카드가 아닙니다.")
    card.status = "ACTIVE"


class CardService:
    async def list_products(self, db: AsyncSession, type_: str | None) -> list[CardProduct]:
        return await card_repository.find_products(db, type_)

    async def issue(self, db: AsyncSession, user_id: int, data: CardIssue) -> CardResponse:
        async with db.begin():
            product = await db.get(CardProduct, data.product_id)
            if product is None or not product.is_active:
                raise NotFoundException(message="판매 중인 카드 상품이 아닙니다.", code="CARD_PRODUCT_NOT_FOUND")
            account = await db.get(Account, data.linked_account_id)
            if (account is None or account.user_id != user_id or account.status != "ACTIVE"
                    or account.account_type != "CHECKING"):  # 카드 주인 = 결제 계좌 주인 (ERD 규칙 10)
                raise BadRequestException(message="결제 계좌는 내 입출금 계좌여야 합니다.", code="ACCOUNT_NOT_FOUND")
            serial = await card_repository.last_serial(db, prefix(product.type, product.product_code)) + 1
            if serial > MAX_SERIAL:
                raise ConflictException(message="이 상품은 더 이상 발급할 수 없습니다.", code="CARD_NUM_EXHAUSTED")
            credit = product.type == "CREDIT"
            card = Card(
                user_id=user_id, product_id=product.product_id, linked_account_id=account.account_id,
                card_type=product.type, card_num=make_card_num(product.type, product.product_code, serial),
                nickname=data.nickname, status="ACTIVE",
                daily_limit=CREDIT_DAILY_LIMIT if credit else DEBIT_DAILY_LIMIT,
                monthly_limit=CREDIT_MONTHLY_LIMIT if credit else None,
                payment_day=(data.payment_day or DEFAULT_PAYMENT_DAY) if credit else None,
            )
            # shortcut: 같은 상품을 동시에 발급하면 번호가 겹쳐 409 (계좌번호와 같은 방식, ADR 0008)
            try:
                await card_repository.save(db, card)
            except IntegrityError as e:
                if "card_num" not in str(e.orig):
                    raise
                raise ConflictException(message="잠시 후 다시 시도해 주세요.", code="CARD_NUM_CONFLICT") from None
            await db.refresh(card)
            return response(card, product.name)

    async def list_mine(self, db: AsyncSession, user_id: int) -> list[CardResponse]:
        return [response(c, name) for c, name in await card_repository.find_mine(db, user_id)]

    async def get_mine(self, db: AsyncSession, user_id: int, card_id: int) -> CardResponse:
        found = await card_repository.find_by_id(db, card_id)
        if found is None or found[0].user_id != user_id:
            raise not_found()
        return response(*found)

    async def suspend(self, db: AsyncSession, user_id: int, card_id: int, reason: str) -> CardResponse:
        """정지·분실 신고는 안전해지는 쪽이라 바로 (ADR 0004). 분실은 되돌릴 수 없다"""
        async with db.begin():
            found = await card_repository.find_by_id(db, card_id, lock=True)
            if found is None or found[0].user_id != user_id:
                raise not_found()
            card = found[0]
            if card.status == "LOST":
                raise ConflictException(message="분실 신고된 카드입니다. 재발급해 주세요.", code="CARD_LOST")
            card.status = reason
        return response(*found)

    async def request_unsuspend(
        self, db: AsyncSession, user_id: int, card_id: int, idempotency_key: str
    ) -> tuple[PendingAction, bool]:
        """정지 해제는 위험해지는 쪽이라 승인 대기만 만든다 (PIN 승인 뒤 run_unsuspend_card)"""
        async with db.begin():
            existing = await approval_repository.find_by_key(db, user_id, idempotency_key)
            if existing is not None:
                if existing.action_type != "UNSUSPEND_CARD" or existing.payload != {"card_id": card_id}:
                    raise ConflictException(
                        message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
                    )
                return existing, False
            found = await card_repository.find_by_id(db, card_id)
            if found is None or found[0].user_id != user_id:
                raise not_found()
            card, product_name = found
            if card.status == "LOST":
                raise ConflictException(message="분실 신고된 카드는 다시 쓸 수 없습니다. 재발급해 주세요.", code="CARD_LOST")
            if card.status != "SUSPENDED":
                raise ConflictException(message="정지된 카드가 아닙니다.", code="CARD_NOT_SUSPENDED")
            action = PendingAction(
                user_id=user_id, action_type="UNSUSPEND_CARD", requested_by="WEB",
                idempotency_key=idempotency_key, expires_at=datetime.now(UTC) + APPROVAL_TTL,
                payload={"card_id": card_id},
                summary=f"{card.nickname or product_name}({mask(card.card_num)}) 정지 풀기",
            )
            try:
                await approval_repository.save(db, action)
            except IntegrityError as e:
                if "idempotency_key" not in str(e.orig):
                    raise
                raise ConflictException(message="같은 요청을 처리하고 있습니다.", code="DUPLICATE_REQUEST") from None
            return action, True


card_service = CardService()
