"""카드 발급·조회·정지·해제 (ADR 0009), 결제·취소·사용내역·한도 (ADR 0010). 체크카드 출금은 실행 함수(ADR 0007)를 거친다"""

import logging
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.exceptions import ApiException, BadRequestException, ConflictException, NotFoundException
from avengers_bank.domains.accounts.categories import classify
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected, check_budget_confirmed, execute_card_ledger
from avengers_bank.domains.accounts.repository import kst_midnight_utc
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.approvals.repository import approval_repository
from avengers_bank.domains.audit.repository import audit_repository
from avengers_bank.domains.budget.calc import impact_text
from avengers_bank.domains.budget.models import BudgetDecision
from avengers_bank.domains.budget.service import lock_cycle, preview
from avengers_bank.domains.cards.card_number import make_card_num, mask, prefix
from avengers_bank.domains.cards.models import Card, CardProduct, CardTransaction
from avengers_bank.domains.cards.protection import review_reason
from avengers_bank.domains.cards.repository import card_repository
from avengers_bank.domains.cards.schemas import (
    CardBillRunResponse,
    CardIssue,
    CardLimitsResponse,
    CardTxFilter,
    CardTxSearchResponse,
    CardPayment,
    CardResponse,
    CardTransactionResponse,
    MerchantPayment,
    PendingRefundResponse,
)
from avengers_bank.domains.users.models import User

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


# X-Requested-By(WEB·AGENT·MCP) → 감사 기록의 actor (WEB은 사용자가 직접 누른 것)
REQUESTER_ACTOR = {"WEB": "USER", "AGENT": "AGENT", "MCP": "MCP"}


async def run_unsuspend_card(db: AsyncSession, action: PendingAction) -> None:
    """승인된 정지 해제 (approvals EXECUTORS). 그사이 분실 신고됐으면 풀지 않는다"""
    found = await card_repository.find_by_id(db, action.payload["card_id"], lock=True)
    card = found[0] if found else None
    if card is None or card.user_id != action.user_id:
        raise TransferRejected("CARD_NOT_FOUND", "카드를 찾을 수 없습니다.")
    if card.status != "SUSPENDED":
        raise TransferRejected("CARD_NOT_SUSPENDED", "정지된 카드가 아닙니다.")
    card.status = "ACTIVE"
    await audit_repository.record(  # 푼 사람은 PIN을 넣은 사용자. 요청을 누가 만들었는지는 detail에
        db, user_id=card.user_id, actor="USER", action="CARD_UNSUSPENDED", target=str(card.card_id),
        detail={"action_id": str(action.action_id), "requested_by": action.requested_by},
    )


def budget_confirmation_required(action: PendingAction) -> ApiException:
    """409 + 승인 대기 번호와 예산 숫자. 사용자가 승인 화면에서 사유를 적고 PIN을 넣어야 결제된다 (AI는 확인 못 함)"""
    b = action.budget_check
    return ApiException(
        409, "BUDGET_CONFIRMATION_REQUIRED", "예산을 넘는 결제입니다. 승인 화면에서 사유를 적고 PIN으로 확인해 주세요.",
        data={"action_id": str(action.action_id), "free_to_spend": b["free_before"],
              "after": b["free_before"] - b["amount"], "shortage": b["amount"] - b["free_before"], "impact": b["impact"]},
    )


async def run_card_payment(db: AsyncSession, action: PendingAction, emergency: bool = False) -> None:
    """결제 보호(ADR 0023)로 보류됐다가 사용자가 PIN으로 승인한 결제 (approvals EXECUTORS).
    보류 때 예산을 넘었으면 같은 승인에서 사유를 받았으므로 실행 때는 나빠졌는지만 본다 (ADR 0024)"""
    payment = CardPayment.model_validate(action.payload["payment"])
    await _run_approved_payment(db, action, action.payload["card_id"], payment, emergency)


async def run_budget_card_payment(db: AsyncSession, action: PendingAction, emergency: bool = False) -> None:
    """사람이 확인한 예산 초과 카드 결제 (approvals EXECUTORS). 같은 결제 함수를 지나며 잠금 안에서 다시 검사한다"""
    p = action.payload
    payment = CardPayment(merchant_name=p["merchant_name"], amount=p["amount"], idempotency_key=p["idempotency_key"])
    await _run_approved_payment(db, action, p["card_id"], payment, emergency)


