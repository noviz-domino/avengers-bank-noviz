"""고객이 승인한 타행 출금만 허브에 전달하고, 서명된 확정 결과로 장부를 마감한다."""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from avengers_bank.core.config import get_settings
from avengers_bank.core.database import SessionLocal
from avengers_bank.core.exceptions import ApiException, BadRequestException
from avengers_bank.domains.accounts.models import Account
from avengers_bank.domains.accounts.money import TransferRejected, check_transfer_amount, record_clearing_entry, today_transfer_out
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.transfers.signing import message, sign, verify_response

ACTION_TYPE = "INTERBANK_TRANSFER"
logger = logging.getLogger(__name__)


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.clearing_private_key and settings.clearing_hub_public_key
        and settings.clearing_bank_code and settings.clearing_api_key
    )


async def hub_call(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    if not configured():
        raise ApiException(503, "CLEARING_DISABLED", "ClearingHub 송금이 설정되지 않았습니다.")
    settings = get_settings()
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = sign(settings.clearing_private_key.get_secret_value(), message(timestamp, method, path, body=body))
    headers = {
        "X-Bank-Code": settings.clearing_bank_code, "X-Api-Key": settings.clearing_api_key.get_secret_value(),
        "X-Timestamp": timestamp, "X-Signature": signature, "X-Signature-Alg": "ed25519",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.request(method, settings.clearing_hub_url.rstrip("/") + path, content=body, headers=headers)
        if response.status_code < 500 and verify_response(settings.clearing_hub_public_key, response, signature):
            data = response.json()
            if isinstance(data, dict):
                return response.status_code, data
    except (httpx.HTTPError, ValueError):
        pass
    raise ApiException(502, "CLEARING_UNAVAILABLE", "ClearingHub 응답을 확인할 수 없습니다.")


async def banks() -> list[dict]:
    status, data = await hub_call("GET", "/v1/banks")
    if status != 200 or not isinstance(data.get("banks"), list):
        raise ApiException(502, "CLEARING_UNAVAILABLE", "참가 은행 목록을 확인할 수 없습니다.")
    own_code = get_settings().clearing_bank_code
    return [
        {"bank_code": bank["bank_code"], "name": bank["name"]}
        for bank in data["banks"]
        if isinstance(bank, dict) and isinstance(bank.get("bank_code"), str)
        and isinstance(bank.get("name"), str) and bank["bank_code"] != own_code
    ]


async def recipient(to_bank: str, to_account: str) -> str:
    if to_bank == get_settings().clearing_bank_code:
        raise BadRequestException(message="우리 은행 계좌는 일반 이체를 사용해 주세요.", code="SAME_BANK")
    status, data = await hub_call("POST", "/v1/inquiry", {"to_bank": to_bank, "to_account": to_account})
    holder = data.get("holder_name")
    if status == 200 and isinstance(holder, str) and 0 < len(holder) <= 50:
        return holder
    if data.get("error") in ("BANK_NOT_FOUND", "BANK_INACTIVE", "ACCOUNT_NOT_FOUND", "ACCOUNT_INACTIVE"):
        raise BadRequestException(message="입금 가능한 받는 계좌를 확인해 주세요.", code=data["error"])
    raise ApiException(502, "CLEARING_UNAVAILABLE", "받는 은행의 계좌를 확인할 수 없습니다.")


def check_source(account: Account | None, user_id: int) -> None:
    if account is None or account.user_id != user_id or account.status != "ACTIVE":
        raise TransferRejected("ACCOUNT_NOT_FOUND", "보내는 계좌를 찾을 수 없습니다.")
    if account.account_type != "CHECKING":
        raise TransferRejected("ACCOUNT_CANNOT_SEND", "입출금 계좌에서만 보낼 수 있습니다.")


async def stage_transfer(db: AsyncSession, action: PendingAction) -> None:
    """PIN 승인 트랜잭션에서 출금하고, APPROVED 상태를 송금 대기 기록으로 남긴다."""
    if not configured():
        raise TransferRejected("CLEARING_DISABLED", "ClearingHub 송금이 설정되지 않았습니다.")
    p = action.payload
    src = await db.scalar(select(Account).where(Account.account_id == p["from_account_id"])
                          .with_for_update().execution_options(populate_existing=True))
    check_source(src, action.user_id)
    check_transfer_amount(src, p["amount"], await today_transfer_out(db, src.account_id))
    record_clearing_entry(
        db, src, transfer_id=action.action_id, action_id=action.action_id, tx_type="TRANSFER_OUT",
        amount=-p["amount"], counterparty_name=p["holder_name"], counterparty_account=p["to_account_num"],
        memo=p["memo"],
    )
    action.result = {"transfer_id": str(action.action_id), "clearing_status": "PENDING"}


async def hub_transfer_result(transfer_id: str, payload: dict) -> tuple[int, dict]:
    status, data = await hub_call("GET", f"/v1/transfers/{transfer_id}")
    if status == 404 and data.get("error") == "TRANSFER_NOT_FOUND":
        return await hub_call("POST", "/v1/transfers", {
            "transfer_id": transfer_id, "to_bank": payload["to_bank"], "to_account": payload["to_account_num"],
            "from_account": payload["from_account"], "amount": payload["amount"],
            "sender_name": payload["sender_name"], "memo": payload["memo"] or "",
        })
    return status, data


async def reconcile(action_id: uuid.UUID, payload: dict) -> None:
    """재시작·응답 유실에도 같은 ID로 조회하고, 허브에 기록이 없을 때만 전송한다."""
    transfer_id = str(action_id)
    async with SessionLocal.begin() as db:
        pending = (
            PendingAction.action_id == action_id, PendingAction.status == "APPROVED",
            PendingAction.action_type == ACTION_TYPE,
        )
        # 워커끼리 같은 거래를 동시에 보내지 않도록 승인 행만 잠근다. 계좌 잠금은 반환할 때만 잡는다.
        claimed = await db.scalar(select(PendingAction.action_id).where(*pending).with_for_update(skip_locked=True))
        if claimed is None:
            return
        status, data = await hub_transfer_result(transfer_id, payload)
        outcome = data.get("status")
        if data.get("transfer_id") != transfer_id or outcome not in ("COMPLETED", "FAILED"):
            return
        if not (status == 200 or (400 <= status < 500 and outcome == "FAILED")):
            return
        action = await db.scalar(
            update(PendingAction)
            .where(*pending)
            .values(status="EXECUTED" if outcome == "COMPLETED" else "FAILED")
            .returning(PendingAction)
        )
        if action is None:
            return
        action.result = {"transfer_id": transfer_id, "clearing_status": outcome}
        if outcome == "COMPLETED":
            action.executed_at = datetime.now(UTC)
            return
        src = await db.scalar(select(Account).where(Account.account_id == payload["from_account_id"]).with_for_update())
        record_clearing_entry(
            db, src, transfer_id=action_id, action_id=action_id, tx_type="REFUND",
            amount=payload["amount"], counterparty_name=payload["holder_name"],
            counterparty_account=payload["to_account_num"], memo="타행 이체 실패로 반환",
        )
        action.failure_reason = f"{data.get('fail_code') or data.get('error') or 'CLEARING_FAILED'}: 타행 이체가 거절되었습니다."


async def reconcile_pending() -> None:
    last_checked = {}
    while True:
        try:
            async with SessionLocal() as db:
                pending = (await db.execute(
                    select(PendingAction.action_id, PendingAction.payload, PendingAction.approved_at)
                    .where(PendingAction.action_type == ACTION_TYPE, PendingAction.status == "APPROVED")
                    .order_by(PendingAction.approved_at)
                )).all()
            now = datetime.now(UTC)
            previous = last_checked
            last_checked = {}
            for action_id, payload, approved_at in pending:
                slow = now - approved_at.replace(tzinfo=UTC) >= timedelta(minutes=30)
                last_attempt, was_slow = previous.get(action_id, (None, False))
                if slow and not was_slow:
                    logger.warning("ClearingHub 송금 확인 필요: %s", action_id)
                if last_attempt is not None and time.monotonic() - last_attempt < (600 if slow else 30):
                    last_checked[action_id] = last_attempt, slow
                    continue
                try:
                    await reconcile(action_id, payload)
                except ApiException as error:
                    logger.warning("ClearingHub 송금 %s 확인 대기: %s", action_id, error.code)
                except Exception:
                    logger.exception("ClearingHub 송금 %s 마감 실패", action_id)
                last_checked[action_id] = time.monotonic(), slow
        except Exception:
            logger.exception("ClearingHub 송금 결과 확인에 실패했습니다.")
        await asyncio.sleep(5)


@asynccontextmanager
async def clearing_worker():
    worker = asyncio.create_task(reconcile_pending()) if configured() else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
