"""예산 관리 API (budget.md, ADR 0022). 가드를 약하게 하는 변경(해지)은 승인 대기만 만든다 (ADR 0007)"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import RequestedBy, get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.approvals.schemas import ActionResponse
from avengers_bank.domains.budget.schemas import BudgetCheck, BudgetEnroll, BudgetNotEnrolled, BudgetSummary, BudgetUpdate
from avengers_bank.domains.budget.service import budget_service
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/budget", tags=["budget"], responses=error_responses(401, 422))

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]


@router.post("", response_model=SuccessResponse[BudgetSummary], status_code=status.HTTP_201_CREATED,
             responses=error_responses(409))
async def enroll(data: BudgetEnroll, db: DB, me: Me):
    """신청: 월 수입·월급날·필수 생활비(하루)·고정 지출·목표·항상 통과 업종. 바로 반영(가드를 강하게 하는 쪽)"""
    summary = await budget_service.enroll(db, me.user_id, data)
    return SuccessResponse[BudgetSummary](data=summary, message="예산 관리를 시작했습니다.")


@router.get("", response_model=SuccessResponse[BudgetSummary | BudgetNotEnrolled])
async def get_budget(db: DB, me: Me):
    """이번 주기 자유 사용 가능액과 계산 내역. 신청 안 했으면 `{"enrolled": false}`"""
    return SuccessResponse[BudgetSummary | BudgetNotEnrolled](data=await budget_service.summary(db, me.user_id))


@router.get("/check", response_model=SuccessResponse[BudgetCheck], responses=error_responses(404))
async def check(db: DB, me: Me, amount: Annotated[int, Query(gt=0, le=10_000_000_000)], category: str | None = None):
    """"이거 사도 돼?": 결제 검사와 같은 규칙으로 계산만 한다 (아무것도 바꾸지 않음)"""
    return SuccessResponse[BudgetCheck](data=await budget_service.check(db, me.user_id, amount, category))


@router.patch("", response_model=SuccessResponse[BudgetSummary], responses=error_responses(400, 404))
async def update(data: BudgetUpdate, db: DB, me: Me):
    """가드를 강하게 하는 변경만 바로 반영. 약하게 하면 400 BUDGET_WEAKEN_REQUIRES_APPROVAL"""
    summary = await budget_service.update(db, me.user_id, data)
    return SuccessResponse[BudgetSummary](data=summary, message="예산을 바꿨습니다.")


@router.delete("", response_model=SuccessResponse[ActionResponse], status_code=status.HTTP_202_ACCEPTED,
               responses=error_responses(404))
async def disable(response: Response, db: DB, me: Me, requested_by: RequestedBy):
    """해지 요청: 승인 대기(BUDGET_DISABLE)만 만든다. `POST /approvals/{action_id}/approve`(PIN)로 해지"""
    action, created = await budget_service.request_disable(db, me.user_id, requested_by)
    if not created:
        response.status_code = status.HTTP_200_OK  # 기다리는 해지 요청이 이미 있음
    return SuccessResponse[ActionResponse](data=action, message="승인 화면에서 PIN을 입력하면 예산 관리가 해지됩니다.")