async def _run_approved_payment(
    db: AsyncSession, action: PendingAction, card_id: int, payment: CardPayment, emergency: bool
) -> None:
    try:
        card = await card_service._my_card(db, action.user_id, card_id, lock=True)
        tx = await card_service._execute_payment(db, card, payment, budget_check=action.budget_check, emergency=emergency)
    except ApiException as e:  # 그사이 카드 정지·한도 초과·잔액 부족 → FAILED, 돈은 안 움직임
        raise TransferRejected(e.code, e.message) from None
    action.result = {"card_tx_id": tx.card_tx_id}


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

    async def suspend(self, db: AsyncSession, user_id: int, card_id: int, reason: str, requested_by: str = "WEB") -> CardResponse:
        """정지·분실 신고는 안전해지는 쪽이라 바로 (ADR 0004). 분실은 되돌릴 수 없어서 누가 어느 입구로 했는지 남긴다"""
        async with db.begin():
            found = await card_repository.find_by_id(db, card_id, lock=True)
            if found is None or found[0].user_id != user_id:
                raise not_found()
            card = found[0]
            if card.status == "LOST":
                raise ConflictException(message="분실 신고된 카드입니다. 재발급해 주세요.", code="CARD_LOST")
            await audit_repository.record(
                db, user_id=user_id, actor=REQUESTER_ACTOR.get(requested_by, "USER"), action="CARD_" + reason,
                target=str(card_id), detail={"from": card.status, "requested_by": requested_by},
            )
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

    async def pay(
        self, db: AsyncSession, card_id: int, data: CardPayment, *, user_id: int | None = None
    ) -> tuple[CardTransaction | PendingAction, bool]:
        """같은 카드의 결제와 확인 요청을 카드 행 잠금으로 직렬화한다. 결제 보호(ADR 0023)가 보류하거나
        예산(ADR 0024)을 넘으면 결제 대신 승인 대기를 돌려준다. 내 화면 경로(user_id)에서 예산 확인이 필요하면
        409 BUDGET_CONFIRMATION_REQUIRED (승인 대기는 커밋돼야 해서 트랜잭션이 끝난 뒤에 알린다)"""
        async with db.begin():
            result, created = await self._pay_in_tx(db, card_id, data, user_id)
        if user_id is not None and isinstance(result, PendingAction) and result.action_type == "BUDGET_CARD_PAYMENT":
            raise budget_confirmation_required(result)
        return result, created

    async def _pay_in_tx(
        self, db: AsyncSession, card_id: int, data: CardPayment, user_id: int | None
    ) -> tuple[CardTransaction | PendingAction, bool]:
        found = await card_repository.find_by_id(db, card_id, lock=True)
        if found is None or (user_id is not None and found[0].user_id != user_id):
            raise not_found()
        card, product_name = found
        user = await db.get(User, card.user_id)
        state = user.card_protection or {}
        settings = state.get("settings", {})
        existing = await card_repository.find_tx_by_key(db, card_id, data.idempotency_key)
        if existing is not None:
            if (existing.merchant_name, existing.amount) != (data.merchant_name, data.amount):
                raise ConflictException(
                    message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
                )
            return existing, False
        # 같은 요청 번호로 다시 옴: 기다리는 예산 확인이 있으면 그것을 다시 알려 준다
        if waiting := await approval_repository.find_by_key(db, card.user_id, data.idempotency_key):
            return self._same_budget_request(waiting, card_id, data), False

        payment = data.model_dump(include=set(CardPayment.model_fields))
        request = {"card_id": card_id, "payment": payment}
        key = "card-review-" + sha256(f"{card_id}:{data.idempotency_key}".encode()).hexdigest()
        prior = await approval_repository.find_by_key(db, card.user_id, key)
        now = datetime.now(UTC)
        if user_id is not None and (prior or settings.get("location_check") or settings.get("active_from")):
            raise ConflictException(
                message="보호 중인 결제는 가맹점 결제 경로로 보내야 합니다.", code="MERCHANT_CHANNEL_REQUIRED"
            )
        if prior is not None:
            # 예산 숫자(budget_check)는 그사이 바뀔 수 있어서 결제 내용만 비교한다
            if prior.action_type != "CARD_PAYMENT" or {k: prior.payload.get(k) for k in request} != request:
                raise ConflictException(
                    message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED"
                )
            expires = prior.expires_at
            if prior.status == "PENDING" and (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) > now:
                return prior, False
            raise ConflictException(message="거절·만료되었거나 실패한 결제입니다.", code="CARD_PAYMENT_NOT_APPROVABLE")

        if card.status != "ACTIVE":
            raise ConflictException(message="쓸 수 없는 카드입니다(정지·분실).", code="CARD_NOT_ACTIVE")
        if isinstance(data, MerchantPayment) and (reason := await review_reason(db, card_id, state, data, now)):
            summary = (f"{card.nickname or product_name} 끝자리 {card.card_num[-4:]} · "
                       f"{data.merchant_name} {data.amount:,}원 · {reason}")
            # 예산 미리 계산 (ADR 0024): 넘으면 같은 승인 화면에서 사유도 받는다 (PIN 한 번, 이체와 같은 방식)
            check = await self._budget_preview(db, card.user_id, data)
            if check is not None:
                request["budget_check"] = check
                if check["over"]:
                    summary += "\n" + check["impact"]
            action = PendingAction(
                user_id=card.user_id, action_type="CARD_PAYMENT", requested_by="SYSTEM", idempotency_key=key,
                expires_at=now + APPROVAL_TTL, payload=request, summary=summary,
            )
            return await approval_repository.save(db, action), True
        requested_by = "WEB" if user_id is not None else "SYSTEM"
        return await self._execute_payment(db, card, data, requested_by=requested_by), True

    async def _budget_preview(self, db: AsyncSession, user_id: int, data: CardPayment) -> dict | None:
        """잠그지 않고 보는 예산 미리 계산. 실행 때 잠금 안에서 다시 검사한다 (ADR 0007)"""
        found = await preview(db, user_id)
        if found is None:
            return None
        profile, budget = found
        category = classify("CARD_PAYMENT", None, data.merchant_name)
        over = data.amount > budget.free_to_spend and category not in profile.always_allow
        check = {"free_before": budget.free_to_spend, "amount": data.amount, "over": over}
        if over:
            check["impact"] = impact_text(budget, data.amount, profile.goal_name)
        return check

    async def _execute_payment(
        self, db: AsyncSession, card: Card, data: CardPayment, *,
        budget_check: dict | None = None, emergency: bool = False, requested_by: str = "WEB",
    ) -> CardTransaction | PendingAction:
        """한도·신용·예산을 검사하고 결제한다. budget_check는 승인된 건의 실행(run_card_payment·run_budget_card_payment)일 때
        요청 때 저장한 예산 미리 계산({}이면 그때 예산을 넘지 않았음). None이면 바로 결제라서, 예산을 넘으면
        결제 대신 예산 확인용 승인 대기를 돌려준다"""
        if card.status != "ACTIVE":
            raise ConflictException(message="쓸 수 없는 카드입니다(정지·분실).", code="CARD_NOT_ACTIVE")
        used_today = await card_repository.spent_since(db, card.card_id, kst_midnight_utc(today_kst()))
        if used_today + data.amount > card.daily_limit:
            left = max(card.daily_limit - used_today, 0)
            raise BadRequestException(
                message=f"오늘 더 쓸 수 있는 금액은 {left:,}원입니다.", code="CARD_DAILY_LIMIT_EXCEEDED"
            )
        category = classify("CARD_PAYMENT", None, data.merchant_name)  # 업종은 서버가 가맹점 이름으로 (ADR 0007)
        if card.card_type == "CREDIT":
            if await card_repository.has_overdue(db, card.card_id):
                raise ConflictException(message="밀린 카드 대금이 있어 결제할 수 없습니다.", code="CARD_OVERDUE")
            unpaid = await card_repository.unpaid_credit(db, card.card_id)
            if unpaid + data.amount > card.credit_limit:
                left = max(card.credit_limit - unpaid, 0)
                raise BadRequestException(message=f"남은 신용 한도는 {left:,}원입니다.", code="CREDIT_LIMIT_EXCEEDED")
        # 예산 가드 (ADR 0007·0024): 체크·신용 모두. 잠금 순서 카드 → 예산 주기 → 계좌 (ERD 규칙 5)
        if locked := await lock_cycle(db, card.user_id):
            profile, budget = locked
            over = data.amount > budget.free_to_spend
            if budget_check and budget_check.get("over"):  # 사람이 사유와 함께 확인한 예산 초과 건: 나빠졌는지만 본다
                check_budget_confirmed(budget, data.amount, budget_check, emergency)
            elif over and category in profile.always_allow:
                db.add(BudgetDecision(  # 항상 통과 업종: 결제하고 기록. 자유 사용 가능액에서는 그대로 빠진다
                    user_id=card.user_id, amount=data.amount, free_to_spend_at_confirm=budget.free_to_spend,
                    reason=f"항상 통과 업종({category})",
                ))
            elif over and budget_check is not None:
                # 보호 승인 사이에 예산을 넘게 됨: 승인 안에서 새 확인을 만들 수 없어서 실패로 남긴다 (돈은 안 움직임)
                raise TransferRejected("BUDGET_CHANGED", "승인한 뒤 예산이 바뀌어 결제하지 않았습니다. 다시 결제해 주세요.")
            elif over:
                return await self._request_budget_confirmation(db, card, data, profile, budget, requested_by)
        tx = CardTransaction(
            card_id=card.card_id, idempotency_key=data.idempotency_key, merchant_name=data.merchant_name,
            category=category, amount=data.amount, status="APPROVED",
        )
        if card.card_type == "CREDIT":
            tx.billing_status = "UNBILLED"  # 돈은 대금 출금일에 나간다 (대금 출금 PR)
        else:
            try:
                ledger = await execute_card_ledger(
                    db, owner_user_id=card.user_id, account_id=card.linked_account_id, tx_type="CARD_PAYMENT",
                    amount=-data.amount, merchant_name=data.merchant_name, category=category,
                )
            except TransferRejected as e:
                raise rejected(e) from None
            tx.account_tx_id = ledger.tx_id
        db.add(tx)
        await db.flush()
        await db.refresh(tx)
        return tx

    async def _request_budget_confirmation(
        self, db: AsyncSession, card: Card, data: CardPayment, profile, budget, requested_by: str,
    ) -> PendingAction:
        """예산을 넘는 카드 결제: 결제 대신 승인 대기. 멱등키는 처음 결제 요청의 키 그대로 (budget.md 동시성과 중복)"""
        impact = impact_text(budget, data.amount, profile.goal_name)
        kind = "신용카드" if card.card_type == "CREDIT" else "체크카드"
        action = PendingAction(
            user_id=card.user_id, action_type="BUDGET_CARD_PAYMENT", requested_by=requested_by,
            idempotency_key=data.idempotency_key, expires_at=datetime.now(UTC) + APPROVAL_TTL,
            payload={
                "card_id": card.card_id, "merchant_name": data.merchant_name, "amount": data.amount,
                "idempotency_key": data.idempotency_key,
                "budget_check": {"free_before": budget.free_to_spend, "amount": data.amount, "over": True, "impact": impact},
            },
            summary=f"{card.nickname or kind}({mask(card.card_num)})로 {data.merchant_name}에서 {data.amount:,}원 결제\n{impact}",
        )
        try:
            await approval_repository.save(db, action)
        except IntegrityError as e:
            if "idempotency_key" not in str(e.orig):
                raise
            raise ConflictException(message="같은 요청을 처리하고 있습니다.", code="DUPLICATE_REQUEST") from None
        return action

    def _same_budget_request(self, waiting: PendingAction, card_id: int, data: CardPayment) -> PendingAction:
        """같은 결제 요청 번호로 다시 옴: 기다리는 예산 확인이 있으면 그것을 다시 알려 준다"""
        p = waiting.payload
        if (waiting.action_type != "BUDGET_CARD_PAYMENT"
                or (p.get("card_id"), p.get("merchant_name"), p.get("amount")) != (card_id, data.merchant_name, data.amount)):
            raise ConflictException(message="같은 요청 번호로 다른 내용을 보낼 수 없습니다.", code="IDEMPOTENCY_KEY_REUSED")
        expires = waiting.expires_at if waiting.expires_at.tzinfo else waiting.expires_at.replace(tzinfo=UTC)
        if waiting.status == "PENDING" and expires > datetime.now(UTC):
            return waiting
        raise ConflictException(
            message="이 결제의 예산 확인은 이미 끝났습니다. 새 요청 번호로 다시 결제해 주세요.", code="ACTION_NOT_PENDING"
        )

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

    async def list_txs(
        self, db: AsyncSession, user_id: int, card_id: int, payment_date: date | None = None
    ) -> list[CardTransaction]:
        await self._my_card(db, user_id, card_id)
        since = kst_midnight_utc(payment_date) if payment_date else None
        return await card_repository.find_txs(db, card_id, since, since + timedelta(days=1) if since else None)

    async def search_txs(self, db: AsyncSession, user_id: int, f: CardTxFilter) -> CardTxSearchResponse:
        """카드 탭의 카드 검색. 남의 카드 번호를 넣어도 내 카드 조건(user_id)으로만 찾으므로 결과가 비어 있다"""
        since = kst_midnight_utc(f.from_date) if f.from_date else None
        before = kst_midnight_utc(f.to_date) + timedelta(days=1) if f.to_date else None
        rows, total, count = await card_repository.search_txs(
            db, user_id, card_id=f.card_id, keyword=f.keyword, category=f.category, since=since, before=before)
        return CardTxSearchResponse(transactions=rows, total_amount=total, count=count)

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
