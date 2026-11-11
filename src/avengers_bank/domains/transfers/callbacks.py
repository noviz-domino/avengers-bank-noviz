"""허브가 호출하는 수신 전용 API. 고객 출금·승인과 경로 및 인증이 분리된다."""

import time
import uuid
from collections.abc import Callable
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.config import get_settings
from avengers_bank.core.database import get_db
from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import record_clearing_entry
from avengers_bank.domains.transfers.models import ClearingReceipt
from avengers_bank.domains.transfers.signing import fresh, message, sign, verify
from avengers_bank.domains.users.models import User

PREFIX = "/interbank"
BANK_CODE = r"^[0-9]{3}$"
UUID4 = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
MAX_AMOUNT = 100_000_000
AccountNumber = Annotated[str, Field(min_length=1, max_length=50)]
TransferID = Annotated[str, Field(pattern=UUID4)]
DB = Annotated[AsyncSession, Depends(get_db)]


class ClearingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handle = super().get_route_handler()

        async def signed(request: Request) -> Response:
            config = get_settings()
            if not config.clearing_private_key or not config.clearing_hub_public_key:
                return JSONResponse({"error": "UNAVAILABLE", "message": "ClearingHub 수신이 꺼져 있습니다."}, 503)
            signature = request.headers.get("X-Signature", "")
            timestamp = request.headers.get("X-Timestamp", "")
            try:
                if (
                    request.headers.get("X-Bank-Code") != "000"
                    or request.headers.get("X-Signature-Alg") != "ed25519"
                    or not timestamp or not signature
                ):
                    raise ApiException(401, "UNAUTHORIZED", "허브 인증 헤더가 올바르지 않습니다.")
                if not fresh(timestamp):
                    raise ApiException(401, "SIGNATURE_EXPIRED", "요청 서명 시각이 유효하지 않습니다.")
                path = request.url.path.removeprefix(request.scope.get("root_path", "")).removeprefix(PREFIX)
                data = message(timestamp, request.method, path, body=await request.body())
                if not verify(config.clearing_hub_public_key, data, signature):
                    raise ApiException(401, "SIGNATURE_INVALID", "허브 요청 서명이 맞지 않습니다.")
                response = await handle(request)
            except RequestValidationError:
                response = JSONResponse({"error": "VALIDATION_ERROR", "message": "요청 형식이 올바르지 않습니다."}, 422)
            except ApiException as error:
                body = {"error": error.code, "message": error.message}
                if transfer_id := request.path_params.get("transfer_id"):
                    body["transfer_id"] = transfer_id
                response = JSONResponse(body, error.status_code)
            timestamp = str(int(time.time()))
            response.headers.update({
                "X-Response-Timestamp": timestamp,
                "X-Response-Signature": sign(
                    config.clearing_private_key.get_secret_value(),
                    message(timestamp, response.status_code, signature, body=response.body),
                ),
                "X-Signature-Alg": "ed25519",
            })
            return response

        return signed


router = APIRouter(prefix=PREFIX, tags=["clearing callbacks"], route_class=ClearingRoute)


class Inquiry(BaseModel):
    account_num: AccountNumber


class ReceiptRequest(BaseModel):
    transfer_id: TransferID
    from_bank: str = Field(pattern=BANK_CODE)
    from_bank_name: str = Field(min_length=1, max_length=50)
    from_account: AccountNumber
    to_account: AccountNumber
    amount: StrictInt
    sender_name: str = Field(min_length=1, max_length=50)
    memo: str = Field(max_length=100)


async def receiving_account(db: AsyncSession, account_num: str, *, lock: bool = False) -> Account:
    query = select(Account).where(Account.account_num == account_num)
    account = await db.scalar(query.with_for_update() if lock else query)
    if account is None:
        raise ApiException(404, "ACCOUNT_NOT_FOUND", "받는 계좌를 찾을 수 없습니다.")
    if account.status != "ACTIVE" or account.account_type != "CHECKING":
        raise ApiException(400, "ACCOUNT_INACTIVE", "입금 가능한 입출금 계좌가 아닙니다.")
    return account


@router.post("/inquiry")
async def inquiry(data: Inquiry, db: DB):
    account = await receiving_account(db, data.account_num)
    return {"holder_name": (await db.get(User, account.user_id)).name}


def receipt_result(receipt: ClearingReceipt) -> dict:
    return {"transfer_id": str(receipt.transfer_id), "status": "COMPLETED", "holder_name": receipt.holder_name}


@router.post("/receive")
async def receive(data: ReceiptRequest, db: DB):
    transfer_id = uuid.UUID(data.transfer_id)
    try:
        async with db.begin():
            # 계좌 변경보다 먼저 ID를 선점한다. 이미 처리 중인 같은 ID가 4xx로 거절되는 것을 막는다.
            receipt = ClearingReceipt(transfer_id=transfer_id, holder_name="")
            db.add(receipt)
            await db.flush()
            if not 0 < data.amount <= MAX_AMOUNT:
                code = "AMOUNT_INVALID" if data.amount <= 0 else "LIMIT_EXCEEDED"
                raise ApiException(400, code, "입금 금액은 1원 이상 1억 원 이하여야 합니다.")
            account = await receiving_account(db, data.to_account, lock=True)
            if account.balance + data.amount > 2**63 - 1:
                raise ApiException(400, "LIMIT_EXCEEDED", "입금 후 잔액이 계좌의 상한을 넘습니다.")
            receipt.holder_name = (await db.get(User, account.user_id)).name
            record_clearing_entry(
                db, account, transfer_id=transfer_id, tx_type="TRANSFER_IN", amount=data.amount,
                counterparty_name=f"{data.from_bank_name} {data.sender_name}",
                counterparty_account=data.from_account, memo=data.memo or None,
            )
    except IntegrityError:
        receipt = await db.get(ClearingReceipt, transfer_id)
        if receipt is None:
            raise
    except ApiException as error:
        return JSONResponse({
            "error": error.code, "message": error.message, "transfer_id": data.transfer_id,
        }, error.status_code)
    return receipt_result(receipt)


@router.get("/receive/{transfer_id}")
async def receipt_status(transfer_id: TransferID, db: DB):
    receipt = await db.get(ClearingReceipt, uuid.UUID(transfer_id))
    if receipt is None:
        raise ApiException(404, "TRANSFER_NOT_FOUND", "입금한 기록이 없습니다.")
    return receipt_result(receipt) | {
        "received_at": receipt.received_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if receipt.received_at.tzinfo else receipt.received_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
