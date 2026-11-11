import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActionResponse(BaseModel):
    """승인 화면에 보여 줄 내용. payload는 보여 주지 않고 서버가 만든 summary만 보여 준다"""

    action_id: uuid.UUID
    action_type: str
    summary: str
    status: str
    requested_by: str
    expires_at: datetime
    created_at: datetime
    executed_at: datetime | None
    failure_reason: str | None
    result: dict | None  # 실행 결과. 예금 개설이면 {"account_id": 새 계좌}, 예산 확인 카드 결제면 {"card_tx_id": …}
    needs_budget_reason: bool = False  # 예산을 넘는 건: 승인 때 reason이 필요 (ADR 0024)
    budget_impact: str | None = None  # 승인 화면에 보여 줄 예산 영향 (서버가 만든 문장)

    model_config = ConfigDict(from_attributes=True)


class ApproveRequest(BaseModel):
    """승인은 PIN만 받는다. 실행할 내용(payload)은 받지 않는다 (바꿔치기 방지, ERD 승인·실행 규칙 1).
    예산을 넘는 건만 사람이 적은 사유와 "긴급" 여부를 함께 받는다 (budget_decisions에 기록)"""

    model_config = ConfigDict(str_strip_whitespace=True)  # 공백뿐인 사유는 빈 사유

    pin: str = Field(pattern=r"^\d{6}$", repr=False)
    reason: str | None = Field(default=None, min_length=1, max_length=200)
    emergency: bool = False
