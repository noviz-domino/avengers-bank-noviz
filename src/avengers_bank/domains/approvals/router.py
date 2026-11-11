"""승인 API. 사람이 화면에서만 쓴다: Agent·MCP 도구에는 넣지 않는다 (ADR 0004)"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.approvals.schemas import ActionResponse, ApproveRequest
from avengers_bank.domains.approvals.service import approval_service
from avengers_bank.domains.users.router import client_ip
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/approvals", tags=["approvals"], responses=error_responses(401, 404, 422))

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]


@router.get("", response_model=SuccessResponse[list[ActionResponse]])
async def list_pending(db: DB, me: Me):
    """승인을 기다리는 내 요청 (만료 전)"""
    return SuccessResponse[list[ActionResponse]](data=await approval_service.list_pending(db, me.user_id))


@router.get("/{action_id}", response_model=SuccessResponse[ActionResponse])
async def get_action(action_id: uuid.UUID, db: DB, me: Me):
    return SuccessResponse[ActionResponse](data=await approval_service.get(db, me.user_id, action_id))


@router.post(
    "/{action_id}/approve", response_model=SuccessResponse[ActionResponse],
    responses=error_responses(400, 409, 423),
)
async def approve(action_id: uuid.UUID, data: ApproveRequest, request: Request, db: DB, me: Me):
    action = await approval_service.approve(
        db, me.user_id, action_id, data.pin, ip=client_ip(request), reason=data.reason, emergency=data.emergency
    )
    return SuccessResponse[ActionResponse](data=action, message="처리되었습니다.")


@router.post("/{action_id}/reject", response_model=SuccessResponse[ActionResponse], responses=error_responses(409))
async def reject(action_id: uuid.UUID, db: DB, me: Me):
    return SuccessResponse[ActionResponse](data=await approval_service.reject(db, me.user_id, action_id))
