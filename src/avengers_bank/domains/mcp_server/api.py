"""MCP 도구가 REST API를 부르는 곳 (ADR 0004: MCP는 DB·service를 직접 부르지 않고 사용자 토큰으로 REST만).

- HTTP(/mcp, 우리 Agent): 요청의 Authorization 헤더를 그대로 넘기고, 앱 안의 API를 네트워크 없이 부른다.
- 로컬 stdio(Claude Desktop 등, ADR 0005): refresh token을 파일에 두고 access token을 받아 쓴다.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

import httpx
import jwt
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

TIMEOUT = 60.0  # RAG 답변(Gemini)까지 기다린다
LOCK_WAIT = 30.0


def login_again() -> ToolError:
    return ToolError("로그인이 필요합니다. 터미널에서 `python -m avengers_bank.domains.mcp_server login`을 실행하세요.")


def server_down() -> ToolError:
    return ToolError("은행 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")


@asynccontextmanager
async def file_lock(path: Path):
    """여러 프로세스(Claude Desktop과 Claude Code가 각각 띄운 서버)가 같은 토큰 파일을 쓸 때 교체를 한 줄로.
    잠금 파일을 '없을 때만 만들기'로 잡는다 (표준 라이브러리만, Windows·리눅스 공통)"""
    deadline = time.monotonic() + LOCK_WAIT
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:  # 죽은 프로세스가 남긴 잠금은 기다리다 치운다
                path.unlink(missing_ok=True)
                continue
            await asyncio.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


class TokenFile:
    """로컬 stdio용. refresh token은 쓸 때마다 바뀌어서(ADR 0005) 받을 때마다 파일에 다시 쓴다.
    같은 refresh token을 두 번 쓰면 도난으로 보고 로그인이 끊기므로, 교체는 한 번에 하나만
    (프로세스 안은 asyncio 잠금, 프로세스 사이는 파일 잠금, 잠근 뒤 파일을 다시 읽는다)"""

    def __init__(self, path: Path):
        self.path, self.access, self.expires = path, None, 0.0
        self.lock = asyncio.Lock()

    def save(self, refresh_token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)  # 처음부터 나만 읽기 (Windows는 무시)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"refresh_token": refresh_token}, f)
        tmp.replace(self.path)  # 쓰다가 끊겨도 옛 파일이 남게

    def forget(self) -> None:
        self.access = None  # 서버가 401을 주면 다음 호출에서 새로 받는다

    async def token(self, client: httpx.AsyncClient) -> str:
        async with self.lock:
            if self.access and time.time() < self.expires - 60:
                return self.access
            async with file_lock(self.path.with_suffix(".lock")):
                if not self.path.exists():
                    raise login_again()
                refresh = json.loads(self.path.read_text(encoding="utf-8"))["refresh_token"]
                try:
                    res = await client.post("/users/token/refresh", json={"refresh_token": refresh})
                except httpx.HTTPError:
                    raise server_down() from None
                if res.status_code == 401:
                    raise login_again()
                if res.is_error:
                    raise server_down()  # 일시 장애에 다시 로그인하라고 하지 않는다
                data = res.json()["data"]
                self.save(data["refresh_token"])
            self.access = data["access_token"]
            # 서명 확인은 서버가 한다. 여기서는 언제 다시 받을지만 본다
            self.expires = jwt.decode(self.access, options={"verify_signature": False})["exp"]
            return self.access


# 로컬 stdio로 띄우면 __main__이 채운다. 비어 있으면 HTTP 모드(요청 헤더의 토큰)
token_file: TokenFile | None = None
# 우리 Agent가 메모리 연결로 부를 때: 채팅 요청마다 그 사용자의 토큰과 "AGENT"를 넣는다.
# ContextVar라서 동시에 들어온 다른 사용자의 요청과 섞이지 않는다 (ADR 0015)
agent_token: ContextVar[str | None] = ContextVar("agent_token", default=None)
requester: ContextVar[str] = ContextVar("requester", default="MCP")
API_URL = os.environ.get("AVENGERS_API_URL", "http://localhost:8000")


def client() -> httpx.AsyncClient:
    if token_file is not None:
        return httpx.AsyncClient(base_url=API_URL, timeout=TIMEOUT)
    from avengers_bank.main import app  # 앱이 이 서버를 /mcp에 붙여서, 위에서 가져오면 순환 import

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bank", timeout=TIMEOUT)


async def token_for(ctx: Context, c: httpx.AsyncClient) -> str:
    if (token := agent_token.get()) is not None:
        return token
    if token_file is not None:
        return await token_file.token(c)
    request = getattr(ctx.request_context, "request", None)
    auth = request.headers.get("authorization", "") if request is not None else ""
    if not auth.lower().startswith("bearer "):
        raise ToolError("Authorization: Bearer <access token> 헤더가 필요합니다.")
    return auth[7:]


async def send(ctx: Context, c: httpx.AsyncClient, method: str, path: str, body, params) -> httpx.Response:
    headers = {"Authorization": f"Bearer {await token_for(ctx, c)}", "X-Requested-By": requester.get()}  # 승인 화면에 "AI가 만든 요청"
    return await c.request(method, path, json=body, params=params, headers=headers)


async def call(ctx: Context, method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict:
    """REST API를 사용자 토큰으로 부르고 data와 message를 돌려준다. 실패하면 서버의 오류 코드·메시지를 그대로 도구 오류로"""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if body is not None:
        body = {k: v for k, v in body.items() if v is not None}
    async with client() as c:
        try:
            res = await send(ctx, c, method, path, body, params)
            if res.status_code == 401 and token_file is not None:  # 만료 전에 무효가 된 토큰: 새로 받아 한 번만 다시
                token_file.forget()
                res = await send(ctx, c, method, path, body, params)
        except httpx.HTTPError:
            raise server_down() from None
    try:
        payload = res.json()
    except ValueError:  # 프록시의 502 HTML 같은 JSON 아닌 응답
        raise server_down() from None
    if res.is_error:
        error = payload.get("error") or {}
        raise ToolError(f"{error.get('code', res.status_code)}: {error.get('message', '요청을 처리할 수 없습니다.')}")
    return {"message": payload.get("message"), "data": payload.get("data")}
