from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.exceptions import BadRequestException
from avengers_bank.core.clock import today_kst
from avengers_bank.core.dependencies import RequestedBy, get_current_user, require_system_key
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.approvals.schemas import ActionResponse
from avengers_bank.domains.cards.schemas import (
    CardBillRunResponse,
    CardIssue,
    CardLimitsResponse,
    CardPayment,
    CardProductResponse,
    CardRefundTo,
    CardResponse,
    CardSuspend,
    CardTransactionResponse,
    PendingRefundResponse,
)
from avengers_bank.domains.cards.service import card_service
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/cards", tags=["cards"], responses=error_responses(401, 422))
products_router = APIRouter(prefix="/products", tags=["products"], responses=error_responses(422))
# 사용자 토큰이 아니라 서버 키(X-System-Key)로만 부르는 시스템 작업 (ADR 0011)
system_router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_system_key)],
                          responses=error_responses(403, 422))

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]


class UnsuspendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=100)


@products_router.get("/cards", response_model=SuccessResponse[list[CardProductResponse]])
async def list_card_products(db: DB, type: Literal["CREDIT", "DEBIT"] | None = None):
    return SuccessResponse[list[CardProductResponse]](data=await card_service.list_products(db, type))


@router.get("", response_model=SuccessResponse[list[CardResponse]])
async def list_my_cards(db: DB, me: Me):
    return SuccessResponse[list[CardResponse]](data=await card_service.list_mine(db, me.user_id))


@router.post("", response_model=SuccessResponse[CardResponse], status_code=status.HTTP_201_CREATED,
             responses=error_responses(400, 404, 409))
async def issue_card(data: CardIssue, db: DB, me: Me):
    return SuccessResponse[CardResponse](data=await card_service.issue(db, me.user_id, data), message="카드가 발급되었습니다.")


@router.get("/{card_id}", response_model=SuccessResponse[CardResponse], responses=error_responses(404))
async def get_my_card(card_id: int, db: DB, me: Me):
    return SuccessResponse[CardResponse](data=await card_service.get_mine(db, me.user_id, card_id))


@router.post("/{card_id}/suspend", response_model=SuccessResponse[CardResponse], responses=error_responses(404, 409))
async def suspend_card(card_id: int, data: CardSuspend, db: DB, me: Me):
    """정지·분실 신고: 바로 적용 (안전해지는 쪽은 승인 없이, ADR 0004)"""
    return SuccessResponse[CardResponse](data=await card_service.suspend(db, me.user_id, card_id, data.reason))


@router.post("/{card_id}/unsuspend", response_model=SuccessResponse[ActionResponse],
             status_code=status.HTTP_202_ACCEPTED, responses=error_responses(404, 409))
async def request_unsuspend(card_id: int, data: UnsuspendRequest, response: Response, db: DB, me: Me,
                            requested_by: RequestedBy):
    """정지 해제: 승인 대기만 만든다. `POST /approvals/{action_id}/approve`(PIN)로 풀린다"""
    action, created = await card_service.request_unsuspend(db, me.user_id, card_id, data.idempotency_key, requested_by)
    if not created:
        response.status_code = status.HTTP_200_OK
    return SuccessResponse[ActionResponse](data=action, message="승인 화면에서 PIN을 입력하면 정지가 풀립니다.")


@router.post("/{card_id}/payments", response_model=SuccessResponse[CardTransactionResponse],
             status_code=status.HTTP_201_CREATED, responses=error_responses(400, 404, 409))
async def pay(card_id: int, data: CardPayment, response: Response, db: DB, me: Me):
    """가맹점 결제 흉내 (ADR 0010): PIN 없이 바로. 체크는 결제 계좌에서 출금, 신용은 사용 기록.
    Agent·MCP 도구에는 넣지 않는다. 같은 요청 번호로 다시 오면 처음 결과를 200으로 돌려준다"""
    tx, created = await card_service.pay(db, me.user_id, card_id, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    message = "결제되었습니다." if created else "이미 처리된 결제 요청입니다."  # 재전송: 상태는 data.status로
    return SuccessResponse[CardTransactionResponse](data=tx, message=message)


@router.get("/{card_id}/transactions", response_model=SuccessResponse[list[CardTransactionResponse]],
            responses=error_responses(404))
async def list_card_transactions(card_id: int, db: DB, me: Me):
    return SuccessResponse[list[CardTransactionResponse]](data=await card_service.list_txs(db, me.user_id, card_id))


@router.post("/{card_id}/transactions/{card_tx_id}/cancel", response_model=SuccessResponse[CardTransactionResponse],
             responses=error_responses(400, 404, 409))
async def cancel_card_transaction(card_id: int, card_tx_id: int, db: DB, me: Me):
    """전액 취소: 체크는 결제 계좌로 환불, 신용은 사용 기록만 취소"""
    tx = await card_service.cancel(db, me.user_id, card_id, card_tx_id)
    pending = "결제는 취소됐고, 결제 계좌를 쓸 수 없어 상담원이 확인한 뒤 환불합니다."
    return SuccessResponse[CardTransactionResponse](data=tx, message=pending if tx.refund_pending else "결제가 취소되었습니다.")


@router.get("/{card_id}/limits", response_model=SuccessResponse[CardLimitsResponse], responses=error_responses(404))
async def card_limits(card_id: int, db: DB, me: Me):
    return SuccessResponse[CardLimitsResponse](data=await card_service.limits(db, me.user_id, card_id))


@system_router.post("/card-bills/run", response_model=SuccessResponse[CardBillRunResponse])
async def run_card_bills(db: DB, run_date: date | None = None):
    """신용카드 대금 출금. 매일 한 번 부른다(cron 등). 날짜를 비우면 오늘(한국). 같은 날짜로 다시 불러도 한 번만 출금"""
    today = today_kst()
    if run_date is not None and run_date > today:  # 아직 오지 않은 결제일을 앞당겨 청구하지 않게
        raise BadRequestException(message="오늘 이후 날짜로는 실행할 수 없습니다.", code="RUN_DATE_IN_FUTURE")
    result = await card_service.run_bills(db, run_date or today)
    return SuccessResponse[CardBillRunResponse](data=result, message="카드 대금 출금을 실행했습니다.")


@system_router.get("/card-refunds", response_model=SuccessResponse[list[PendingRefundResponse]])
async def list_pending_refunds(db: DB):
    """상담원용: 결제 계좌를 쓸 수 없어 못 돌려준 카드 결제 취소 (ADR 0012). 카드 주인·원래 결제 계좌 포함"""
    return SuccessResponse[list[PendingRefundResponse]](data=await card_service.list_pending_refunds(db))


@system_router.post("/card-refunds/{card_tx_id}", response_model=SuccessResponse[CardTransactionResponse],
                    responses=error_responses(400, 404, 409))
async def refund_to_account(card_tx_id: int, data: CardRefundTo, db: DB):
    """상담원용: 고객 요청을 확인하고, 카드 주인의 다른 입출금 계좌로 환불"""
    tx = await card_service.refund_to(db, card_tx_id, data.to_account_id)
    return SuccessResponse[CardTransactionResponse](data=tx, message="환불했습니다.")
