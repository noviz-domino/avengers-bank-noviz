import time
from collections import Counter, defaultdict, deque
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.clock import today_kst
from avengers_bank.core.config import get_settings
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

# 사용자당 1분에 6번: 상담 한 번(또는 검색·답변 한 번)을 1번으로 센다 (2026-11-12, ADR 0026).
# 사용자가 세는 단위(대화 횟수)와 같게 해야 "1분에 6번" 안내가 맞는다. 비용 상한은 아래 하루 한도가 AI 호출 수로 따로 막는다
LIMIT, WINDOW = 6, 60.0
calls: dict[int, deque[float]] = defaultdict(deque)
daily_calls: Counter[date] = Counter()  # 서버 전체 하루 사용량. 재시작하면 0부터 (한 대·평일 낮 운영 기준)


def spend_ai_calls(user_id: int, cost: int) -> None:
    """요청 한 번을 기록한다. 1분 한도는 요청(대화) 수로, 하루 한도는 AI 호출 수(cost, 상담 = 3)로 센다.
    shortcut: 서버 메모리에 기록한다(서버 한 대 기준). 여러 대가 되면 Redis 같은 공용 저장소로"""
    now, recent = time.monotonic(), calls[user_id]
    while recent and now - recent[0] > WINDOW:
        recent.popleft()
    if len(recent) + 1 > LIMIT:
        raise ApiException(status_code=429, code="AI_RATE_LIMITED", message=f"잠시 후 다시 물어봐 주세요(1분에 {LIMIT}번까지).")
    today = today_kst()
    if today not in daily_calls:
        daily_calls.clear()  # 날짜가 바뀌면 새로 센다
    if daily_calls[today] + cost > get_settings().ai_daily_limit:
        raise ApiException(status_code=429, code="AI_DAILY_LIMIT",
                           message="오늘 준비한 AI 사용량을 모두 썼습니다. 내일 다시 이용해 주세요.")
    recent.append(now)
    daily_calls[today] += cost


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
