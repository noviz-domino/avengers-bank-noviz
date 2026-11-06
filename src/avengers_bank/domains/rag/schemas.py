from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchHit(BaseModel):
    chunk_id: str
    title: str
    content: str
    score: float  # RRF 점수 (클수록 앞)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)


class AskOutput(BaseModel):
    """LLM이 내는 JSON. citations는 받은 근거의 chunk_id만 허용하고 나머지는 서버가 버린다"""

    action: Literal["answer", "clarify", "abstain"]  # 답함 / 되물음 / 자료 없음
    answer: str
    citations: list[str]


class Citation(BaseModel):
    chunk_id: str
    title: str


class AskResponse(BaseModel):
    action: Literal["answer", "clarify", "abstain"]
    answer: str
    citations: list[Citation]


class ReindexResponse(BaseModel):
    total: int  # 지금 색인에 있는 청크 수
    embedded: int  # 새로 임베딩한 청크 수 (바뀐 것만)
    deleted: int
    embedding_model: str
