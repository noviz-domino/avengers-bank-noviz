from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.accounts.schemas import (
    AccountCreate,
    AccountDetailResponse,
    AccountListResponse,
    AccountUpdate,
    DepositCreate,
    TransactionFilter,
    TransactionResponse,
    TransactionSearchResponse,
    TransactionUpdate,
)
from avengers_bank.domains.accounts.service import account_service
from avengers_bank.domains.approvals.schemas import ActionResponse
from avengers_bank.domains.users.schemas import UserResponse

# 계좌가 한 테이블이라 종류별 경로를 두지 않는다 (ADR 0003)
router = APIRouter(prefix="/accounts", tags=["accounts"], responses=error_responses(401, 422))

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]


@router.get("", response_model=SuccessResponse[AccountListResponse])
async def list_my_accounts(db: DB, me: Me):
    return SuccessResponse[AccountListResponse](data=await account_service.list_my_accounts(db, me.user_id))


@router.post(
    "", response_model=SuccessResponse[AccountDetailResponse],
    status_code=status.HTTP_201_CREATED, responses=error_responses(400, 404, 409),
)
async def open_account(data: AccountCreate, db: DB, me: Me):
    account = await account_service.open_account(db, me, data)
    return SuccessResponse[AccountDetailResponse](data=account, message="계좌가 개설되었습니다.")


@router.post(
    "/deposits", response_model=SuccessResponse[ActionResponse],
    status_code=status.HTTP_202_ACCEPTED, responses=error_responses(400, 404, 409),
)
async def request_deposit(data: DepositCreate, response: Response, db: DB, me: Me):
    """예금 개설 신청 → 승인 대기. `POST /approvals/{action_id}/approve`(PIN)로 계좌가 열리고 돈이 옮겨진다."""
    action, created = await account_service.request_deposit(db, me, data)
    if not created:
        response.status_code = status.HTTP_200_OK
    return SuccessResponse[ActionResponse](data=action, message="승인 화면에서 PIN을 입력하면 예금이 열립니다.")


@router.get("/{account_id}", response_model=SuccessResponse[AccountDetailResponse], responses=error_responses(404))
async def get_my_account(account_id: int, db: DB, me: Me):
    return SuccessResponse[AccountDetailResponse](data=await account_service.get_my_account(db, me.user_id, account_id))


@router.get(
    "/{account_id}/transactions",
    response_model=SuccessResponse[list[TransactionResponse]], responses=error_responses(404),
)
async def list_transactions(
    account_id: int, db: DB, me: Me,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[int | None, Query(description="이전 쪽의 마지막 tx_id")] = None,
):
    txs = await account_service.list_transactions(db, me.user_id, account_id, limit, before)
    return SuccessResponse[list[TransactionResponse]](data=txs)


@router.patch("/{account_id}", response_model=SuccessResponse[AccountDetailResponse], responses=error_responses(404))
async def rename_account(account_id: int, data: AccountUpdate, db: DB, me: Me):
    account = await account_service.rename(db, me.user_id, account_id, data.nickname)
    return SuccessResponse[AccountDetailResponse](data=account)


# 계좌를 가로지르는 거래 검색 (Agent의 search_transactions 도구도 이걸 쓴다: ADR 0006)
tx_router = APIRouter(prefix="/transactions", tags=["transactions"], responses=error_responses(401, 422))


@tx_router.get("", response_model=SuccessResponse[TransactionSearchResponse], responses=error_responses(404))
async def search_transactions(f: Annotated[TransactionFilter, Query()], db: DB, me: Me):
    """기간(한국 날짜)·금액·키워드(메모·상대방)·방향·카테고리로 검색. 합계는 조건 전체"""
    return SuccessResponse[TransactionSearchResponse](data=await account_service.search_transactions(db, me.user_id, f))


@tx_router.patch("/{tx_id}", response_model=SuccessResponse[TransactionResponse], responses=error_responses(404))
async def update_transaction(tx_id: int, data: TransactionUpdate, db: DB, me: Me):
    """카테고리·메모 고치기 (금액·상대방은 못 고침)"""
    return SuccessResponse[TransactionResponse](data=await account_service.update_transaction(db, me.user_id, tx_id, data))
