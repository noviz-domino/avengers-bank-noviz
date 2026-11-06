"""카드 발급·조회·정지·해제 (ADR 0009), 결제·취소·사용내역·한도 (ADR 0010). 체크카드 출금은 실행 함수(ADR 0007)를 거친다"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.categories import classify
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected, execute_card_ledger
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.audit.repository import audit_repository
from avengers_bank.domains.cards.card_number import make_card_num, mask, prefix
from avengers_bank.domains.cards.models import Card, CardProduct, CardTransaction
from avengers_bank.domains.cards.repository import card_repository
from avengers_bank.domains.cards.schemas import (
    CardBillRunResponse,
    CardIssue,
    CardLimitsResponse,
    CardPayment,
    CardResponse,
    CardTransactionResponse,
    PendingRefundResponse,
)

# 기본 한도. 올리는 것은 보안을 약하게 해서 승인 기능과 함께 만든다 (ADR 0009)
DEBIT_DAILY_LIMIT = 1_000_000
CREDIT_DAILY_LIMIT = 1_000_000
CREDIT_LIMIT = 3_000_000  # 안 갚은 사용액 합계의 한도 (ADR 0010)
DEFAULT_PAYMENT_DAY = 14
MAX_SERIAL = 99_999_999
APPROVAL_TTL = timedelta(minutes=10)

logger = logging.getLogger(__name__)


def response(card: Card, product_name: str) -> CardResponse:
    return CardResponse(
        card_id=card.card_id, card_type=card.card_type, product_name=product_name,
        masked_card_num=mask(card.card_num), nickname=card.nickname, linked_account_id=card.linked_account_id,
        daily_limit=card.daily_limit, credit_limit=card.credit_limit, payment_day=card.payment_day,
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


def tx_not_found() -> NotFoundException:
    return NotFoundException(message="카드 사용내역을 찾을 수 없습니다.", code="CARD_TX_NOT_FOUND")


def rejected(e: TransferRejected) -> BadRequestException:
    return BadRequestException(message=e.message, code=e.code)


class CardService:
    async def list_products(self, db: AsyncSession, type_: str | None) -> list[CardProduct]:
        return await card_repository.find_products(db, type_)

    async def issue(self, db: AsyncSession, user_id: int, data: CardIssue) -> CardResponse:
        async with db.begin():
            product = await db.get(CardProduct, data.product_id)
            if product is None or not product.is_active:
                raise NotFoundException(message="판매 중인 카드 상품이 아닙니다.", code="CARD_PRODUCT_NOT_FOUND")
            # 잠근다: 해지(ADR 0012)가 계좌를 잠근 뒤 카드를 보므로, 해지 중인 계좌로 발급되지 않는다
            account = await db.scalar(select(Account).where(Account.account_id == data.linked_account_id)
                                      .with_for_update().execution_options(populate_existing=True))
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
                credit_limit=CREDIT_LIMIT if credit else None,
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
        self, db: AsyncSession, user_id: int, card_id: int, idempotency_key: str, requested_by: str = "WEB"
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
                user_id=user_id, action_type="UNSUSPEND_CARD", requested_by=requested_by,
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

    async def _my_card(self, db: AsyncSession, user_id: int, card_id: int, lock: bool = False) -> Card:
        found = await card_repository.find_by_id(db, card_id, lock=lock)
        if found is None or found[0].user_id != user_id:
            raise not_found()
        return found[0]

    async def pay(self, db: AsyncSession, user_id: int, card_id: int, data: CardPayment) -> tuple[CardTransaction, bool]:
        """가맹점 결제 흉내 (ADR 0010). 카드 행을 잠가서 같은 카드의 결제·취소를 한 줄로 세운다
        (한도 합계와 요청 번호 검사가 동시 결제에 뚫리지 않게)"""
        async with db.begin():
            card = await self._my_card(db, user_id, card_id, lock=True)
            existing = await card_repository.find_tx_by_key(db, card_id, data.idempotency_key)
            if existing is not None:
                if (existing.merchant_name, existing.amount) != (data.merchant_name, data.amount):
                    raise ConflictException(
                        message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
                    )
                return existing, False
            if card.status != "ACTIVE":
                raise ConflictException(message="쓸 수 없는 카드입니다(정지·분실).", code="CARD_NOT_ACTIVE")
            used_today = await card_repository.spent_since(db, card_id, kst_midnight_utc(today_kst()))
            if used_today + data.amount > card.daily_limit:
                left = max(card.daily_limit - used_today, 0)
                raise BadRequestException(
                    message=f"오늘 더 쓸 수 있는 금액은 {left:,}원입니다.", code="CARD_DAILY_LIMIT_EXCEEDED"
                )
            category = classify("CARD_PAYMENT", None, data.merchant_name)
            tx = CardTransaction(
                card_id=card_id, idempotency_key=data.idempotency_key, merchant_name=data.merchant_name,
                category=category, amount=data.amount, status="APPROVED",
            )
            if card.card_type == "CREDIT":
                if await card_repository.has_overdue(db, card_id):
                    raise ConflictException(message="밀린 카드 대금이 있어 결제할 수 없습니다.", code="CARD_OVERDUE")
                unpaid = await card_repository.unpaid_credit(db, card_id)
                if unpaid + data.amount > card.credit_limit:
                    left = max(card.credit_limit - unpaid, 0)
                    raise BadRequestException(message=f"남은 신용 한도는 {left:,}원입니다.", code="CREDIT_LIMIT_EXCEEDED")
                tx.billing_status = "UNBILLED"  # 돈은 대금 출금일에 나간다 (대금 출금 PR)
            else:
                try:
                    ledger = await execute_card_ledger(
                        db, owner_user_id=user_id, account_id=card.linked_account_id, tx_type="CARD_PAYMENT",
                        amount=-data.amount, merchant_name=data.merchant_name, category=category,
                    )
                except TransferRejected as e:
                    raise rejected(e) from None
                tx.account_tx_id = ledger.tx_id
            db.add(tx)
            await db.flush()
            await db.refresh(tx)
            return tx, True

    async def cancel(self, db: AsyncSession, user_id: int, card_id: int, card_tx_id: int) -> CardTransaction:
        """전액 취소. 이미 돈이 나간 것(체크카드, 대금을 낸 신용카드)은 결제 계좌로 환불(REFUND),
        아직 안 나간 것(UNBILLED·BILLED 신용카드)은 기록만 취소. 정지·분실 카드도 취소는 된다"""
        async with db.begin():
            card = await self._my_card(db, user_id, card_id, lock=True)
            tx = await db.get(CardTransaction, card_tx_id, populate_existing=True)
            if tx is None or tx.card_id != card_id:
                raise tx_not_found()
            if tx.status == "CANCELED":
                raise ConflictException(message="이미 취소된 결제입니다.", code="CARD_TX_ALREADY_CANCELED")
            linked = await db.get(Account, card.linked_account_id, populate_existing=True)
            # 돈이 나간 결제는 결제 계좌로 환불. 계좌가 해지됐으면 환불 대기로 두고 상담원이 다른 계좌로 (ADR 0012)
            if (tx.account_tx_id is not None or tx.billing_status == "PAID") and linked.status == "ACTIVE":
                try:
                    refund = await execute_card_ledger(  # 쓴 업종 그대로: 예산에서 그 업종 지출이 줄어든다
                        db, owner_user_id=user_id, account_id=card.linked_account_id, tx_type="REFUND",
                        amount=tx.amount, merchant_name=tx.merchant_name, category=tx.category,
                    )
                except TransferRejected as e:
                    raise rejected(e) from None
                tx.refund_tx_id = refund.tx_id
            tx.status, tx.canceled_at = "CANCELED", datetime.now(UTC)
            await db.flush()
            await db.refresh(tx)
            return tx

    async def list_pending_refunds(self, db: AsyncSession) -> list[PendingRefundResponse]:
        return [
            PendingRefundResponse(**CardTransactionResponse.model_validate(tx).model_dump(),
                                  user_id=card.user_id, linked_account_id=card.linked_account_id)
            for tx, card in await card_repository.find_pending_refunds(db)
        ]

    async def refund_to(self, db: AsyncSession, card_tx_id: int, to_account_id: int) -> CardTransaction:
        """상담원 처리: 환불 대기 건을 카드 주인의 다른 입출금 계좌로 (ADR 0012). 잠금 순서 카드 → 계좌"""
        async with db.begin():
            tx = await db.get(CardTransaction, card_tx_id)
            if tx is None:
                raise tx_not_found()
            card = (await card_repository.find_by_id(db, tx.card_id, lock=True))[0]
            await db.refresh(tx)  # 카드를 잠근 뒤의 최신 상태로 (같은 건을 두 번 환불하지 않게)
            if not tx.refund_pending:
                raise ConflictException(message="환불 대기 중인 건이 아닙니다.", code="REFUND_NOT_PENDING")
            target = await db.get(Account, to_account_id)
            if target is None or target.account_type != "CHECKING":
                raise BadRequestException(message="카드 주인의 입출금 계좌가 아닙니다.", code="ACCOUNT_NOT_FOUND")
            try:  # 주인·ACTIVE는 실행 함수가 잠근 뒤 다시 본다
                refund = await execute_card_ledger(
                    db, owner_user_id=card.user_id, account_id=to_account_id, tx_type="REFUND",
                    amount=tx.amount, merchant_name=tx.merchant_name, category=tx.category,
                )
            except TransferRejected as e:
                raise rejected(e) from None
            tx.refund_tx_id = refund.tx_id
            await audit_repository.record(  # 누가 어느 계좌로 보냈는지 (상담원 역할이 생기면 actor를 그 직원으로)
                db, user_id=card.user_id, actor="SYSTEM", action="CARD_REFUND_TO", target=str(card_tx_id),
                detail={"to_account_id": to_account_id, "amount": tx.amount, "refund_tx_id": refund.tx_id},
            )
            await db.flush()
            await db.refresh(tx)
            return tx

    async def list_txs(self, db: AsyncSession, user_id: int, card_id: int) -> list[CardTransaction]:
        await self._my_card(db, user_id, card_id)
        return await card_repository.find_txs(db, card_id)

    async def limits(self, db: AsyncSession, user_id: int, card_id: int) -> CardLimitsResponse:
        card = await self._my_card(db, user_id, card_id)
        return CardLimitsResponse(
            daily_limit=card.daily_limit,
            daily_used=await card_repository.spent_since(db, card_id, kst_midnight_utc(today_kst())),
            credit_limit=card.credit_limit,
            credit_used=await card_repository.unpaid_credit(db, card_id) if card.card_type == "CREDIT" else None,
        )

    async def run_bills(self, db: AsyncSession, run_date: date) -> CardBillRunResponse:
        """신용카드 대금 출금 (ADR 0011). 카드마다 트랜잭션 하나: 한 카드가 실패해도 다른 카드는 진행된다"""
        result = CardBillRunResponse(run_date=run_date, paid_cards=0, overdue_cards=0, failed_cards=0, total_paid=0)
        async with db.begin():  # 목록만 읽고 닫는다: 카드마다 새 트랜잭션을 연다
            card_ids = await card_repository.cards_to_bill(db, run_date.day)
        for card_id in card_ids:
            try:
                paid = await self._bill_card(db, card_id, run_date)
            except Exception:  # 그 카드만 되돌리고 다음 카드로. 다시 부르면 다시 시도된다
                logger.exception("card bill failed: card_id=%s run_date=%s", card_id, run_date)
                result.failed_cards += 1
                continue
            if paid is None:
                result.overdue_cards += 1
            elif paid:
                result.paid_cards, result.total_paid = result.paid_cards + 1, result.total_paid + paid
        return result

    async def _bill_card(self, db: AsyncSession, card_id: int, run_date: date) -> int | None:
        """결제일이면 전날까지 쓴 UNBILLED를 BILLED로 묶고, BILLED 합계를 전액 출금해 PAID로.
        낸 금액(없으면 0)을 돌려준다. 못 내면 None: BILLED(연체)로 커밋되고 다음 실행 때 다시 시도"""
        async with db.begin():
            card, product_name = await card_repository.find_by_id(db, card_id, lock=True)
            if card.payment_day == run_date.day:
                await card_repository.bill(db, card_id, kst_midnight_utc(run_date))
            billed = await card_repository.find_billed(db, card_id)
            amount = sum(t.amount for t in billed)
            if amount == 0:
                return 0
            try:
                ledger = await execute_card_ledger(
                    db, owner_user_id=card.user_id, account_id=card.linked_account_id, tx_type="CARD_BILL",
                    amount=-amount, merchant_name=f"{product_name} 대금", category=classify("CARD_BILL", None),
                )
            except TransferRejected as e:  # 잔액 부족, 결제 계좌를 쓸 수 없음
                logger.info("card bill overdue: card_id=%s reason=%s", card_id, e.code)
                return None
            for t in billed:
                t.billing_status, t.bill_tx_id = "PAID", ledger.tx_id
            return amount

card_service = CardService()
