import asyncio
import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from avengers_bank.domains.mcp_server import api
from avengers_bank.domains.mcp_server.server import mcp
from avengers_bank.main import app
from avengers_bank.seed import seed_card_products, seed_products
from tests.test_cards import issue
from tests.test_transfers import balance, open_account, user

pytestmark = pytest.mark.anyio


def asgi_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bank")


class StaticToken:
    def __init__(self, headers):
        self.value = headers["Authorization"][7:]

    async def token(self, client):
        return self.value


@pytest.fixture
async def bank(client, monkeypatch):
    from avengers_bank.core.database import SessionLocal

    async with SessionLocal() as db:
        await seed_products(db)
    async with SessionLocal() as db:
        await seed_card_products(db)
    tony = await user(client, "ironman", "토니")
    peter = await user(client, "spidey", "피터")
    src = await open_account(client, tony, balance=1_000_000)
    dst = await open_account(client, peter)
    monkeypatch.setattr(api, "client", asgi_client)  # 도구가 부르는 REST도 테스트 앱으로
    return client, tony, peter, src, dst


async def tool(name: str, **args):
    """FastMCP로 도구를 부른다. dict 결과는 JSON 텍스트로 오고, LLM도 그 텍스트를 읽는다"""
    content = await mcp.call_tool(name, args)
    return json.loads(content[0].text)


def as_user(monkeypatch, headers):
    monkeypatch.setattr(api, "token_file", StaticToken(headers))


async def test_tool_list_has_no_approval_payment_or_system():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert len(tools) == 16
    assert not [n for n in tools if any(w in n for w in ("approve", "pin", "pay", "bill", "reindex", "refund"))]
    assert tools["get_my_accounts"].annotations.readOnlyHint is True
    assert tools["request_transfer"].annotations.destructiveHint is False  # 승인 대기만 만듦
    assert tools["close_account"].annotations.destructiveHint is True


async def test_transfer_tool_only_creates_pending(bank, monkeypatch):
    client, tony, peter, src, dst = bank
    as_user(monkeypatch, tony)
    result = await tool("request_transfer", from_account_id=src["account_id"],
                        to_account_num=dst["account_num"], amount=50_000, memo="밥값")
    assert result["data"]["status"] == "PENDING" and "PIN" in result["message"]
    again = await tool("request_transfer", from_account_id=src["account_id"],  # 시간 초과·재시도로 또 불려도
                       to_account_num=dst["account_num"], amount=50_000, memo="밥값")
    assert again["data"]["action_id"] == result["data"]["action_id"]  # 승인 대기는 하나
    assert result["data"]["requested_by"] == "MCP"  # 승인 화면이 AI가 만든 요청임을 보여 줄 수 있게
    assert await balance(src["account_id"]) == 1_000_000  # PIN 없이는 돈이 안 움직임


async def test_errors_and_ownership_come_from_rest(bank, monkeypatch):
    client, tony, peter, src, dst = bank
    card = (await issue(client, tony, src)).json()["data"]
    as_user(monkeypatch, peter)  # 남의 카드
    with pytest.raises(ToolError, match="CARD_NOT_FOUND"):
        await tool("suspend_card", card_id=card["card_id"], lost=True)
    as_user(monkeypatch, tony)
    assert (await tool("suspend_card", card_id=card["card_id"], lost=True))["data"]["status"] == "LOST"
    products = await tool("search_products")
    assert products["data"]["cards"] and all(p["type"] != "LOAN" for p in products["data"]["accounts"])


async def test_http_mcp_forwards_bearer_token(bank):
    client, tony, peter, src, dst = bank
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_my_accounts", "arguments": {}}}
    accept = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    async with mcp.session_manager.run():  # 테스트 클라이언트는 앱 lifespan을 돌리지 않는다
        ok = await client.post("/mcp", content=json.dumps(rpc), headers={**accept, **tony})  # 리다이렉트 없이
        anonymous = await client.post("/mcp", content=json.dumps(rpc), headers=accept)
    result = ok.json()["result"]
    assert not result["isError"] and json.loads(result["content"][0]["text"])["data"]["total_balance"] == 1_000_000
    assert anonymous.json()["result"]["isError"] and "Bearer" in anonymous.json()["result"]["content"][0]["text"]


async def test_token_file_rotates_once_and_saves(client, tmp_path, monkeypatch):
    await user(client, "ironman", "토니", pin=None)
    login = (await client.post("/users/login", json={"login_id": "ironman", "password": "password1234"})).json()
    store = api.TokenFile(tmp_path / "mcp-token.json")
    store.save(login["data"]["refresh_token"])
    async with asgi_client() as c:
        # 동시에 두 도구가 불려도 refresh는 한 번만 (두 번 쓰면 재사용으로 보여 로그인이 끊긴다)
        first, second = await asyncio.gather(store.token(c), store.token(c))
        assert first == second
        saved = json.loads(store.path.read_text(encoding="utf-8"))["refresh_token"]
        assert saved != login["data"]["refresh_token"]  # 바뀐 refresh token을 파일에 다시 씀
        res = await c.get("/users/me", headers={"Authorization": f"Bearer {first}"})
        assert res.status_code == 200
        store.access = None  # 만료된 것처럼
        assert await store.token(c)  # 파일의 새 refresh token으로 다시 받을 수 있다


async def test_two_processes_share_token_file(client, tmp_path):
    # Claude Desktop과 Claude Code가 같은 토큰 파일로 서버를 하나씩 띄운 상황 (리뷰 🟡1)
    await user(client, "ironman", "토니", pin=None)
    login = (await client.post("/users/login", json={"login_id": "ironman", "password": "password1234"})).json()
    desktop, code = api.TokenFile(tmp_path / "t.json"), api.TokenFile(tmp_path / "t.json")
    desktop.save(login["data"]["refresh_token"])
    async with asgi_client() as c:
        a, b = await asyncio.gather(desktop.token(c), code.token(c))  # 파일 잠금 → 뒤에 온 쪽은 바뀐 토큰을 읽음
        for token in (a, b):  # 재사용으로 끊겼다면 둘 중 하나는 401
            assert (await c.get("/users/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://bank")


async def test_refresh_failure_kinds(tmp_path):
    store = api.TokenFile(tmp_path / "t.json")
    store.save("old")
    for status, expected in ((503, "연결할 수 없습니다"), (401, "로그인이 필요")):
        async with mock_client(lambda r, s=status: httpx.Response(s, json={}))() as c:
            with pytest.raises(ToolError, match=expected):  # 일시 장애에 다시 로그인하라고 하지 않는다
                await store.token(c)


async def test_call_retries_once_after_401(monkeypatch):
    class Stub:
        forgot = 0

        async def token(self, c):
            return f"t{self.forgot}"

        def forget(self):
            self.forgot += 1

    def handler(request):
        if request.headers["authorization"] == "Bearer t0":  # 만료 전에 무효가 된 토큰
            return httpx.Response(401, json={"error": {"code": "INVALID_TOKEN", "message": "x"}})
        return httpx.Response(200, json={"success": True, "data": {"ok": 1}})

    stub = Stub()
    monkeypatch.setattr(api, "token_file", stub)
    monkeypatch.setattr(api, "client", mock_client(handler))
    assert (await tool("get_my_cards"))["data"] == {"ok": 1} and stub.forgot == 1
    monkeypatch.setattr(api, "client", mock_client(lambda r: httpx.Response(502, text="<html>bad gateway</html>")))
    with pytest.raises(ToolError, match="연결할 수 없습니다"):  # JSON이 아닌 응답
        await tool("get_my_cards")
