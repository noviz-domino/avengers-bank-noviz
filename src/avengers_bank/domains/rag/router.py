import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.database import get_db
from avengers_bank.core.dependencies import get_current_user, require_system_key
from avengers_bank.core.exceptions import ApiException
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.rag.ai import AI, get_ai
from avengers_bank.domains.rag.schemas import AskRequest, AskResponse, ReindexResponse, SearchHit
from avengers_bank.domains.rag.service import rag_service
from avengers_bank.domains.users.schemas import UserResponse

# 로그인한 사용자만: 상품·약관은 공개 정보지만 호출마다 Gemini 무료 한도를 쓴다
router = APIRouter(prefix="/rag", tags=["rag"], responses=error_responses(401, 422, 429, 503))
system_router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_system_key)],
                          responses=error_responses(403, 422, 503))

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[UserResponse, Depends(get_current_user)]
AIDep = Annotated[AI, Depends(get_ai)]

LIMIT, WINDOW = 10, 60.0  # 사용자당 1분에 10번: 한 사람이 무료 한도를 다 써서 모두의 RAG가 멈추지 않게
calls: dict[int, deque[float]] = defaultdict(deque)


def spend_ai_calls(user_id: int, cost: int) -> None:
    """shortcut: 서버 메모리에 기록한다(서버 한 대 기준). 여러 대가 되면 Redis 같은 공용 저장소로"""
    now, recent = time.monotonic(), calls[user_id]
    while recent and now - recent[0] > WINDOW:
        recent.popleft()
    if len(recent) + cost > LIMIT:
        raise ApiException(status_code=429, code="AI_RATE_LIMITED", message="잠시 후 다시 물어봐 주세요(1분에 10번까지).")
    recent.extend([now] * cost)


def limit_ai_calls(me: Me) -> None:
    spend_ai_calls(me.user_id, 1)


Limited = Annotated[None, Depends(limit_ai_calls)]


@router.get("/search", response_model=SuccessResponse[list[SearchHit]])
async def search(db: DB, me: Me, _: Limited, ai: AIDep, q: Annotated[str, Query(min_length=1, max_length=500)],
                 k: Annotated[int, Query(ge=1, le=10)] = 5):
    """상품·약관 검색 (벡터 + 단어 하이브리드, RRF). 답변 없이 근거만"""
    return SuccessResponse[list[SearchHit]](data=await rag_service.search(db, ai, q, k))


@router.post("/ask", response_model=SuccessResponse[AskResponse])
async def ask(data: AskRequest, db: DB, me: Me, _: Limited, ai: AIDep):
    """근거와 함께 답한다. 근거가 없으면 abstain, 모호하면 clarify. 인용은 검색된 청크 안에서만"""
    return SuccessResponse[AskResponse](data=await rag_service.ask(db, ai, data.question))


@system_router.post("/rag/reindex", response_model=SuccessResponse[ReindexResponse])
async def reindex(db: DB, ai: AIDep):
    """약관 문서와 판매 중인 상품을 다시 색인. 바뀐 청크만 임베딩한다. 상품을 바꾸면 다시 부른다"""
    return SuccessResponse[ReindexResponse](data=await rag_service.reindex(db, ai), message="RAG 색인을 갱신했습니다.")
