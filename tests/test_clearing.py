import asyncio
import base64
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr
from sqlalchemy import select

from avengers_bank.core.config import get_settings
from avengers_bank.core.database import SessionLocal
from avengers_bank.core.exceptions import ApiException
from avengers_bank.domains.accounts.models import AccountTransaction
from avengers_bank.domains.approvals.models import PendingAction
from avengers_bank.domains.transfers import clearing
from avengers_bank.domains.transfers.signing import message, sign, verify, verify_response
from tests.test_transfers import PIN, balance, bank, transfer

pytestmark = pytest.mark.anyio


def keypair():
    key = Ed25519PrivateKey.generate()
    return tuple(base64.b64encode(value).decode() for value in (
        key.private_bytes_raw(), key.public_key().public_bytes_raw(),
    ))


@pytest.fixture
def keys(monkeypatch):
    hub_private, hub_public = keypair()
    bank_private, bank_public = keypair()
    config = get_settings()
    monkeypatch.setattr(config, "clearing_private_key", SecretStr(bank_private))
    monkeypatch.setattr(config, "clearing_hub_public_key", hub_public)
    monkeypatch.setattr(config, "clearing_bank_code", "903")
    monkeypatch.setattr(config, "clearing_api_key", SecretStr("test-key"))
    return hub_private, hub_public, bank_public


def test_signature_matches_spec():
    key = "cycR/h4ydSTPkBGuRFO340cDtdAdwrXQjKC4N1GPgtQ="
    path = "/receive/7c9e6679-7425-40de-944b-e07fc1f90ae7"
    assert sign(key, message("1762300800", "GET", path, body=b"")) == (
        "IMn6yCKkn/eZGPNY74b3+cNvA/4ax9knE97hh4wCQnPEHe6IEdKREh/Pit3+7bJJjx801OiRbJIvJD0HbKzPAA=="
    )


async def test_callback_auth_validation_and_concurrent_idempotency(bank, keys):
    client, _, _, src, dst = bank
    hub_key, _, bank_public = keys
    transfer_id = str(uuid.uuid4())
    payload = {
        "transfer_id": transfer_id, "from_bank": "902", "from_bank_name": "SimBank",
        "from_account": "SIM-1", "to_account": dst["account_num"], "amount": 1_000,
        "sender_name": "팀원", "memo": "테스트",
    }

    async def call(method, path, data=None, *, age=0, tamper=False):
        body = b"" if data is None else json.dumps(data, ensure_ascii=False).encode()
        timestamp = str(int(time.time()) - age)
        signature = sign(hub_key, message(timestamp, method, path, body=body))
        response = await client.request(method, "/interbank" + path, content=body + (b" " if tamper else b""), headers={
            "X-Bank-Code": "000", "X-Timestamp": timestamp, "X-Signature-Alg": "ed25519",
            "X-Signature": signature, "Content-Type": "application/json",
        })
        assert verify_response(bank_public, response, signature)
        return response

    assert (await client.post("/interbank/receive", json=payload)).status_code == 401
    assert (await call("POST", "/receive", payload, tamper=True)).json()["error"] == "SIGNATURE_INVALID"
    assert (await call("POST", "/receive", payload, age=301)).json()["error"] == "SIGNATURE_EXPIRED"
    assert (await call("POST", "/receive", payload | {"amount": "1000"})).status_code == 422
    assert (await call("POST", "/receive", payload | {"amount": -1})).json()["error"] == "AMOUNT_INVALID"
    assert (await call("POST", "/receive", payload | {"to_account": "missing"})).status_code == 404
    assert (await call("GET", f"/receive/{transfer_id}")).status_code == 404
    assert await balance(dst["account_id"]) == 0

    replies = await asyncio.gather(*(call("POST", "/receive", payload) for _ in range(2)))
    assert [reply.status_code for reply in replies] == [200, 200]
    assert await balance(dst["account_id"]) == 1_000
    assert await balance(src["account_id"]) == 1_000_000
    status = await call("GET", f"/receive/{transfer_id}")
    assert status.json()["status"] == "COMPLETED"
    async with SessionLocal() as db:
        row = (await db.scalars(select(AccountTransaction))).one()
        assert (row.tx_type, row.counterparty_name) == ("TRANSFER_IN", "SimBank 팀원")


@pytest.mark.parametrize("outcome", ["COMPLETED", "FAILED"])
async def test_outbound_pin_timeout_and_finalization(bank, keys, monkeypatch, outcome):
    client, tony, peter, src, dst = bank
    hub_private, _, bank_public = keys
    requests = []
    settled = False
    real_client = httpx.AsyncClient

    def hub(request):
        timestamp = request.headers["X-Timestamp"]
        signature = request.headers["X-Signature"]
        path = request.url.path
        assert verify(bank_public, message(timestamp, request.method, path, body=request.content), signature)
        assert request.headers["X-Bank-Code"] == "903"
        requests.append(path)
        if path == "/v1/inquiry":
            status, data = 200, {"holder_name": "팀원"}
        elif path == "/v1/transfers":
            body = json.loads(request.content)
            assert body["transfer_id"] == str(action_id)
            assert body["amount"] == 1_000_000
            assert body["to_bank"] == "902"
            raise httpx.ReadTimeout("응답 유실", request=request)
        elif settled:
            status, data = 200, {"status": outcome, "transfer_id": str(action_id)}
        else:
            status, data = 404, {"error": "TRANSFER_NOT_FOUND"}
        body = json.dumps(data).encode()
        signed = sign(hub_private, message(timestamp, status, signature, body=body))
        return httpx.Response(status, content=body, headers={
            "X-Response-Timestamp": timestamp, "X-Response-Signature": signed, "X-Signature-Alg": "ed25519",
        })

    monkeypatch.setattr(clearing.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(hub), **kw))
    request = transfer(src, dst, amount=1_000_000, to_bank="902")
    assert (await client.post("/transfers", json=request, headers=peter)).status_code == 400
    created = await client.post("/transfers", json=request, headers=tony)
    assert created.status_code == 202, created.text
    action_id = uuid.UUID(created.json()["data"]["action_id"])
    url = f"/approvals/{action_id}/approve"
    assert (await client.post(url, json={"pin": "000000"}, headers=tony)).status_code == 400
    assert await balance(src["account_id"]) == 1_000_000
    assert requests == ["/v1/inquiry"]

    approved = await client.post(url, json={"pin": PIN}, headers=tony)
    assert approved.json()["data"]["status"] == "APPROVED"
    assert await balance(src["account_id"]) == 0
    closed = await client.post(f"/accounts/{src['account_id']}/close", headers=tony)
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "CLEARING_PENDING"
    async with SessionLocal() as db:
        payload = (await db.get(PendingAction, action_id)).payload
    with pytest.raises(ApiException, match="응답을 확인할 수 없습니다"):
        await clearing.reconcile(action_id, payload)
    assert await balance(src["account_id"]) == 0
    settled = True
    await asyncio.gather(*(clearing.reconcile(action_id, payload) for _ in range(2)))
    detail = (await client.get(f"/approvals/{action_id}", headers=tony)).json()["data"]
    assert detail["result"]["clearing_status"] == outcome
    assert await balance(src["account_id"]) == (1_000_000 if outcome == "FAILED" else 0)
    assert requests.count("/v1/transfers") == 1
