import uuid

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from avengers_bank.domains.agent.graph import MAX_HOPS, Route
from avengers_bank.domains.agent.llm import get_llm
from avengers_bank.domains.rag import router as rag_router
from avengers_bank.main import app
from avengers_bank.seed import seed_products
from tests.test_transfers import balance, open_account, user

pytestmark = pytest.mark.anyio


class FakeChat(BaseChatModel):
    """Gemini 대신: 감독관의 선택(routes)과 담당 Agent의 응답(replies)을 차례로 내놓는다. 도구는 진짜로 불린다"""

    routes: list = Field(default_factory=list)
    replies: list = Field(default_factory=list)
    agent_inputs: list = Field(default_factory=list)  # 담당 Agent가 받은 메시지들
    supervisor_inputs: list = Field(default_factory=list)
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.agent_inputs.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        def route(messages):
            if self.fail:
                raise RuntimeError("Gemini 장애")
            self.supervisor_inputs.append(messages)
            return self.routes.pop(0)
        return RunnableLambda(route)


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
    humans = [m.content for m in fake.supervisor_inputs[1] if isinstance(m, HumanMessage)]
    assert humans == ["안녕", "고마워"]  # 같은 대화방이면 앞 대화를 기억한다

    history = (await client.get(f"/chat/{first['session_id']}", headers=tony)).json()["data"]
    assert [t["role"] for t in history] == ["user", "assistant", "user", "assistant"]
    assert (await client.get(f"/chat/{first['session_id']}", headers=peter)).json()["data"] == []  # 남의 대화방

    fake.routes = [Route(next="FINISH", reply="처음 뵙겠습니다")]
    await chat(client, peter, "안녕?", first["session_id"])  # 토니의 session_id를 써도 피터의 새 대화
    assert [m.content for m in fake.supervisor_inputs[-1] if isinstance(m, HumanMessage)] == ["안녕?"]


async def test_hop_limit_stops_ping_pong(bank):
    client, tony, peter, src, dst, fake = bank
    fake.routes = [Route(next="account")] * MAX_HOPS  # 감독관이 계속 같은 담당을 고르는 경우
    fake.replies = [AIMessage(f"답 {i}") for i in range(MAX_HOPS)]
    data = (await chat(client, tony, "계좌")).json()["data"]
    assert data["routed"] == ["account"] * MAX_HOPS and data["reply"] == f"답 {MAX_HOPS - 1}"


async def test_llm_failure_and_disabled(bank):
    client, tony, peter, src, dst, fake = bank
    fake.fail = True
    res = await chat(client, tony, "내 계좌")
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    app.dependency_overrides.pop(get_llm)
    res = await chat(client, tony, "내 계좌")  # 키가 없으면 (테스트는 항상 없음)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"
    assert (await client.post("/chat", json={"message": "안녕"})).status_code == 401
