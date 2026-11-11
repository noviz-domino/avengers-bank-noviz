"""채팅 한 턴 (ADR 0015). Agent는 MCP 도구를 그대로 쓴다(ADR 0006): 앱 안의 MCP 서버에 메모리로 연결해서
실제 MCP 프로토콜을 지나고, 도구는 이 사용자의 토큰으로 REST만 부른다. 그래서 Agent는 사용자보다 큰 권한이 없다."""

import asyncio
import logging
from collections.abc import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

from avengers_bank.core.exceptions import ApiException, ConflictException
from avengers_bank.domains.agent import checkpoint, tracing
from avengers_bank.domains.agent.graph import MAX_HOPS, build
from avengers_bank.domains.agent.schemas import ChatResponse, ChatTurn
from avengers_bank.domains.agent.stream import EventTranslator, sse
from avengers_bank.domains.agent.transfer_check import build_transfer_check
from avengers_bank.domains.mcp_server import api as mcp_api
from avengers_bank.domains.mcp_server.server import mcp
from avengers_bank.domains.rag.ai import unavailable

logger = logging.getLogger(__name__)
TURN_TIMEOUT = 90.0  # LLM 여러 번 + 도구. 넘으면 503 (요청을 끝없이 붙잡지 않게)
# shortcut: 서버 한 프로세스 안에서만 막는다. 여러 대가 되면 DB advisory lock으로 바꾼다
busy: set[str] = set()
running: set[asyncio.Task] = set()  # 스트리밍 턴 작업 (참조를 잡아 두지 않으면 도중에 사라질 수 있다)


def thread_id(user_id: int, session_id: str) -> str:
    """대화방 id에 사용자를 넣는다: 남의 session_id를 알아도 그 사람의 대화를 읽거나 이어 쓸 수 없다"""
    return f"user:{user_id}:{session_id}"


def text(content) -> str:
    """Gemini는 content를 문자열 대신 조각 목록으로 줄 때가 있다"""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


def final_reply(messages: list) -> str:
    """이번 턴(마지막 사람 말 뒤)의 담당 답을 차례대로 합친다. 복합 요청("카드 한도랑 잔액")은 두 담당의 답이 다 나간다.
    이번 턴에 답이 없으면 예전 턴의 답을 돌려주지 않는다"""
    answers = []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, AIMessage) and m.content and not m.tool_calls:
            answers.append(text(m.content))
    return "\n\n".join(reversed(answers)) or "죄송합니다. 답을 만들지 못했습니다. 다시 말씀해 주세요."


def take(thread: str) -> None:
    """같은 대화방에 동시에 두 턴이 오면 같은 저장 지점에서 갈라져 한쪽 메시지가 덮어써진다 (PR #21 리뷰)"""
    if thread in busy:
        raise ConflictException(message="이전 메시지를 처리하고 있습니다. 답을 받은 뒤 다시 보내 주세요.", code="CHAT_BUSY")
    busy.add(thread)


def prepare(token: str, thread: str, callbacks: list, metadata: dict) -> dict:
    mcp_api.agent_token.set(token)  # 이 요청(태스크) 안에서만 보이는 값. 아래 MCP 서버 태스크가 물려받는다
    mcp_api.requester.set("AGENT")  # 승인 대기에 "AI 상담이 만든 요청"으로 남는다
    return {"configurable": {"thread_id": thread}, "recursion_limit": 10 + MAX_HOPS * 10,
            "callbacks": callbacks, "metadata": metadata, "run_name": "chat"}


def first_turn(message: str) -> dict:
    return {"messages": [HumanMessage(message)], "plan": [], "routed": []}


async def read(queue: asyncio.Queue) -> AsyncIterator[str]:
    """턴 작업이 쌓은 이벤트를 끝(None)까지 보낸다. 연결이 끊기면 여기서 멈출 뿐 턴은 계속 간다"""
    while (item := await queue.get()) is not None:
        yield item


