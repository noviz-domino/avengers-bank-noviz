"""로컬 MCP 서버 (Claude Desktop·Claude Code, ADR 0005·0014).

    uv run python -m avengers_bank.domains.mcp_server login   # 한 번: 아이디·비밀번호 → refresh token을 파일에
    uv run python -m avengers_bank.domains.mcp_server         # MCP 앱이 stdio로 띄운다

비밀번호는 저장하지 않는다. refresh token은 쓸 때마다 바뀌어 파일에 다시 쓴다. 14일 동안 안 쓰면 다시 로그인.
"""

import getpass
import os
import sys
from pathlib import Path

import httpx

from avengers_bank.domains.mcp_server import api

TOKEN_PATH = Path(os.environ.get("AVENGERS_TOKEN_FILE", Path.home() / ".avengers-bank" / "mcp-token.json"))


def login() -> None:
    login_id = input("아이디: ")
    password = getpass.getpass("비밀번호: ")
    res = httpx.post(f"{api.API_URL}/users/login", json={"login_id": login_id, "password": password, "device_name": "MCP (로컬)"}, timeout=30)
    if res.is_error:
        sys.exit(f"로그인 실패: {res.json().get('error', {}).get('message', res.status_code)}")
    api.TokenFile(TOKEN_PATH).save(res.json()["data"]["refresh_token"])
    print(f"로그인했습니다. 토큰 파일: {TOKEN_PATH}")


def main() -> None:
    if sys.argv[1:] == ["login"]:
        return login()
    api.token_file = api.TokenFile(TOKEN_PATH)
    from avengers_bank.domains.mcp_server.server import mcp

    mcp.run("stdio")


if __name__ == "__main__":
    main()
