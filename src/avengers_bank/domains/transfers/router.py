from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import RequestedBy, get_current_user
from avengers_bank.core.responses import ErrorResponse, SuccessResponse, error_responses
from avengers_bank.domains.approvals.schemas import ActionResponse
from avengers_bank.domains.transfers import clearing
from avengers_bank.domains.transfers.schemas import TransferCreate
from avengers_bank.domains.transfers.service import transfer_service
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/transfers", tags=["transfers"], responses=error_responses(401, 422))


HUB_ERRORS = {502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.get("/banks", response_model=SuccessResponse[list[dict[str, str]]], responses=HUB_ERRORS)
async def list_banks(me: Annotated[UserResponse, Depends(get_current_user)]):
    return SuccessResponse(data=await clearing.banks())


@router.post(
    "", response_model=SuccessResponse[ActionResponse],
    status_code=status.HTTP_202_ACCEPTED, responses=error_responses(400, 409) | HUB_ERRORS,
)
async def request_transfer(
    data: TransferCreate, response: Response,
    db: Annotated[AsyncSession, Depends(get_db)], me: Annotated[UserResponse, Depends(get_current_user)],
    requested_by: RequestedBy,
):
    """이체 요청: 바로 보내지 않고 승인 대기를 만든다. 승인은 `POST /approvals/{action_id}/approve`(PIN)."""
    action, created = await transfer_service.request_transfer(db, me.user_id, data, requested_by)
    if not created:
        response.status_code = status.HTTP_200_OK  # 같은 요청을 다시 보냄
    return SuccessResponse[ActionResponse](data=action, message="승인 화면에서 PIN을 입력하면 보내집니다.")
