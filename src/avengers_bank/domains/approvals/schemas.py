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

    model_config = ConfigDict(from_attributes=True)


class ApproveRequest(BaseModel):
    """승인은 PIN만 받는다. 실행할 내용(payload)은 받지 않는다 (바꿔치기 방지, ERD 승인·실행 규칙 1)"""

    pin: str = Field(pattern=r"^\d{6}$", repr=False)
