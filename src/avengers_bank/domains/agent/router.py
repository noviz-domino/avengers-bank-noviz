import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from langchain_core.language_models import BaseChatModel

from avengers_bank.core.dependencies import bearer_scheme, get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.agent.benefits import ask_benefits
from avengers_bank.domains.agent.llm import get_llm
from avengers_bank.domains.agent.schemas import BenefitsChatRequest, BenefitsChatResponse, ChatRequest, ChatResponse, ChatTurn
from avengers_bank.domains.agent.service import agent_service
from avengers_bank.domains.rag.router import spend_ai_calls
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/chat", tags=["chat"], responses=error_responses(401, 409, 422, 429, 503))

Me = Annotated[UserResponse, Depends(get_current_user)]
Token = Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]
# 채팅 한 번 = LLM 호출 3번 이상(라우터, 담당의 도구 선택, 담당의 답). 1분 한도에는 대화 1번으로, 하루 한도(비용 상한)에는 3으로 센다
CHAT_COST = 3


def limit_chat(me: Me) -> None:
    spend_ai_calls(me.user_id, CHAT_COST)


@router.post("", response_model=SuccessResponse[ChatResponse])
async def chat(data: ChatRequest, me: Me, token: Token, _: Annotated[None, Depends(limit_chat)],
               llm: Annotated[BaseChatModel, Depends(get_llm)]):
    """AI 상담 한 턴. 이체 등은 승인 대기까지만 만들고, PIN 승인은 사람이 승인 화면에서 한다 (ADR 0004·0015)"""
    session_id = str(data.session_id or uuid.uuid4())
    result = await agent_service.chat(llm, me.user_id, token.credentials, session_id, data.message)
    return SuccessResponse[ChatResponse](data=result)


@router.post("/transfer-check", response_model=SuccessResponse[ChatResponse])
async def check_transfer_request(
    data: ChatRequest, me: Me, token: Token, _: Annotated[None, Depends(limit_chat)],
    llm: Annotated[BaseChatModel, Depends(get_llm)],
):
    """내 거래내역과 받은 송금 요청을 읽기 전용으로 점검한다. 일반 상담과는 별도 대화다."""
    session_id = str(data.session_id or uuid.uuid4())
    result = await agent_service.chat(llm, me.user_id, token.credentials, session_id, data.message, transfer_check=True)
    return SuccessResponse[ChatResponse](data=result)


@router.post("/benefits", response_model=SuccessResponse[BenefitsChatResponse])
async def chat_benefits(
    data: BenefitsChatRequest, me: Me, _: Annotated[None, Depends(limit_chat)],
    llm: Annotated[BaseChatModel, Depends(get_llm)],
):
    """혜택 조합 또는 주변 코스를 읽기 전용으로 계산하고 근거와 함께 설명한다."""
    session_id = str(data.session_id or uuid.uuid4())
    return SuccessResponse[BenefitsChatResponse](data=await ask_benefits(llm, me.user_id, session_id, data))


@router.post("/stream", responses={200: {"content": {"text/event-stream": {}}}})
async def chat_stream(data: ChatRequest, me: Me, token: Token, _: Annotated[None, Depends(limit_chat)],
                      llm: Annotated[BaseChatModel, Depends(get_llm)]):
    """AI 상담 한 턴을 SSE로 (ADR 0018). 이벤트: status(진행 상태), token(답 글자), done(끝), error.
    전체 시간은 /chat과 같고, 사용자가 기다리는 동안 무엇을 하는지 보이고 답이 만들어지는 대로 보인다"""
    session_id = str(data.session_id or uuid.uuid4())
    events = agent_service.open_stream(llm, me.user_id, token.credentials, session_id, data.message)
    return StreamingResponse(events, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{session_id}", response_model=SuccessResponse[list[ChatTurn]])
async def history(session_id: uuid.UUID, me: Me):
    """내 대화 기록 (사람 말과 AI 답). 남의 session_id면 빈 목록"""
    return SuccessResponse[list[ChatTurn]](data=await agent_service.history(me.user_id, str(session_id)))
