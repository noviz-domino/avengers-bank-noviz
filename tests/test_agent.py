import asyncio
import uuid

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from avengers_bank.domains.agent.graph import HISTORY, MAX_HOPS, Route, recent
from avengers_bank.domains.agent.service import final_reply
from avengers_bank.domains.agent.llm import get_llm
from avengers_bank.domains.rag import router as rag_router
from avengers_bank.main import app
from avengers_bank.seed import seed_products
from tests.test_transfers import balance, open_account, user

pytestmark = pytest.mark.anyio


def like_gemini(messages):
    """실제 Gemini 규칙: 모델 차례(AI 메시지)로 끝나는 요청은 400 (실제 점검에서 이걸로 모든 대화가 실패했다)"""
    if isinstance(messages[-1], AIMessage):
        raise ValueError("Requests ending with a model turn are not supported.")


class FakeChat(BaseChatModel):
    """Gemini 대신: 감독관의 선택(routes)과 담당 Agent의 응답(replies)을 차례로 내놓는다. 도구는 진짜로 불린다"""

    routes: list = Field(default_factory=list)
    replies: list = Field(default_factory=list)
    agent_inputs: list = Field(default_factory=list)  # 담당 Agent가 받은 메시지들
    supervisor_inputs: list = Field(default_factory=list)
    fail: bool = False
    delay: float = 0.0  # 감독관이 생각하는 시간 (동시 요청 테스트)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        like_gemini(messages)
        self.agent_inputs.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        def route(messages):
            like_gemini(messages)
            if self.fail:
                raise RuntimeError("Gemini 장애")
            self.supervisor_inputs.append(messages)
            return self.routes.pop(0)

        async def aroute(messages):
            await asyncio.sleep(self.delay)
            return route(messages)
        return RunnableLambda(route, afunc=aroute)


def call(name, **args):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call-{uuid.uuid4().hex[:6]}"}])


@pytest.fixture
async def bank(client):
    from avengers_bank.core.database import SessionLocal

    async with SessionLocal() as db:
        await seed_products(db)
    tony = await user(client, "ironman", "토니")
    peter = await user(client, "spidey", "피터")
    src = await open_account(client, tony, balance=1_000_000)
    dst = await open_account(client, peter)
    fake = FakeChat()
    app.dependency_overrides[get_llm] = lambda: fake
    rag_router.calls.clear()
    yield client, tony, peter, src, dst, fake
    app.dependency_overrides.pop(get_llm, None)


def chat(client, me, message, session_id=None):
    body = {"message": message} | ({"session_id": session_id} if session_id else {})
    return client.post("/chat", json=body, headers=me)


async def test_account_question_goes_through_mcp_tools(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="account"), Route(next="FINISH")]
    fake.replies = [call("get_my_accounts"), AIMessage("총자산은 1,000,000원입니다.")]
    data = (await chat(client, tony, "내 계좌 얼마 있어?")).json()["data"]
    assert data["reply"] == "총자산은 1,000,000원입니다." and data["routed"] == ["account"]
    tool_result = [m for m in fake.agent_inputs[1] if isinstance(m, ToolMessage)][0]
    assert "1000000" in str(tool_result.content)  # 도구가 MCP → REST를 지나 토니의 실제 잔액을 받았다


async def test_transfer_only_creates_pending_marked_agent(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="account"), Route(next="FINISH")]
    fake.replies = [call("request_transfer", from_account_id=src["account_id"], to_account_num=dst["account_num"],
                         amount=50_000), AIMessage("승인 화면에서 PIN을 입력해 주세요.")]
    await chat(client, tony, "피터한테 5만 원 보내줘")
    pending = (await client.get("/approvals", headers=tony)).json()["data"]
    assert [(p["action_type"], p["requested_by"]) for p in pending] == [("TRANSFER", "AGENT")]
    assert await balance(src["account_id"]) == 1_000_000  # PIN 없이는 돈이 안 움직임


