"""ClearingHub SPEC 2.2와 2.5. 전송할 본문 바이트에 그대로 서명한다."""

import base64
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def message(timestamp: str, *fields: str | int, body: bytes) -> bytes:
    return ("\n".join(map(str, (timestamp, *fields))) + "\n").encode() + body


def sign(key: str, data: bytes) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key, validate=True))
    return base64.b64encode(private_key.sign(data)).decode()


def verify(key: str, data: bytes, signature: str) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True))
        public_key.verify(base64.b64decode(signature, validate=True), data)
    except (InvalidSignature, ValueError):
        return False
    return True


def fresh(timestamp: str) -> bool:
    return (
        timestamp.isascii() and timestamp.isdecimal() and len(timestamp) <= 12
        and abs(int(time.time()) - int(timestamp)) <= 300
    )


def verify_response(key: str, response, request_signature: str) -> bool:
    timestamp = response.headers.get("X-Response-Timestamp", "")
    return (
        response.headers.get("X-Signature-Alg") == "ed25519"
        and fresh(timestamp)
        and verify(
            key, message(timestamp, response.status_code, request_signature, body=response.content),
            response.headers.get("X-Response-Signature", ""),
        )
    )
