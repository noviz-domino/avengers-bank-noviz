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
        ok = await client.post("/mcp/", content=json.dumps(rpc), headers={**accept, **tony})
        anonymous = await client.post("/mcp/", content=json.dumps(rpc), headers=accept)
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
