"""MCP 도구가 REST API를 부르는 곳 (ADR 0004: MCP는 DB·service를 직접 부르지 않고 사용자 토큰으로 REST만).

- HTTP(/mcp, 우리 Agent): 요청의 Authorization 헤더를 그대로 넘기고, 앱 안의 API를 네트워크 없이 부른다.
- 로컬 stdio(Claude Desktop 등, ADR 0005): refresh token을 파일에 두고 access token을 받아 쓴다.
"""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import jwt
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

TIMEOUT = 60.0  # RAG 답변(Gemini)까지 기다린다


def login_again() -> ToolError:
    return ToolError("로그인이 필요합니다. 터미널에서 `python -m avengers_bank.domains.mcp_server login`을 실행하세요.")


class TokenFile:
    """로컬 stdio용. refresh token은 쓸 때마다 바뀌어서(ADR 0005) 받을 때마다 파일에 다시 쓴다.
    같은 refresh token을 두 번 쓰면 도난으로 보고 로그인이 끊기므로, 교체는 한 번에 하나만"""

    def __init__(self, path: Path):
        self.path, self.access, self.expires = path, None, 0.0
        self.lock = asyncio.Lock()

    def save(self, refresh_token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")
        os.chmod(tmp, 0o600)  # 나만 읽기 (Windows는 무시됨)
        tmp.replace(self.path)  # 쓰다가 끊겨도 옛 파일이 남게

    async def token(self, client: httpx.AsyncClient) -> str:
        async with self.lock:
            if self.access and time.time() < self.expires - 60:
                return self.access
            if not self.path.exists():
                raise login_again()
            refresh = json.loads(self.path.read_text(encoding="utf-8"))["refresh_token"]
            res = await client.post("/users/token/refresh", json={"refresh_token": refresh})
            if res.is_error:
                raise login_again()
            data = res.json()["data"]
            self.save(data["refresh_token"])
            self.access = data["access_token"]
            # 서명 확인은 서버가 한다. 여기서는 언제 다시 받을지만 본다
            self.expires = jwt.decode(self.access, options={"verify_signature": False})["exp"]
            return self.access


# 로컬 stdio로 띄우면 __main__이 채운다. 비어 있으면 HTTP 모드(요청 헤더의 토큰)
token_file: TokenFile | None = None
API_URL = os.environ.get("AVENGERS_API_URL", "http://localhost:8000")


def client() -> httpx.AsyncClient:
    if token_file is not None:
        return httpx.AsyncClient(base_url=API_URL, timeout=TIMEOUT)
    from avengers_bank.main import app  # 앱이 이 서버를 /mcp에 붙여서, 위에서 가져오면 순환 import

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bank", timeout=TIMEOUT)


async def token_for(ctx: Context, c: httpx.AsyncClient) -> str:
    if token_file is not None:
        return await token_file.token(c)
    request = getattr(ctx.request_context, "request", None)
    auth = request.headers.get("authorization", "") if request is not None else ""
    if not auth.lower().startswith("bearer "):
        raise ToolError("Authorization: Bearer <access token> 헤더가 필요합니다.")
    return auth[7:]


async def call(ctx: Context, method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict:
    """REST API를 사용자 토큰으로 부르고 data와 message를 돌려준다. 실패하면 서버의 오류 코드·메시지를 그대로 도구 오류로"""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if body is not None:
        body = {k: v for k, v in body.items() if v is not None}
    async with client() as c:
        token = await token_for(ctx, c)
        headers = {"Authorization": f"Bearer {token}", "X-Requested-By": "MCP"}  # 승인 화면에 "AI가 만든 요청"
        res = await c.request(method, path, json=body, params=params, headers=headers)
    payload = res.json()
    if res.is_error:
        error = payload.get("error") or {}
        raise ToolError(f"{error.get('code', res.status_code)}: {error.get('message', '요청을 처리할 수 없습니다.')}")
    return {"message": payload.get("message"), "data": payload.get("data")}