class AgentService:
    async def chat(self, llm: BaseChatModel, user_id: int, token: str, session_id: str, message: str,
                   callbacks: list | None = None, *, transfer_check: bool = False) -> ChatResponse:
        thread = thread_id(user_id, session_id)
        if transfer_check:
            thread += ":transfer-check"
        take(thread)
        try:
            # 붙여넣은 문자와 조회 거래를 외부 추적 서비스로 보내지 않는다.
            trace_callbacks = [] if transfer_check else tracing.handlers()
            callbacks = [*trace_callbacks, *(callbacks or [])]
            return await self._turn(
                llm, user_id, thread, session_id, token, message, callbacks,
                tracing.metadata(user_id, session_id), transfer_check,
            )
        finally:
            busy.discard(thread)

    async def _turn(self, llm, user_id: int, thread: str, session_id: str, token: str, message: str, callbacks: list,
                    metadata: dict, transfer_check: bool) -> ChatResponse:
        config = prepare(token, thread, callbacks, metadata)
        if transfer_check:
            config.update(recursion_limit=12, run_name="transfer_check")
        try:
            async with asyncio.timeout(TURN_TIMEOUT):
                if transfer_check:
                    graph = build_transfer_check(llm, user_id, checkpoint.saver)
                    state = await graph.ainvoke({"messages": [HumanMessage(message)]}, config)
                else:
                    async with create_connected_server_and_client_session(mcp) as session:
                        graph = build(llm, await load_mcp_tools(session), checkpoint.saver)
                        state = await graph.ainvoke(first_turn(message), config)
        except ApiException:
            raise
        except Exception:  # LLM(외부 서비스) 실패·시간 초과·형식 오류. 원인은 로그로 (버그도 여기로 오니 로그를 본다)
            logger.exception("agent turn failed: thread=%s", thread)
            raise unavailable("AI 상담을 지금 쓸 수 없습니다. 잠시 후 다시 시도해 주세요.") from None
        return ChatResponse(
            session_id=session_id, reply=final_reply(state["messages"]),
            routed=["transfer_check"] if transfer_check else state["routed"],
        )

    def open_stream(self, llm: BaseChatModel, user_id: int, token: str, session_id: str, message: str,
                    callbacks: list | None = None) -> AsyncIterator[str]:
        """스트리밍 한 턴 (ADR 0018). 같은 대화방 잠금은 스트림을 열기 전에 잡아서, 처리 중이면 스트림 대신 409가 나간다.
        턴은 따로 작업으로 끝까지 돌고 스트림은 쌓인 이벤트를 읽기만 한다: 사용자가 연결을 끊어도 턴은 /chat처럼 끝까지 가서
        대화가 저장된다(승인 대기만 만들고 기록이 빠지면 다시 요청해 승인 대기가 두 개 생길 수 있다. PR #25 리뷰)"""
        thread = thread_id(user_id, session_id)
        take(thread)
        callbacks = [*tracing.handlers(), *(callbacks or [])]
        config = prepare(token, thread, callbacks, tracing.metadata(user_id, session_id))
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(llm, thread, session_id, config, message, queue.put_nowait))  # 토큰 등 ContextVar를 물려받는다
        running.add(task)
        task.add_done_callback(running.discard)
        return read(queue)

    async def _run(self, llm, thread: str, session_id: str, config: dict, message: str, put) -> None:
        try:
            put(sse("status", {"stage": "routing", "label": "담당을 고르고 있어요"}))
            translate = EventTranslator()
            async with asyncio.timeout(TURN_TIMEOUT):
                async with create_connected_server_and_client_session(mcp) as session:
                    graph = build(llm, await load_mcp_tools(session), checkpoint.saver)
                    async for ev in graph.astream_events(first_turn(message), config, version="v2"):
                        for out in translate(ev):
                            put(out)
                    state = (await graph.aget_state(config)).values
            put(sse("done", {"session_id": session_id, "reply": final_reply(state["messages"]), "routed": state["routed"]}))
        except Exception:  # 스트림은 이미 200으로 시작해서 오류도 이벤트로 알린다
            logger.exception("agent stream failed: thread=%s", thread)
            put(sse("error", {"code": "AI_UNAVAILABLE", "message": "AI 상담을 지금 쓸 수 없습니다. 잠시 후 다시 시도해 주세요."}))
        finally:  # 끝까지 갔든, 실패했든, 서버가 꺼지며 취소됐든
            busy.discard(thread)
            put(None)

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


agent_service = AgentService()
