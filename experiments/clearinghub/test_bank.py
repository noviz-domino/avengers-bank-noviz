import base64
import importlib
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from fastapi.testclient import TestClient

from signing import sign_request, verify_response


def keys():
    key = Ed25519PrivateKey.generate()
    return (
        base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
        base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode(),
    )


def test_signed_receive_and_duplicate(monkeypatch):
    hub_private, hub_public = keys()
    bank_private, bank_public = keys()
    monkeypatch.setenv('BANK_PRIVATE_KEY', bank_private)
    monkeypatch.setenv('HUB_PUBLIC_KEY', hub_public)
    bank = importlib.import_module('bank')
    bank.received.clear()
    client = TestClient(bank.app)
    body = ('{"transfer_id":"' + str(uuid.uuid4()) + '","to_account":"110-123-000001","amount":100}').encode()
    headers = {**sign_request(hub_private, 'POST', '/receive', body), 'X-Bank-Code': '000', 'Content-Type': 'application/json'}
    response = client.post('/interbank/receive', content=body, headers=headers)
    assert response.status_code == 200
    assert verify_response(bank_public, response.headers['X-Response-Timestamp'], 200, headers['X-Signature'], response.content, response.headers['X-Response-Signature'])
    assert client.post('/interbank/receive', content=body, headers=headers).json() == response.json()
    assert len(bank.received) == 1
    assert client.post('/interbank/receive', content=body, headers={**headers, 'X-Signature': 'invalid'}).status_code == 401
