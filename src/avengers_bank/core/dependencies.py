import secrets
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from avengers_bank.core.database import SessionLocal
from avengers_bank.core.config import get_settings
from avengers_bank.core.exceptions import ForbiddenException, UnauthorizedException
from avengers_bank.domains.users.schemas import UserResponse
from avengers_bank.domains.users.service import user_service

bearer_scheme = HTTPBearer(bearerFormat="JWT", auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UserResponse:
    if credentials is None:
        raise UnauthorizedException(
            message="로그인이 필요합니다.", code="AUTHENTICATION_REQUIRED"
        )
    async with SessionLocal() as db:
        user = await user_service.get_current_user(db, credentials.credentials)
        return UserResponse.model_validate(user)


async def require_system_key(x_system_key: Annotated[str | None, Header()] = None) -> None:
    """시스템 작업(대금 출금 등)은 사용자 토큰이 아니라 서버 키로만 부른다 (ADR 0011)"""
    key = get_settings().system_api_key
    if key is None:
        raise ForbiddenException(message="시스템 작업 API가 꺼져 있습니다.", code="SYSTEM_API_DISABLED")
    if x_system_key is None or not secrets.compare_digest(x_system_key.encode(), key.get_secret_value().encode()):
        raise ForbiddenException(message="시스템 키가 맞지 않습니다.", code="SYSTEM_KEY_INVALID")
