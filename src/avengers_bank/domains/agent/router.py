import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from langchain_core.language_models import BaseChatModel

from avengers_bank.core.dependencies import bearer_scheme, get_current_user
from avengers_bank.core.responses import SuccessResponse, error_responses
from avengers_bank.domains.agent.llm import get_llm
from avengers_bank.domains.agent.schemas import ChatRequest, ChatResponse, ChatTurn
from avengers_bank.domains.agent.service import agent_service
from avengers_bank.domains.rag.router import spend_ai_calls
from avengers_bank.domains.users.schemas import UserResponse

router = APIRouter(prefix="/chat", tags=["chat"], responses=error_responses(401, 409, 422, 429, 503))

Me = Annotated[UserResponse, Depends(get_current_user)]
Token = Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]
CHAT_COST = 3  # 채팅 한 번 = LLM 호출 3번 이상(감독관, 담당, 감독관 FINISH). RAG 검색·답변과 같은 한도(1분 10)를 나눠 쓴다


def limit_chat(me: Me) -> None:
    spend_ai_calls(me.user_id, CHAT_COST)


@router.post("", response_model=SuccessResponse[ChatResponse])
async def chat(data: ChatRequest, me: Me, token: Token, _: Annotated[None, Depends(limit_chat)],
               llm: Annotated[BaseChatModel, Depends(get_llm)]):
    """AI 상담 한 턴. 이체 등은 승인 대기까지만 만들고, PIN 승인은 사람이 승인 화면에서 한다 (ADR 0004·0015)"""
    session_id = str(data.session_id or uuid.uuid4())
    result = await agent_service.chat(llm, me.user_id, token.credentials, session_id, data.message)
    return SuccessResponse[ChatResponse](data=result)


@router.get("/{session_id}", response_model=SuccessResponse[list[ChatTurn]])
async def history(session_id: uuid.UUID, me: Me):
    """내 대화 기록 (사람 말과 AI 답). 남의 session_id면 빈 목록"""
    return SuccessResponse[list[ChatTurn]](data=await agent_service.history(me.user_id, str(session_id)))