async def test_context_is_kept_and_private(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="FINISH", reply="안녕하세요! 무엇을 도와드릴까요?"), Route(next="FINISH", reply="네")]
    first = (await chat(client, tony, "안녕")).json()["data"]
    assert first["reply"] == "안녕하세요! 무엇을 도와드릴까요?" and first["routed"] == []
    await chat(client, tony, "고마워", first["session_id"])
    humans = [m.content for m in fake.supervisor_inputs[1] if isinstance(m, HumanMessage) and not m.content.startswith("(상담 안내)")]
    assert humans == ["안녕", "고마워"]  # 같은 대화방이면 앞 대화를 기억한다

    history = (await client.get(f"/chat/{first['session_id']}", headers=tony)).json()["data"]
    assert [t["role"] for t in history] == ["user", "assistant", "user", "assistant"]
    assert (await client.get(f"/chat/{first['session_id']}", headers=peter)).json()["data"] == []  # 남의 대화방

    fake.routes = [Route(next="FINISH", reply="처음 뵙겠습니다")]
    await chat(client, peter, "안녕?", first["session_id"])  # 토니의 session_id를 써도 피터의 새 대화
    assert [m.content for m in fake.supervisor_inputs[-1] if isinstance(m, HumanMessage) and not m.content.startswith("(상담 안내)")] == ["안녕?"]


async def test_same_agent_once_per_turn_and_hop_limit(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="account"), Route(next="account")]  # 담당이 되물었는데 감독관이 또 고르는 핑퐁
    fake.replies = [AIMessage("어느 계좌로 보낼까요?")]
    data = (await chat(client, tony, "토니한테 보내줘")).json()["data"]
    assert data["routed"] == ["account"] and data["reply"] == "어느 계좌로 보낼까요?"

    fake.routes = [Route(next="account"), Route(next="card"), Route(next="product")]
    fake.replies = [AIMessage(f"답 {i}") for i in range(MAX_HOPS)]
    data = (await chat(client, tony, "다 알려줘")).json()["data"]
    assert data["routed"] == ["account", "card", "product"]  # 세 번에서 멈춤 (네 번째 감독관 호출 없음)
    assert data["reply"] == "답 0\n\n답 1\n\n답 2"


async def test_llm_failure_and_disabled(bank):
    client, tony, peter, src, dst, fake = bank
    fake.fail = True
    res = await chat(client, tony, "내 계좌")
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    app.dependency_overrides.pop(get_llm)
    res = await chat(client, tony, "내 계좌")  # 키가 없으면 (테스트는 항상 없음)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"
    assert (await client.post("/chat", json={"message": "안녕"})).status_code == 401


async def test_same_session_one_turn_at_a_time(bank):
    client, tony, peter, src, dst, fake = bank
    session_id = str(uuid.uuid4())
    fake.delay = 0.2
    fake.routes = [Route(next="FINISH", reply="네")]
    first, second = await asyncio.gather(chat(client, tony, "안녕", session_id), chat(client, tony, "안녕", session_id))
    assert sorted([first.status_code, second.status_code]) == [200, 409]  # 두 번 눌러도 한 턴만
    assert 409 in (first.status_code, second.status_code)
    busy = first if first.status_code == 409 else second
    assert busy.json()["error"]["code"] == "CHAT_BUSY"


async def test_compound_request_second_agent_gets_its_task(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="card"), Route(next="account"), Route(next="FINISH")]
    fake.replies = [AIMessage("카드를 정지했어요."), AIMessage("잔액은 1,000,000원이에요.")]
    data = (await chat(client, tony, "카드 정지하고 잔액 알려줘")).json()["data"]
    assert data["routed"] == ["card", "account"]
    assert data["reply"] == "카드를 정지했어요.\n\n잔액은 1,000,000원이에요."  # 두 담당의 답이 모두 나간다
    second = fake.agent_inputs[1][-1]  # 두 번째 담당이 받은 마지막 메시지: 앞 담당의 AI 답이 아니라 할 일 안내
    assert isinstance(second, HumanMessage) and "계좌" in second.content
    history = (await client.get(f"/chat/{data['session_id']}", headers=tony)).json()["data"]
    assert not any("상담 안내" in t["content"] for t in history)  # 안내는 저장하지 않음


def test_recent_starts_at_human_and_reply_is_this_turn():
    messages = [HumanMessage("q0")] + [m for i in range(HISTORY) for m in (AIMessage("", tool_calls=[
        {"name": "x", "args": {}, "id": f"c{i}"}]), ToolMessage("r", tool_call_id=f"c{i}"))] + [HumanMessage("q1")]
    assert isinstance(recent(messages)[0], HumanMessage)  # 도구 결과로 시작해서 짝이 어긋나지 않게
    assert final_reply([HumanMessage("a"), AIMessage("예전 답"), HumanMessage("b")]).startswith("죄송합니다")
