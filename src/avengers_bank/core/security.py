import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from avengers_bank.core.config import get_settings
from avengers_bank.core.exceptions import UnauthorizedException

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(password, hashed_password)
    except UnknownHashError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=ALGORITHM
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise UnauthorizedException(
            message="유효하지 않거나 만료된 토큰입니다.", code="INVALID_TOKEN"
        ) from None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    # 무작위 32바이트라 비밀번호처럼 느린 해시(Argon2)가 필요 없다. DB가 새도 원문은 알 수 없다
    return hashlib.sha256(token.encode()).hexdigest()
