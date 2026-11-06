"""채팅 한 턴 (ADR 0015). Agent는 MCP 도구를 그대로 쓴다(ADR 0006): 앱 안의 MCP 서버에 메모리로 연결해서
실제 MCP 프로토콜을 지나고, 도구는 이 사용자의 토큰으로 REST만 부른다. 그래서 Agent는 사용자보다 큰 권한이 없다."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.agent import checkpoint
from avengers_bank.domains.agent.graph import MAX_HOPS, build
from avengers_bank.domains.agent.schemas import ChatResponse, ChatTurn
from avengers_bank.domains.mcp_server import api as mcp_api
from avengers_bank.domains.mcp_server.server import mcp
from avengers_bank.domains.rag.ai import unavailable

logger = logging.getLogger(__name__)


def thread_id(user_id: int, session_id: str) -> str:
    """대화방 id에 사용자를 넣는다: 남의 session_id를 알아도 그 사람의 대화를 읽거나 이어 쓸 수 없다"""
    return f"user:{user_id}:{session_id}"


class AgentService:
    async def chat(self, llm: BaseChatModel, user_id: int, token: str, session_id: str, message: str) -> ChatResponse:
        mcp_api.agent_token.set(token)  # 이 요청(태스크) 안에서만 보이는 값. 아래 MCP 서버 태스크가 물려받는다
        mcp_api.requester.set("AGENT")  # 승인 대기에 "AI 상담이 만든 요청"으로 남는다
        config = {"configurable": {"thread_id": thread_id(user_id, session_id)}, "recursion_limit": 10 + MAX_HOPS * 10}
        try:
            async with create_connected_server_and_client_session(mcp) as session:
                graph = build(llm, await load_mcp_tools(session), checkpoint.saver)
                state = await graph.ainvoke(
                    {"messages": [HumanMessage(message)], "hops": 0, "routed": []}, config
                )
        except ApiException:
            raise
        except Exception:  # LLM(외부 서비스) 실패·형식 오류. 대화 상태는 체크포인터에 남은 데까지
            logger.exception("agent turn failed: thread=%s", config["configurable"]["thread_id"])
            raise unavailable("AI 상담을 지금 쓸 수 없습니다. 잠시 후 다시 시도해 주세요.") from None
        reply = next((m.content for m in reversed(state["messages"]) if isinstance(m, AIMessage) and m.content
                      and not m.tool_calls), "죄송합니다. 답을 만들지 못했습니다.")
        return ChatResponse(session_id=session_id, reply=text(reply), routed=state["routed"])

    async def history(self, user_id: int, session_id: str) -> list[ChatTurn]:
        """사람 말과 AI의 최종 답만 (도구 호출·결과는 빼고)"""
        saved = await checkpoint.saver.aget_tuple({"configurable": {"thread_id": thread_id(user_id, session_id)}})
        if saved is None:
            return []
        messages = saved.checkpoint["channel_values"].get("messages", [])
        return [
            ChatTurn(role="user" if isinstance(m, HumanMessage) else "assistant", content=text(m.content))
            for m in messages
            if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and m.content and not m.tool_calls)
        ]


def text(content) -> str:
    """Gemini는 content를 문자열 대신 조각 목록으로 줄 때가 있다"""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


agent_service = AgentService()
