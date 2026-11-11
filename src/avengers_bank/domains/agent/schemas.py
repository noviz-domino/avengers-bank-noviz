from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    session_id: UUID | None = None  # 없으면 새 대화. 같은 값을 보내면 앞 대화를 기억한다


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    routed: list[str]  # 이번 턴에 일한 담당 (account·card·product·budget), 평가·디버깅용


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
