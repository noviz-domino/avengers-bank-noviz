# bank.py — 받는 쪽 최소 구현 (4절). 저장은 메모리라 연습용이다
import json, os
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from signing import sign_response, verify_request

BANK_PRIVATE_KEY = os.environ["BANK_PRIVATE_KEY"]  # 응답 서명용 내 개인키
HUB_PUBLIC_KEY = os.environ["HUB_PUBLIC_KEY"]  # 허브 요청 검증용
PREFIX = "/interbank"  # base_url의 경로 부분
ACCOUNTS = {"110-123-000001": "김민수"}  # 계좌번호 → 예금주 (실제로는 DB)
# transfer_id → 입금 기록. 실제로는 DB 테이블에 transfer_id 유니크 제약을 걸고, 입금과 기록을 한 트랜잭션으로 (4.2 규칙 1·2)
received: dict[str, dict] = {}


class SignResponses:
    """순수 ASGI 미들웨어: 2xx·4xx 응답 본문 바이트에 응답 서명을 붙인다 (2.5). 서명 검증 실패 401에도 붙는다."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_signature, start = dict(scope["headers"]).get(b"x-signature", b"").decode(), {}

        async def send_signed(message):
            if message["type"] == "http.response.start":
                return start.update(message)  # 본문을 볼 때까지 미룬다
            if start:
                if start["status"] < 500:
                    signed = sign_response(BANK_PRIVATE_KEY, start["status"], request_signature, message.get("body", b""))
                    start["headers"] = [*start["headers"], *((k.lower().encode(), v.encode()) for k, v in signed.items())]
                await send(start)
                start.clear()
            await send(message)
        await self.app(scope, receive, send_signed)


app = FastAPI()
app.add_middleware(SignResponses)


class BadSignature(Exception):
    pass


def error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, **extra}, status_code=status)


# 모두 401이면 충분하다. 오류 코드를 나누려면 2.3 끝: 헤더 없음·X-Bank-Code가 000이 아님 → UNAUTHORIZED, 시각 초과 → SIGNATURE_EXPIRED
@app.exception_handler(BadSignature)
async def bad_signature(request: Request, exc: BadSignature):
    return error(401, "SIGNATURE_INVALID", "서명이 맞지 않습니다")  # 이 401에도 응답 서명이 붙는다


async def hub_request(request: Request) -> dict:
    """허브 서명 검증 (2.2): 원본 바이트로, 허브 공개키로, PATH는 base_url 뒤 부분. 입금 처리보다 먼저 한다."""
    body, h = await request.body(), request.headers
    path = request.url.path.partition(PREFIX)[2]  # /interbank/receive → /receive
    if (h.get("x-bank-code") != "000" or h.get("x-signature-alg", "ed25519") != "ed25519"
            or not verify_request(HUB_PUBLIC_KEY, h.get("x-timestamp"), request.method, path, body, h.get("x-signature"))):
        raise BadSignature()
    return json.loads(body) if body else {}


@app.post(PREFIX + "/inquiry")
async def inquiry(request: Request):
    account = (await hub_request(request)).get("account_num")
    if account not in ACCOUNTS:
        return error(404, "ACCOUNT_NOT_FOUND", "받는 계좌를 찾을 수 없습니다")
    return {"holder_name": ACCOUNTS[account]}


@app.post(PREFIX + "/receive")
async def receive(request: Request):
    data = await hub_request(request)
    tid = data.get("transfer_id")
    if tid not in received:  # 같은 ID가 다시 오면 입금하지 않고 같은 답 (4.2 규칙 1)
        if data.get("to_account") not in ACCOUNTS:  # 거절은 4xx, 기록하지 않는다 (4.2 규칙 5)
            return error(404, "ACCOUNT_NOT_FOUND", "받는 계좌를 찾을 수 없습니다", transfer_id=tid)
        # 여기서 [한 트랜잭션] 고객 계좌 입금 + 기록. 유니크 제약에 걸리면 4xx가 아니라 200(저장된 결과)이나 5xx (4.2 규칙 2)
        received[tid] = {**data, "holder_name": ACCOUNTS[data["to_account"]],
                         "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return {"transfer_id": tid, "status": "COMPLETED", "holder_name": received[tid]["holder_name"]}


@app.get(PREFIX + "/receive/{transfer_id}")
async def receive_status(transfer_id: str, request: Request):
    await hub_request(request)
    if (record := received.get(transfer_id)) is None:  # 입금하지 않은 거래는 모두 404 (4.3)
        return error(404, "TRANSFER_NOT_FOUND", "그 거래 ID로 입금한 적이 없습니다", transfer_id=transfer_id)
    return {"transfer_id": transfer_id, "status": "COMPLETED", "holder_name": record["holder_name"],
            "received_at": record["received_at"]}
